"""Development/demo seed.

This script is the *only* place demo data is created, and it refuses to run
against a production database unless explicitly forced. Production starts from
an empty database: run ``alembic upgrade head`` and nothing else.

Usage::

    python -m scripts.seed_demo --reset

Every demo account uses the password ``SafirDemo!2027`` and is clearly marked
as demo data so it can never be mistaken for a real holding.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.core.config import settings  # noqa: E402
from backend.db.base import utcnow  # noqa: E402
from backend.db.models.enums import (  # noqa: E402
    CompanyHealth,
    ReportStatus,
    SupportCategory,
    SupportStatus,
)
from backend.db.models.identity import Company, Role, User, UserCompanyAccess  # noqa: E402
from backend.db.models.report import MonthlyReport  # noqa: E402
from backend.db.models.support import SupportRequest  # noqa: E402
from backend.db.session import session_scope  # noqa: E402
from backend.services.auth_service import create_user  # noqa: E402
from backend.services.rbac_service import bootstrap_rbac  # noqa: E402

DEMO_PASSWORD = "SafirDemo!2027"
DEMO_EMAIL_DOMAIN = "demo.safir.local"

COMPANIES = [
    ("SAF-TECH", "السفير للتقنية", "Safir Technology", "Technology", CompanyHealth.STRONG),
    ("SAF-REAL", "السفير للعقار", "Safir Real Estate", "Real Estate", CompanyHealth.STABLE),
    ("SAF-MFG", "السفير للتصنيع", "Safir Manufacturing", "Industrial", CompanyHealth.WATCH),
    ("SAF-RET", "السفير للتجزئة", "Safir Retail", "Retail", CompanyHealth.STRONG),
    ("SAF-LOG", "السفير للخدمات اللوجستية", "Safir Logistics", "Logistics", CompanyHealth.STABLE),
    ("SAF-HLT", "السفير للرعاية الصحية", "Safir Healthcare", "Healthcare", CompanyHealth.ATTENTION),
]

# (company_code, revenue, expenses, net, receivables, status, problems)
REPORTS_2027_10 = [
    ("SAF-TECH", "4820000", "3110000", "1710000", "420000", ReportStatus.REVIEWED, None),
    ("SAF-REAL", "3150000", "2240000", "910000", "980000", ReportStatus.SUBMITTED, None),
    ("SAF-MFG", "2760000", "2580000", "180000", "1340000", ReportStatus.SUBMITTED,
     "ارتفاع تكاليف المواد الخام وتأخر التوريد"),
    ("SAF-RET", "1980000", "1290000", "690000", "150000", ReportStatus.REVIEWED, None),
    ("SAF-LOG", "1420000", "1180000", "240000", "310000", ReportStatus.UNDER_REVIEW, None),
    # SAF-HLT intentionally has no report -- it appears in "missing reports".
]

SUPPORT_REQUESTS = [
    ("SAF-TECH", "طلب تطوير خطة التوسع الإقليمي", SupportCategory.BUSINESS_DEVELOPMENT,
     SupportStatus.IN_PROGRESS),
    ("SAF-REAL", "حملة تسويقية لمشروع الواجهة البحرية", SupportCategory.MARKETING,
     SupportStatus.NEW),
    ("SAF-MFG", "مراجعة الهيكل المالي والتكاليف", SupportCategory.ACCOUNTING,
     SupportStatus.NEW),
    ("SAF-RET", "هوية بصرية لفرع جديد", SupportCategory.DESIGN, SupportStatus.COMPLETED),
    ("SAF-LOG", "دعم في إعداد نموذج تسعير", SupportCategory.GENERAL, SupportStatus.NEW),
]


def _reset(db) -> None:
    """Delete demo rows only -- identified by the demo email domain."""
    demo_users = list(
        db.execute(select(User).where(User.email.like(f"%@{DEMO_EMAIL_DOMAIN}"))).scalars()
    )
    for user in demo_users:
        db.delete(user)
    for company in db.execute(select(Company)).scalars():
        db.delete(company)
    db.commit()
    print(f"  removed {len(demo_users)} demo users and all companies")


def seed(reset: bool) -> None:
    if settings.is_production:
        raise SystemExit(
            "Refusing to seed demo data into a production database. "
            "Set APP_ENV to development/test, or pass --force to override."
        )

    with session_scope() as db:
        bootstrap_rbac(db)
        print("  RBAC catalogue synced")

        if reset:
            _reset(db)

        # ---- companies ----
        companies: dict[str, Company] = {}
        for code, name_ar, name_en, sector, health in COMPANIES:
            existing = db.execute(
                select(Company).where(Company.code == code)
            ).scalar_one_or_none()
            if existing is None:
                existing = Company(
                    code=code,
                    name_ar=name_ar,
                    name_en=name_en,
                    sector=sector,
                    health=health.value,
                    contact_email=f"{code.lower()}@{DEMO_EMAIL_DOMAIN}",
                )
                db.add(existing)
                db.flush()
            companies[code] = existing
        db.commit()
        print(f"  {len(companies)} companies")

        # ---- users ----
        def ensure_user(email, name_ar, name_en, role_code, company_codes=(), write=True):
            existing = db.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            user = create_user(
                db,
                email=email,
                password=DEMO_PASSWORD,
                full_name_ar=name_ar,
                full_name_en=name_en,
                role_code=role_code,
            )
            for code in company_codes:
                db.add(
                    UserCompanyAccess(
                        user_id=user.id,
                        company_id=companies[code].id,
                        can_read=True,
                        can_write=write,
                        is_primary=True,
                    )
                )
            db.commit()
            db.refresh(user)
            return user

        owner = ensure_user(
            f"owner@{DEMO_EMAIL_DOMAIN}", "عبدالله السفير", "Abdullah Al-Safir", "holding_owner"
        )
        manager = ensure_user(
            f"manager.tech@{DEMO_EMAIL_DOMAIN}", "مدير شركة التقنية", "Technology Manager",
            "company_manager", ("SAF-TECH",),
        )
        manager_hlt = ensure_user(
            f"manager.hlt@{DEMO_EMAIL_DOMAIN}", "مدير الرعاية الصحية", "Healthcare Manager",
            "company_manager", ("SAF-HLT",),
        )
        accountant = ensure_user(
            f"accountant@{DEMO_EMAIL_DOMAIN}", "المحاسب", "Group Accountant", "accountant"
        )
        ensure_user(
            f"bd@{DEMO_EMAIL_DOMAIN}", "تطوير الأعمال", "Business Development",
            "business_development",
        )
        ensure_user(f"marketing@{DEMO_EMAIL_DOMAIN}", "التسويق", "Marketing", "marketing")
        ensure_user(f"design@{DEMO_EMAIL_DOMAIN}", "التصميم", "Designer", "designer")
        print("  7 demo users (one per role, plus a second company manager)")

        # ---- monthly reports for October 2027 ----
        created_reports = 0
        for code, revenue, expenses, net, receivables, status, problems in REPORTS_2027_10:
            company = companies[code]
            exists = db.execute(
                select(MonthlyReport).where(
                    MonthlyReport.company_id == company.id,
                    MonthlyReport.period_year == 2027,
                    MonthlyReport.period_month == 10,
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(
                MonthlyReport(
                    company_id=company.id,
                    period_year=2027,
                    period_month=10,
                    status=status.value,
                    revenue=Decimal(revenue),
                    expenses=Decimal(expenses),
                    net_result=Decimal(net),
                    outstanding_receivables=Decimal(receivables),
                    major_problems=problems,
                    important_developments="توسع في قاعدة العملاء وتوقيع عقود جديدة.",
                    submitted_at=utcnow(),
                    submitted_by_id=manager.id,
                )
            )
            created_reports += 1
        db.commit()
        print(f"  {created_reports} monthly reports for 2027-10")

        # ---- support requests ----
        created_requests = 0
        for code, title, category, status in SUPPORT_REQUESTS:
            company = companies[code]
            exists = db.execute(
                select(SupportRequest).where(
                    SupportRequest.company_id == company.id,
                    SupportRequest.title == title,
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(
                SupportRequest(
                    company_id=company.id,
                    title=title,
                    description="طلب دعم تجريبي لأغراض التطوير.",
                    category=category.value,
                    status=status.value,
                    requested_by_id=manager.id,
                )
            )
            created_requests += 1
        db.commit()
        print(f"  {created_requests} support requests")

        print(
            "\nDemo seed complete.\n"
            f"  password for every demo account: {DEMO_PASSWORD}\n"
            f"  holding owner:   owner@{DEMO_EMAIL_DOMAIN}\n"
            f"  company manager: manager.tech@{DEMO_EMAIL_DOMAIN}\n"
            f"  accountant:      accountant@{DEMO_EMAIL_DOMAIN}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed development/demo data.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing demo data first."
    )
    parser.add_argument(
        "--force", action="store_true", help="Allow running with APP_ENV=production."
    )
    args = parser.parse_args()
    if args.force:
        settings.APP_ENV = "development"
    seed(reset=args.reset)
