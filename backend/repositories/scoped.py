"""Scoped repositories.

Every read of company-owned data goes through a repository that applies the
caller's company scope as a SQL filter. This is the structural defence against
IDOR: a record is never fetched by id alone and then checked afterwards -- the
scope is part of the query, so an out-of-scope id simply does not match.

``accessible_company_ids(user)`` returns ``None`` for holding-wide users
(meaning "no company filter") and a concrete list otherwise.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.db.models.enums import FinancialSummaryStatus, ReportStatus, SupportStatus
from backend.db.models.identity import Company, User
from backend.db.models.financial import (
    FinancialPeriod,
    FinancialSummaryVersion,
)
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.db.models.support import SupportRequest
from backend.rbac.authorization import accessible_company_ids


def _apply_company_scope(stmt, column, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        # A scoped user with no grants must match nothing.
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


class CompanyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user: User) -> list[Company]:
        stmt = select(Company).order_by(Company.name_en)
        stmt = _apply_company_scope(stmt, Company.id, user)
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user: User, company_id: int) -> Company | None:
        """Fetch a company only if the user may see it."""
        stmt = select(Company).where(Company.id == company_id)
        stmt = _apply_company_scope(stmt, Company.id, user)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Company | None:
        return self.db.execute(
            select(Company).where(Company.code == code)
        ).scalar_one_or_none()

    def count_for_user(self, user: User) -> int:
        stmt = select(func.count(Company.id))
        stmt = _apply_company_scope(stmt, Company.id, user)
        return int(self.db.execute(stmt).scalar_one())


class MonthlyReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self, user: User, *, company_id: int | None = None, year: int | None = None
    ) -> list[MonthlyReport]:
        stmt = (
            select(MonthlyReport)
            .options(selectinload(MonthlyReport.financial_review))
            .order_by(
                MonthlyReport.period_year.desc(),
                MonthlyReport.period_month.desc(),
                MonthlyReport.company_id,
            )
        )
        stmt = _apply_company_scope(stmt, MonthlyReport.company_id, user)
        if company_id is not None:
            # Intersect the requested company with the caller's scope.
            stmt = stmt.where(MonthlyReport.company_id == company_id)
        if year is not None:
            stmt = stmt.where(MonthlyReport.period_year == year)
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user: User, report_id: int) -> MonthlyReport | None:
        stmt = (
            select(MonthlyReport)
            .options(selectinload(MonthlyReport.financial_review))
            .where(MonthlyReport.id == report_id)
        )
        stmt = _apply_company_scope(stmt, MonthlyReport.company_id, user)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_company_period(
        self, company_id: int, year: int, month: int
    ) -> MonthlyReport | None:
        return self.db.execute(
            select(MonthlyReport).where(
                MonthlyReport.company_id == company_id,
                MonthlyReport.period_year == year,
                MonthlyReport.period_month == month,
            )
        ).scalar_one_or_none()

    def status_counts(self, user: User, year: int, month: int) -> dict[str, int]:
        stmt = (
            select(MonthlyReport.status, func.count(MonthlyReport.id))
            .where(
                MonthlyReport.period_year == year,
                MonthlyReport.period_month == month,
            )
            .group_by(MonthlyReport.status)
        )
        stmt = _apply_company_scope(stmt, MonthlyReport.company_id, user)
        return {status: int(count) for status, count in self.db.execute(stmt)}

    def companies_missing_report(self, user: User, year: int, month: int) -> list[Company]:
        """Active companies with no submitted/reviewed report for the period."""
        submitted = select(MonthlyReport.company_id).where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReport.status.in_(
                [
                    ReportStatus.SUBMITTED.value,
                    ReportStatus.UNDER_REVIEW.value,
                    ReportStatus.REVIEWED.value,
                ]
            ),
        )
        stmt = select(Company).where(Company.id.notin_(submitted))
        stmt = _apply_company_scope(stmt, Company.id, user)
        return list(self.db.execute(stmt).scalars())


class FinancialReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_report(self, report: MonthlyReport) -> MonthlyReportFinancialReview | None:
        return self.db.execute(
            select(MonthlyReportFinancialReview).where(
                MonthlyReportFinancialReview.report_id == report.id
            )
        ).scalar_one_or_none()

    def pending_count(self, user: User) -> int:
        """Reports submitted but not yet financially reviewed."""
        reviewed = select(MonthlyReportFinancialReview.report_id)
        stmt = (
            select(func.count(MonthlyReport.id))
            .where(MonthlyReport.status == ReportStatus.SUBMITTED.value)
            .where(MonthlyReport.id.notin_(reviewed))
        )
        stmt = _apply_company_scope(stmt, MonthlyReport.company_id, user)
        return int(self.db.execute(stmt).scalar_one())


class SupportRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self,
        user: User,
        *,
        company_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
    ) -> list[SupportRequest]:
        stmt = select(SupportRequest).order_by(SupportRequest.created_at.desc())
        stmt = _apply_company_scope(stmt, SupportRequest.company_id, user)
        if company_id is not None:
            stmt = stmt.where(SupportRequest.company_id == company_id)
        if status is not None:
            stmt = stmt.where(SupportRequest.status == status)
        if category is not None:
            stmt = stmt.where(SupportRequest.category == category)
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user: User, request_id: int) -> SupportRequest | None:
        stmt = select(SupportRequest).where(SupportRequest.id == request_id)
        stmt = _apply_company_scope(stmt, SupportRequest.company_id, user)
        return self.db.execute(stmt).scalar_one_or_none()

    def open_count(self, user: User) -> int:
        stmt = (
            select(func.count(SupportRequest.id))
            .where(
                SupportRequest.status.in_(
                    [SupportStatus.NEW.value, SupportStatus.IN_PROGRESS.value]
                )
            )
        )
        stmt = _apply_company_scope(stmt, SupportRequest.company_id, user)
        return int(self.db.execute(stmt).scalar_one())


class FinancialPeriodRepository:
    """Company-scoped access to financial periods and their versions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self,
        user: User,
        *,
        company_id: int | None = None,
        year: int | None = None,
        status: str | None = None,
    ) -> list[FinancialPeriod]:
        stmt = select(FinancialPeriod).order_by(
            FinancialPeriod.period_year.desc(),
            FinancialPeriod.period_month.desc(),
            FinancialPeriod.company_id,
        )
        stmt = _apply_company_scope(stmt, FinancialPeriod.company_id, user)
        if company_id is not None:
            stmt = stmt.where(FinancialPeriod.company_id == company_id)
        if year is not None:
            stmt = stmt.where(FinancialPeriod.period_year == year)
        if status is not None:
            # Filter to periods that have at least one version in this status.
            stmt = stmt.where(
                FinancialPeriod.id.in_(
                    select(FinancialSummaryVersion.period_id).where(
                        FinancialSummaryVersion.status == status
                    )
                )
            )
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user: User, period_id: int) -> FinancialPeriod | None:
        stmt = select(FinancialPeriod).where(FinancialPeriod.id == period_id)
        stmt = _apply_company_scope(stmt, FinancialPeriod.company_id, user)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_company_period(
        self, company_id: int, year: int, month: int
    ) -> FinancialPeriod | None:
        return self.db.execute(
            select(FinancialPeriod).where(
                FinancialPeriod.company_id == company_id,
                FinancialPeriod.period_year == year,
                FinancialPeriod.period_month == month,
            )
        ).scalar_one_or_none()


class FinancialVersionRepository:
    """Company-scoped access to individual summary versions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_user(self, user: User, version_id: int) -> FinancialSummaryVersion | None:
        stmt = select(FinancialSummaryVersion).where(
            FinancialSummaryVersion.id == version_id
        )
        stmt = _apply_company_scope(stmt, FinancialSummaryVersion.company_id, user)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_period(self, period_id: int) -> list[FinancialSummaryVersion]:
        stmt = (
            select(FinancialSummaryVersion)
            .where(FinancialSummaryVersion.period_id == period_id)
            .order_by(FinancialSummaryVersion.version_number.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def latest_number(self, period_id: int) -> int:
        value = self.db.execute(
            select(func.max(FinancialSummaryVersion.version_number)).where(
                FinancialSummaryVersion.period_id == period_id
            )
        ).scalar_one()
        return int(value or 0)

    def pending_for_user(self, user: User) -> list[FinancialSummaryVersion]:
        """Versions awaiting an accountant decision, within the caller's scope."""
        stmt = (
            select(FinancialSummaryVersion)
            .where(
                FinancialSummaryVersion.status.in_(
                    [
                        FinancialSummaryStatus.SUBMITTED.value,
                        FinancialSummaryStatus.CORRECTION_REQUIRED.value,
                    ]
                )
            )
            .order_by(FinancialSummaryVersion.submitted_at.asc())
        )
        stmt = _apply_company_scope(stmt, FinancialSummaryVersion.company_id, user)
        return list(self.db.execute(stmt).scalars())
