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
    AuditLog,
    Company,
    MonthlyReport,
    SupportRequest,
    User,
    UserCompanyAccess,
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
        for model in (
            AIMessage,
            AIConversation,
            AuditLog,
            SupportRequest,
            MonthlyReport,
            UserCompanyAccess,
            Company,
            User,
        ):
            db.query(model).delete()
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
