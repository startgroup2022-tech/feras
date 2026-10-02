"""Monthly report models -- the most important V1 business module.

A report carries the narrative and financial fields a subsidiary submits each
month. The accountant's validation lives in a separate
``monthly_report_financial_reviews`` row so that the original submitted figures
are never overwritten: the verified values feed the Holding dashboard.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
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
from backend.db.models.enums import FinancialReviewStatus, ReportStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

# Money is stored as NUMERIC(18, 2) so that aggregated financial figures are
# exact -- never floating point.
MONEY = Numeric(18, 2)


class MonthlyReport(Base, TimestampMixin):
    __tablename__ = "monthly_reports"
    __table_args__ = (
        # One report per company per month.
        UniqueConstraint("company_id", "period_year", "period_month", name="uq_report_company_period"),
        Index("ix_monthly_reports_company_period", "company_id", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReportStatus.DRAFT.value, index=True
    )

    # ---- financial fields (submitted by the company) ----
    revenue: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    expenses: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    net_result: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    outstanding_receivables: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    # ---- narrative fields ----
    important_developments: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_customers: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_opportunities: Mapped[str | None] = mapped_column(Text, nullable=True)
    major_problems: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_development_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship(back_populates="monthly_reports")
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])
    financial_review: Mapped["MonthlyReportFinancialReview | None"] = relationship(
        back_populates="report", uselist=False, cascade="all, delete-orphan"
    )
    attachments: Mapped[list["MonthlyReportAttachment"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class MonthlyReportFinancialReview(Base, TimestampMixin):
    """The accountant's verification of a submitted report's financial fields."""

    __tablename__ = "monthly_report_financial_reviews"
    __table_args__ = (
        # Exactly one review record per report.
        UniqueConstraint("report_id", name="uq_financial_review_report"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FinancialReviewStatus.PENDING.value, index=True
    )

    # ---- verified figures (may differ from what the company submitted) ----
    verified_revenue: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    verified_expenses: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    verified_net_result: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    verified_outstanding_receivables: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    financial_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_financially_accurate: Mapped[bool | None] = mapped_column(nullable=True)
    flagged_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[MonthlyReport] = relationship(back_populates="financial_review")
    reviewer: Mapped["User"] = relationship()


class MonthlyReportAttachment(Base, TimestampMixin):
    """A file attached to a report.

    Only metadata is stored here; the bytes live outside the database. The
    ``storage_key`` is an opaque server-generated name so a client can never
    traverse the filesystem through a supplied filename.
    """

    __tablename__ = "monthly_report_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("monthly_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    report: Mapped[MonthlyReport] = relationship(back_populates="attachments")
