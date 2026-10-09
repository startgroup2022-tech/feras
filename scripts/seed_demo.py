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
from backend.services.document_service import seed_default_categories  # noqa: E402
from backend.services.rbac_service import bootstrap_rbac  # noqa: E402

DEMO_PASSWORD = "SafirDemo!2027"
DEMO_EMAIL_DOMAIN = "demo.safir.local"

# Roles used when building the Phase-3 operations demo (forms, workflows,
# approvals, documents). Kept as codes so they match the RBAC catalogue.
OPS_FINANCE_ROLE = "accountant"
OPS_COMPANY_ROLE = "company_manager"

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

# September baseline so the dashboard can show real month-over-month change and
# per-company growth. Kept slightly lower than October to reflect growth.
REPORTS_2027_09 = [
    ("SAF-TECH", "4280000", "2900000", "1380000", "390000", ReportStatus.REVIEWED),
    ("SAF-REAL", "2990000", "2150000", "840000", "910000", ReportStatus.REVIEWED),
    ("SAF-MFG", "2850000", "2540000", "310000", "1280000", ReportStatus.REVIEWED),
    ("SAF-RET", "1890000", "1250000", "640000", "140000", ReportStatus.REVIEWED),
    ("SAF-LOG", "1290000", "1100000", "190000", "280000", ReportStatus.REVIEWED),
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
    from backend.db.models.documents import Document
    from backend.db.models.forms import DynamicForm
    from backend.db.models.submissions import FormSubmission
    from backend.db.models.workflows import WorkflowDefinition

    demo_users = list(
        db.execute(select(User).where(User.email.like(f"%@{DEMO_EMAIL_DOMAIN}"))).scalars()
    )
    # Operations rows are holding-scoped and not company-cascaded, so purge
    # them explicitly before the users/companies they reference disappear.
    db.query(Document).delete()
    db.query(FormSubmission).delete()
    db.query(WorkflowDefinition).delete()
    db.query(DynamicForm).delete()
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

        seed_default_categories(db)
        print("  document categories synced")

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
        manager_real = ensure_user(
            f"manager.real@{DEMO_EMAIL_DOMAIN}", "مدير شركة العقار", "Real Estate Manager",
            "company_manager", ("SAF-REAL",),
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
        print("  8 demo users (one per role, plus two company managers)")

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

        # ---- September baseline reports (for month-over-month) ----
        created_prev = 0
        for code, revenue, expenses, net, receivables, status in REPORTS_2027_09:
            company = companies[code]
            exists = db.execute(
                select(MonthlyReport).where(
                    MonthlyReport.company_id == company.id,
                    MonthlyReport.period_year == 2027,
                    MonthlyReport.period_month == 9,
                )
            ).scalar_one_or_none()
            if exists:
                continue
            db.add(
                MonthlyReport(
                    company_id=company.id,
                    period_year=2027,
                    period_month=9,
                    status=status.value,
                    revenue=Decimal(revenue),
                    expenses=Decimal(expenses),
                    net_result=Decimal(net),
                    outstanding_receivables=Decimal(receivables),
                    submitted_at=utcnow(),
                    submitted_by_id=manager.id,
                )
            )
            created_prev += 1
        db.commit()
        print(f"  {created_prev} monthly reports for 2027-09 (baseline)")

        # ---- one demo attachment (a tiny PDF) on the reviewed Tech report ----
        tech_report = db.execute(
            select(MonthlyReport).where(
                MonthlyReport.company_id == companies["SAF-TECH"].id,
                MonthlyReport.period_year == 2027,
                MonthlyReport.period_month == 10,
            )
        ).scalar_one_or_none()
        if tech_report is not None and not tech_report.attachments:
            from backend.core import storage
            from backend.db.models.report import MonthlyReportAttachment

            payload = b"%PDF-1.4\n% Safir demo monthly financial pack\n"
            key = storage.store_bytes(data=payload, extension=".pdf")
            db.add(
                MonthlyReportAttachment(
                    report_id=tech_report.id,
                    original_filename="Safir-Tech-2027-10.pdf",
                    storage_key=key,
                    content_type="application/pdf",
                    size_bytes=len(payload),
                    uploaded_by_id=owner.id,
                )
            )
            db.commit()
            print("  1 demo attachment on SAF-TECH report")

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

        # ---- Phase 3 operations demo: forms, workflows, submissions,
        #      approvals and documents -------------------------------------
        _seed_operations(
            db,
            companies=companies,
            owner=owner,
            tech_manager=manager,
            real_manager=manager_real,
            accountant=accountant,
        )

        print(
            "\nDemo seed complete.\n"
            f"  password for every demo account: {DEMO_PASSWORD}\n"
            f"  holding owner:   owner@{DEMO_EMAIL_DOMAIN}\n"
            f"  company manager: manager.tech@{DEMO_EMAIL_DOMAIN}\n"
            f"  accountant:      accountant@{DEMO_EMAIL_DOMAIN}"
        )


def _seed_operations(
    db,
    *,
    companies,
    owner,
    tech_manager,
    real_manager,
    accountant,
):
    """Seed the Phase-3 dynamic platform via the real services.

    Going through the services (rather than inserting rows directly) keeps the
    demo consistent with what the running app can actually do: published forms
    with fields and requirements, a two-step workflow, live submissions routed
    into approvals, an approved request, an incomplete one, and documents.
    """
    from backend.services import (
        document_service,
        form_service,
        requirement_service,
        submission_service,
        workflow_service,
    )
    from backend.db.models.documents import DocumentCategory
    from backend.db.models.forms import DynamicForm
    from datetime import date, timedelta

    # Idempotent: re-running the seed without --reset must not duplicate the
    # operations demo.
    if db.execute(
        select(DynamicForm).where(DynamicForm.code == "capex_request")
    ).scalar_one_or_none() is not None:
        print("  operations demo already present (skipped)")
        return

    # A holding-wide form every subsidiary can submit.
    capex = form_service.create_form(
        db,
        actor=owner,
        payload={
            "code": "capex_request",
            "name_ar": "طلب مصروف رأسمالي",
            "name_en": "Capital Expenditure Request",
            "description_ar": "نموذج موحّد لطلبات المصروفات الرأسمالية.",
            "description_en": "Group-wide capital expenditure request form.",
            "scope": "holding",
        },
    )
    form_service.add_field(
        db,
        actor=owner,
        form_id=capex["id"],
        payload={
            "key": "amount",
            "field_type": "decimal",
            "label_ar": "المبلغ التقديري",
            "label_en": "Estimated amount",
            "is_required": True,
            "config": {"min": 0},
        },
    )
    form_service.add_field(
        db,
        actor=owner,
        form_id=capex["id"],
        payload={
            "key": "purpose",
            "field_type": "long_text",
            "label_ar": "الغرض من الطلب",
            "label_en": "Purpose of the request",
            "is_required": True,
        },
    )
    form_service.add_field(
        db,
        actor=owner,
        form_id=capex["id"],
        payload={
            "key": "priority",
            "field_type": "select",
            "label_ar": "الأولوية",
            "label_en": "Priority",
            "is_required": True,
            "config": {
                "options": [
                    {"value": "low", "label_ar": "منخفضة", "label_en": "Low"},
                    {"value": "normal", "label_ar": "عادية", "label_en": "Normal"},
                    {"value": "high", "label_ar": "عالية", "label_en": "High"},
                ]
            },
        },
    )
    requirement_service.add_requirement(
        db,
        actor=owner,
        form_id=capex["id"],
        payload={
            "key": "quotation",
            "name_ar": "عرض سعر",
            "name_en": "Quotation",
            "requirement_type": "document",
            "is_mandatory": True,
            "config": {"min_count": 1},
        },
    )
    form_service.publish_form(db, actor=owner, form_id=capex["id"])

    workflow = workflow_service.create_workflow(
        db,
        actor=owner,
        payload={
            "code": "capex_flow",
            "name_ar": "مسار اعتماد المصروف الرأسمالي",
            "name_en": "Capital Expenditure Approval Flow",
            "form_id": capex["id"],
            "scope": "holding",
        },
    )
    workflow_service.add_step(
        db,
        actor=owner,
        workflow_id=workflow["id"],
        payload={
            "key": "company_manager",
            "name_ar": "مدير الشركة",
            "name_en": "Company Manager",
            "assignment_type": "company_manager",
        },
    )
    workflow_service.add_step(
        db,
        actor=owner,
        workflow_id=workflow["id"],
        payload={
            "key": "finance_review",
            "name_ar": "المراجعة المالية",
            "name_en": "Finance Review",
            "assignment_type": "role",
            "assignment_config": {"role_code": OPS_FINANCE_ROLE},
        },
    )
    workflow_service.publish_workflow(db, actor=owner, workflow_id=workflow["id"])
    print("  1 published form + 1 published workflow (capex)")

    # -- live submissions -------------------------------------------------
    # (a) SAF-TECH approved all the way through; the document satisfies the
    #     mandatory quotation requirement, so it routes into approvals.
    tech = companies["SAF-TECH"]
    approved = submission_service.create_submission(
        db,
        actor=tech_manager,
        payload={
            "form_id": capex["id"],
            "company_id": tech.id,
            "title": "طلب مصروف رأسمالي — توسعة مركز البيانات",
            "values": {
                "amount": "1850000",
                "purpose": "توسعة مركز البيانات وترقية البنية التحتية.",
                "priority": "high",
            },
        },
    )
    _attach_requirement_document(
        db, submission=approved, actor=tech_manager, filename="عرض-سعر-التوسعة.pdf"
    )
    submission_service.submit_submission(
        db, actor=tech_manager, submission_id=approved.id
    )

    # (b) SAF-REAL left incomplete: submitted with the mandatory quotation
    #     missing, which surfaces it in the "needs attention" queue.
    real = companies["SAF-REAL"]
    incomplete = submission_service.create_submission(
        db,
        actor=real_manager,
        payload={
            "form_id": capex["id"],
            "company_id": real.id,
            "title": "طلب مصروف رأسمالي — تحديث المعرض",
            "values": {
                "amount": "640000",
                "purpose": "تحديث صالة العرض الرئيسية.",
                "priority": "normal",
            },
        },
    )
    # Missing the mandatory quotation: the service records the request as
    # "incomplete" and raises, which is the intended demo state.
    from backend.core.errors import ConflictError

    try:
        submission_service.submit_submission(
            db, actor=real_manager, submission_id=incomplete.id
        )
    except ConflictError:
        pass
    print("  2 form submissions (submitted + incomplete)")

    # -- approve the SAF-TECH request through both workflow steps ---------
    from backend.db.models.enums import TaskStatus
    from backend.db.models.workflows import WorkflowInstance, ApprovalTask

    instance = db.execute(
        select(WorkflowInstance).where(WorkflowInstance.submission_id == approved.id)
    ).scalar_one_or_none()
    if instance is not None:
        # Step 1: company manager.
        pending = db.execute(
            select(ApprovalTask)
            .where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
            .order_by(ApprovalTask.step_order)
        ).scalars().all()
        first = first_of(pending, lambda t: t.assignee_id == tech_manager.id)
        if first is not None:
            _act(db, actor=tech_manager, task_id=first.id, decision="approve",
                 comment="معتمد على مستوى الشركة.")
        # Step 2: finance review (the accountant holds the role).
        pending = db.execute(
            select(ApprovalTask)
            .where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
        ).scalars().all()
        second = first_of(pending, lambda t: t.assignee_id == accountant.id)
        if second is not None:
            _act(db, actor=accountant, task_id=second.id, decision="approve",
                 comment="المراجعة المالية سليمة.")
    print("  1 request fully approved (2 steps)")

    # (c) A second SAF-TECH request left mid-flow: the company manager has
    #     approved, so it now waits in the group accountant's approval queue.
    pending_sub = submission_service.create_submission(
        db,
        actor=tech_manager,
        payload={
            "form_id": capex["id"],
            "company_id": tech.id,
            "title": "طلب مصروف رأسمالي — منصة الذكاء الاصطناعي",
            "values": {
                "amount": "920000",
                "purpose": "بناء منصة تحليلات ذكية للمجموعة.",
                "priority": "normal",
            },
        },
    )
    _attach_requirement_document(
        db, submission=pending_sub, actor=tech_manager, filename="عرض-سعر-المنصة.pdf"
    )
    submission_service.submit_submission(
        db, actor=tech_manager, submission_id=pending_sub.id
    )
    pending_instance = db.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.submission_id == pending_sub.id
        )
    ).scalar_one_or_none()
    if pending_instance is not None:
        step_one = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == pending_instance.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
                ApprovalTask.assignee_id == tech_manager.id,
            )
        ).scalars().first()
        if step_one is not None:
            _act(db, actor=tech_manager, task_id=step_one.id, decision="approve",
                 comment="معتمد، بانتظار المراجعة المالية.")
    print("  1 request awaiting finance approval (in the accountant's queue)")

    # -- documents --------------------------------------------------------
    category = db.execute(
        select(DocumentCategory).where(DocumentCategory.code == "commercial_registration")
    ).scalar_one_or_none()
    from datetime import date, timedelta

    pdf = b"%PDF-1.4\n% Safir demo operations document\n"
    document_service.upload_document(
        db,
        actor=tech_manager,
        company_id=tech.id,
        filename="السجل-التجاري.pdf",
        content_type="application/pdf",
        data=pdf,
        category_id=category.id if category else None,
        title_ar="السجل التجاري — السفير للتقنية",
        title_en="Commercial Registration — Safir Technology",
        expiry_date=date.today() + timedelta(days=20),
    )
    print("  1 registered document (expiring soon)")


def _act(db, *, actor, task_id, decision, comment=None):
    from backend.services import approval_service

    approval_service.act(
        db, actor=actor, task_id=task_id, decision=decision, comment=comment
    )


def _attach_requirement_document(db, *, submission, actor, filename):
    """Upload a document and satisfy the submission's mandatory document
    requirement, mirroring what the UI does when a company attaches its file."""
    from backend.db.models.submissions import SubmissionRequirement
    from backend.services import document_service

    requirement = db.execute(
        select(SubmissionRequirement).where(
            SubmissionRequirement.submission_id == submission.id,
            SubmissionRequirement.requirement_type == "document",
        )
    ).scalars().first()
    if requirement is None:
        return
    pdf = b"%PDF-1.4\n% Safir demo quotation attachment\n"
    document_service.upload_document(
        db,
        actor=actor,
        company_id=submission.company_id,
        filename=filename,
        content_type="application/pdf",
        data=pdf,
        title_ar="عرض سعر مرفق",
        title_en="Attached quotation",
        submission_id=submission.id,
        submission_requirement_id=requirement.id,
    )



def first_of(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None



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
