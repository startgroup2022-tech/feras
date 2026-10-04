"""Shared pytest fixtures.

The suite runs against a temporary SQLite file created per test session. The
database URL is set *before* any application module is imported, because the
engine is constructed at import time.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

# Must happen before importing anything from ``backend``.
_TMP_DIR = tempfile.mkdtemp(prefix="safir-tests-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-in-production"
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.core.security import create_access_token  # noqa: E402
from backend.db.base import Base, utcnow  # noqa: E402
from backend.db.models import (  # noqa: E402
    AIConversation,
    AIMessage,
    ApprovalEvent,
    ApprovalTask,
    AuditLog,
    Company,
    Department,
    Document,
    DocumentCategory,
    DynamicForm,
    FormCompany,
    FormField,
    FormRequirement,
    FormSubmission,
    FormVersion,
    Holding,
    MonthlyReport,
    Notification,
    Ownership,
    SubmissionRequirement,
    SupportRequest,
    User,
    UserCompanyAccess,
    WebhookDelivery,
    WebhookEndpoint,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowVersion,
)

from backend.db.models.enums import (  # noqa: E402
    CompanyHealth,
    ReportStatus,
    SupportCategory,
    SupportStatus,
)
from backend.db.session import SessionLocal, engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.services.auth_service import create_user  # noqa: E402
from backend.services.rbac_service import bootstrap_rbac  # noqa: E402

PASSWORD = "TestPass!2027"
YEAR, MONTH = 2027, 10


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap_rbac(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_data(_database):
    """Remove all business rows before each test, keeping the RBAC catalogue."""
    with SessionLocal() as db:
        # Order matters: children before parents. ``users`` must be cleared
        # before ``departments`` (which references a manager), and departments
        # before companies. Custom roles created by a test are removed too;
        # the bootstrap catalogue is re-synced just after.
        for model in (
            WebhookDelivery,
            WebhookEndpoint,
            Notification,
            ApprovalEvent,
            ApprovalTask,
            WorkflowInstance,
            SubmissionRequirement,
            Document,
            FormSubmission,
            WorkflowStep,
            WorkflowVersion,
            WorkflowDefinition,
            FormRequirement,
            FormField,
            FormVersion,
            FormCompany,
            DynamicForm,
            DocumentCategory,
            AIMessage,
            AIConversation,
            AuditLog,
            SupportRequest,
            MonthlyReport,
            UserCompanyAccess,
            Ownership,
            User,
            Department,
            Holding,
            Company,
        ):
            db.query(model).delete()
        db.flush()
        bootstrap_rbac(db)

        # A test may have created a custom role; drop those so the catalogue is
        # exactly the code-defined set before the next test.
        from backend.db.models.identity import Role
        from backend.rbac.permissions import ROLE_DEFINITIONS

        system_codes = {d["code"] for d in ROLE_DEFINITIONS}
        for role in db.query(Role).all():
            if role.code not in system_codes:
                db.delete(role)
        db.commit()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --------------------------------------------------------------------------
# data builders
# --------------------------------------------------------------------------
@pytest.fixture
def make_company(db):
    def _make(code: str, name_ar: str, health: str = CompanyHealth.STABLE.value) -> Company:
        company = Company(
            code=code, name_ar=name_ar, name_en=code, sector="Test", health=health
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        return company

    return _make


@pytest.fixture
def make_user(db):
    def _make(
        email: str,
        role_code: str,
        companies: list[Company] | None = None,
        can_write: bool = True,
    ) -> User:
        user = create_user(
            db,
            email=email,
            password=PASSWORD,
            full_name_ar=f"مستخدم {email}",
            full_name_en=None,
            role_code=role_code,
        )
        for company in companies or []:
            db.add(
                UserCompanyAccess(
                    user_id=user.id,
                    company_id=company.id,
                    can_read=True,
                    can_write=can_write,
                    is_primary=True,
                )
            )
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def make_report(db):
    def _make(
        company: Company,
        revenue: str = "1000000",
        expenses: str = "600000",
        net: str = "400000",
        status: str = ReportStatus.SUBMITTED.value,
        major_problems: str | None = None,
    ) -> MonthlyReport:
        report = MonthlyReport(
            company_id=company.id,
            period_year=YEAR,
            period_month=MONTH,
            status=status,
            revenue=Decimal(revenue),
            expenses=Decimal(expenses),
            net_result=Decimal(net),
            major_problems=major_problems,
            submitted_at=utcnow() if status != ReportStatus.DRAFT.value else None,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    return _make


@pytest.fixture
def make_request(db):
    def _make(
        company: Company,
        requested_by: User,
        category: str = SupportCategory.GENERAL.value,
        status: str = SupportStatus.NEW.value,
    ) -> SupportRequest:
        request = SupportRequest(
            company_id=company.id,
            title="طلب دعم تجريبي",
            category=category,
            status=status,
            requested_by_id=requested_by.id,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request

    return _make


@pytest.fixture
def world(db, make_company, make_user, make_report, make_request):
    """Two companies, each with a manager, a report and a support request.

    Shared by several test modules so isolation assertions all reason about the
    same shape of data.
    """
    alpha = make_company("ALPHA", "شركة ألفا", health=CompanyHealth.STRONG.value)
    beta = make_company("BETA", "شركة بيتا", health=CompanyHealth.STABLE.value)

    alpha_mgr = make_user("alpha@corp.sa", "company_manager", [alpha])
    beta_mgr = make_user("beta@corp.sa", "company_manager", [beta])
    owner = make_user("owner@corp.sa", "holding_owner")
    accountant = make_user("acc@corp.sa", "accountant")

    alpha_report = make_report(alpha, revenue="111111", expenses="1", net="111110")
    beta_report = make_report(beta, revenue="999999", expenses="1", net="999998")
    alpha_req = make_request(alpha, alpha_mgr)
    beta_req = make_request(beta, beta_mgr)

    return dict(
        alpha=alpha,
        beta=beta,
        alpha_mgr=alpha_mgr,
        beta_mgr=beta_mgr,
        owner=owner,
        accountant=accountant,
        alpha_report=alpha_report,
        beta_report=beta_report,
        alpha_req=alpha_req,
        beta_req=beta_req,
    )


# --------------------------------------------------------------------------
# auth helpers
# --------------------------------------------------------------------------
@pytest.fixture
def auth():
    """Return an ``Authorization`` header dict for a user."""

    def _auth(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return _auth


@pytest.fixture
def login(client):
    def _login(email: str, password: str = PASSWORD) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


# --------------------------------------------------------------------------
# Phase 3: dynamic operations platform world
# --------------------------------------------------------------------------
@pytest.fixture
def ops_world(db, make_company, make_user):
    """Two companies, an owner, company managers, finance manager, a published
    holding-wide form and a two-step workflow. Tests build on this."""
    from backend.db.models.enums import (
        AssignmentType,
        FieldType,
        FormScope,
        FormStatus,
        RequirementType,
        WorkflowStatus,
    )
    from backend.db.models.forms import (
        DynamicForm,
        FormField,
        FormRequirement,
        FormVersion,
    )
    from backend.db.models.workflows import (
        WorkflowDefinition,
        WorkflowStep,
        WorkflowVersion,
    )

    alpha = make_company("ALPHA", "شركة ألفا")
    beta = make_company("BETA", "شركة بيتا")
    # A third company used by document tests, so the extra builder account does
    # not participate in the approval workflow's company-manager resolution.
    gamma = make_company("GAMMA", "شركة غاما")

    owner = make_user("owner2@corp.sa", "holding_owner")
    alpha_mgr = make_user("am@corp.sa", "company_manager", [alpha])
    gamma_owner = make_user("go@corp.sa", "company_owner", [gamma])
    beta_mgr = make_user("bm@corp.sa", "company_manager", [beta])
    finance = make_user("fin@corp.sa", "finance_manager")

    form = DynamicForm(
        code="capex",
        name_ar="طلب مصروف رأسمالي",
        name_en="Capital Expenditure Request",
        scope=FormScope.HOLDING.value,
        status=FormStatus.DRAFT.value,
        created_by_id=owner.id,
    )
    db.add(form)
    db.flush()
    version = FormVersion(
        form_id=form.id,
        version_number=1,
        status=FormStatus.DRAFT.value,
        created_by_id=owner.id,
    )
    db.add(version)
    db.flush()
    db.add(
        FormField(
            form_version_id=version.id,
            key="amount",
            field_type=FieldType.DECIMAL.value,
            label_ar="المبلغ",
            label_en="Amount",
            is_required=True,
            display_order=1,
        )
    )
    db.add(
        FormField(
            form_version_id=version.id,
            key="purpose",
            field_type=FieldType.SHORT_TEXT.value,
            label_ar="الغرض",
            label_en="Purpose",
            is_required=True,
            display_order=2,
        )
    )
    db.add(
        FormRequirement(
            form_version_id=version.id,
            key="quote",
            name_ar="عرض سعر",
            name_en="Quotation",
            requirement_type=RequirementType.DOCUMENT.value,
            is_mandatory=True,
            display_order=1,
            config={"min_count": 1},
        )
    )
    db.commit()
    db.refresh(form)

    workflow = WorkflowDefinition(
        code="capex_flow",
        name_ar="مسار المصروف الرأسمالي",
        name_en="Capex Flow",
        form_id=form.id,
        scope=FormScope.HOLDING.value,
        status=WorkflowStatus.DRAFT.value,
        allow_requirement_override=False,
        created_by_id=owner.id,
    )
    db.add(workflow)
    db.flush()
    wf_version = WorkflowVersion(
        definition_id=workflow.id,
        version_number=1,
        status=WorkflowStatus.DRAFT.value,
        created_by_id=owner.id,
    )
    db.add(wf_version)
    db.flush()
    db.add(
        WorkflowStep(
            workflow_version_id=wf_version.id,
            key="manager",
            name_ar="مدير الشركة",
            name_en="Company Manager",
            display_order=1,
            assignment_type=AssignmentType.COMPANY_MANAGER.value,
            assignment_config={},
        )
    )
    db.add(
        WorkflowStep(
            workflow_version_id=wf_version.id,
            key="finance",
            name_ar="المدير المالي",
            name_en="Finance Manager",
            display_order=2,
            assignment_type=AssignmentType.ROLE.value,
            assignment_config={"role_code": "finance_manager"},
        )
    )
    db.commit()

    return {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "owner": owner,
        "alpha_mgr": alpha_mgr,
        "gamma_owner": gamma_owner,
        "beta_mgr": beta_mgr,
        "finance": finance,
        "form": form,
        "version": version,
        "workflow": workflow,
        "wf_version": wf_version,
    }
