"""Public website lead and opportunity models (Phase 10).

These tables are the bridge between the public marketing website and the
internal SAFIR platform. A visitor submits a form on the public site; the row
created here is the *structured internal record* the Holding then works.

Two deliberate design choices:

* **No confidential data by default.** :class:`WebsiteOpportunity` is private
  to the Holding until it is explicitly reviewed and published. Nothing about a
  submitted business is ever rendered on the public site automatically.
* **Attribution is preserved, not inferred.** The UTM/referrer/landing columns
  are written once, at submission time, and never recomputed, so a lead's
  origin cannot drift as the visitor navigates.

Leads are not company-scoped: they are Holding-level demand until routing
assigns them. ``assigned_to_id`` records the internal owner; ``routed_team``
records the team the routing rules selected.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    LeadPriority,
    LeadStatus,
    WebsiteLeadSource,
)

if TYPE_CHECKING:
    from backend.db.models.identity import User


class WebsiteLead(Base, TimestampMixin):
    """One request submitted through the public website.

    Covers every public journey -- company formation, feasibility study,
    opportunity interest, business listing and general contact -- because the
    internal handling is the same: qualify, route, follow up, record outcome.
    The service-specific answers live in ``payload_json`` (validated against a
    strict schema per service before it is stored).
    """

    __tablename__ = "website_leads"
    __table_args__ = (
        Index("ix_website_leads_market_service", "market", "service_type"),
        Index("ix_website_leads_status_created", "status", "created_at"),
        UniqueConstraint("reference", name="uq_website_leads_reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Human-readable, non-sequential public reference shown to the visitor in
    # the confirmation. It is intentionally the only identifier the visitor
    # ever sees; the numeric id stays internal. Unique so a reference can never
    # be mistaken for another lead's.
    reference: Mapped[str] = mapped_column(String(32), nullable=False)

    # ---- routing / classification (set by the server, never by the client) ----
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WebsiteLeadSource.WEBSITE.value, index=True
    )
    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="ar")

    # ---- contact block (every journey collects these) ----
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- consent ----
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ---- service-specific answers (validated per service before storage) ----
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- attribution (captured once, at submission) ----
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(160), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(160), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(160), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    landing_page: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ---- request context (safe subset only; no secrets) ----
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ---- internal handling ----
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LeadStatus.NEW.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LeadPriority.NORMAL.value
    )
    routed_team: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The company the lead is referred to, when routing determines one. Nullable
    # because a lead may be handled at Holding level.
    routed_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])
    attachments: Mapped[list["WebsiteLeadAttachment"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class WebsiteLeadAttachment(Base, TimestampMixin):
    """A file attached to a public submission.

    Stored with the same opaque-key discipline as internal documents: the
    client filename is never used to build a path, and type/size are validated
    server-side before anything is written.
    """

    __tablename__ = "website_lead_attachments"
    __table_args__ = (Index("ix_website_lead_attachments_lead", "lead_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("website_leads.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    lead: Mapped[WebsiteLead] = relationship(back_populates="attachments")


class WebsiteOpportunity(Base, TimestampMixin):
    """A business or opportunity submitted for sale, partnership or investment.

    Distinct from :class:`WebsiteLead` because it carries a business profile
    that must be reviewed before anything is shown publicly. ``is_public`` is
    the single gate: only rows explicitly published by an authorised user can
    appear on the public Opportunities pages.
    """

    __tablename__ = "website_opportunities"
    __table_args__ = (
        Index("ix_website_opportunities_market_status", "market", "status"),
        Index("ix_website_opportunities_public", "is_public", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The lead that produced this opportunity. Kept 1:1 so the internal team
    # sees the submission and the listing as one story.
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("website_leads.id", ondelete="CASCADE"), nullable=False, index=True
    )

    market: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    applicant_capacity: Mapped[str] = mapped_column(String(30), nullable=False)
    opportunity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_min: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    value_max: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    reason_for_listing: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Public-facing copy, written by the Holding when it publishes a listing.
    # Never auto-populated from the confidential description.
    public_title_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    public_title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    public_summary_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lead: Mapped[WebsiteLead] = relationship()
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
