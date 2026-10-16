"""Execution 30 owner-decision models (D01, D04, D09, D11).

These tables carry the *governance* around decisions whose business values are
still the owner's to set. Nothing here activates a financial value: a proposal,
a currency change and a recovery code are records, and the only path from a
record to an effective rule runs through an explicit owner action that writes an
audit row.

Design rules carried from the decisions:

* **D01** -- an accountant *proposes*; only the owner approves. The proposal is
  a separate row from the policy version, so no code path can conflate the two.
  A rejected proposal never changes the effective policy.
* **D04** -- lead redistribution and its history are D04's subject (spec §21 D04:
  "إعادة توزيع العميل"). Every assignment/reassignment is an append-only event
  with its reason, previous assignee and actor, and history reads are scoped
  server-side: the owner sees everything in scope, BD sees lead history, a
  company manager sees only their own company. History is never rewritten.
* **D09** -- a base-currency change is a request that must be reviewed and
  approved and only takes effect from a new financial period. Historical rows
  keep their original currency; no retrospective conversion exists.
* **D11** -- 2FA secrets and recovery codes are stored per user, never in the
  clear for recovery codes, and 2FA is verified at login rather than trusted
  from a claim in the token.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import CurrencyChangeStatus, PolicyProposalStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class PolicyProposal(Base, TimestampMixin):
    """D01: an accountant's request to activate an accounting-policy version.

    The proposal points at the draft ``AccountingPolicy`` row it concerns and
    carries the mandatory reason plus the previous and proposed values so the
    owner can decide without cross-referencing. Only ``approve``/``reject``
    transitions it, and only a user holding ``policy.approve`` may act.
    """

    __tablename__ = "policy_proposals"
    __table_args__ = (
        Index("ix_policy_proposals_company_kind", "company_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_policies.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # The value in force before this proposal, for side-by-side comparison.
    previous_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    proposed_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    proposed_value_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    proposed_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    proposed_effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PolicyProposalStatus.PENDING.value,
        server_default="pending", index=True,
    )
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    policy = relationship("AccountingPolicy", foreign_keys=[policy_id])
    company: Mapped["Company | None"] = relationship(foreign_keys=[company_id])


class LeadAssignment(Base, TimestampMixin):
    """D04: one assignment or reassignment of a lead (append-only).

    A row records who did it, from whom to whom, why, and when. The lead's
    current ``assigned_to_id``/``routed_company_id`` are the fast read; this
    table is the history and is never edited or deleted.
    """

    __tablename__ = "lead_assignments"
    __table_args__ = (Index("ix_lead_assignments_lead", "lead_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("website_leads.id", ondelete="CASCADE"), nullable=False
    )
    # "assign" for the first assignment, "reassign" when an assignee changed.
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    new_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    previous_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    new_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])
    new_assignee: Mapped["User | None"] = relationship(foreign_keys=[new_assignee_id])
    previous_assignee: Mapped["User | None"] = relationship(
        foreign_keys=[previous_assignee_id]
    )


class CurrencyChangeRequest(Base, TimestampMixin):
    """D09: a requested change of a company's base currency.

    The workflow is request -> accountant review -> owner approval ->
    scheduled for a named future financial period. The company's ``currency``
    is only changed when the change is *applied*, and application is refused
    until the approved effective period begins. Historical journals, invoices
    and reports keep the currency they were recorded in: nothing here rewrites
    a past row.
    """

    __tablename__ = "currency_change_requests"
    __table_args__ = (
        Index("ix_currency_change_company_period", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    requested_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CurrencyChangeStatus.REQUESTED.value,
        server_default="requested", index=True,
    )
    # The financial period the change takes effect from (never retrospective).
    effective_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company: Mapped["Company"] = relationship(foreign_keys=[company_id])


class UserTwoFactor(Base, TimestampMixin):
    """D11: a user's second factor (TOTP) and one-time recovery codes.

    ``secret`` is the TOTP shared secret; it is only ever returned once, at
    enrolment. ``confirmed_at`` is set the first time a valid code is supplied,
    so an abandoned enrolment never counts as "2FA on". Recovery codes are
    stored as hashes and consumed (never re-shown) when used.
    """

    __tablename__ = "user_two_factor"
    __table_args__ = (Index("ix_user_two_factor_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class TwoFactorRecoveryCode(Base, TimestampMixin):
    """D11: a single-use recovery code, stored as a hash (never in the clear)."""

    __tablename__ = "two_factor_recovery_codes"
    __table_args__ = (Index("ix_two_factor_recovery_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = [
    "CurrencyChangeRequest",
    "LeadAssignment",
    "PolicyProposal",
    "TwoFactorRecoveryCode",
    "UserTwoFactor",
]
