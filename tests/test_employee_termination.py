"""S11 / AC-11 -- terminating a Holding employee never bypasses the owner.

The specification separates the two authorities: a subsidiary manager may
terminate *their own* employees, but terminating a Holding employee must go
through the owner. Business development never edits a subsidiary salary, adding
an employee never mints a login, and -- the rule exercised here -- a manager
cannot terminate a Holding employee even when they hold a write grant on the
Holding company row.
"""

from __future__ import annotations

import pytest

from backend.db.models.enums import CompanyType, EmployeeStatus
from backend.db.models.identity import Company
from backend.services import hr_service


@pytest.fixture
def hr_world(db, make_company, make_user):
    """A subsidiary, a holding company, a manager with write on both, an owner."""
    subsidiary = make_company("SUB", "شركة تابعة")
    holding = Company(code="HOLD", name_ar="القابضة", name_en="Holding",
                      company_type=CompanyType.HOLDING.value)
    db.add(holding)
    db.commit()
    db.refresh(holding)

    manager = make_user("mgr.hr@corp.sa", "company_manager", [subsidiary, holding])
    owner = make_user("owner.hr@corp.sa", "holding_owner", [subsidiary, holding])
    return dict(subsidiary=subsidiary, holding=holding, manager=manager, owner=owner)


def _make_employee(db, user, company):
    return hr_service.create_employee(
        db, user=user, company_id=company.id, full_name_ar="موظف تجريبي"
    )


def test_manager_may_terminate_a_subsidiary_employee(client, hr_world, auth, db):
    employee = _make_employee(db, hr_world["owner"], hr_world["subsidiary"])

    r = client.patch(
        f"/api/v1/employees/{employee.id}",
        json={"status": "terminated"},
        headers=auth(hr_world["manager"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == EmployeeStatus.TERMINATED.value
    db.refresh(employee)
    assert employee.status == EmployeeStatus.TERMINATED.value


def test_manager_cannot_terminate_a_holding_employee(client, hr_world, auth, db):
    """AC-11: terminating a Holding employee never bypasses the owner."""
    employee = _make_employee(db, hr_world["owner"], hr_world["holding"])

    r = client.patch(
        f"/api/v1/employees/{employee.id}",
        json={"status": "terminated"},
        headers=auth(hr_world["manager"]),
    )
    assert r.status_code == 403, r.text
    db.refresh(employee)
    assert employee.status != EmployeeStatus.TERMINATED.value


def test_owner_may_terminate_a_holding_employee(client, hr_world, auth, db):
    employee = _make_employee(db, hr_world["owner"], hr_world["holding"])

    r = client.patch(
        f"/api/v1/employees/{employee.id}",
        json={"status": "terminated"},
        headers=auth(hr_world["owner"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == EmployeeStatus.TERMINATED.value


def test_bd_never_edits_a_subsidiary_salary(client, hr_world, auth, db):
    """AC-11: business development cannot change a subsidiary employee's salary."""
    employee = _make_employee(db, hr_world["owner"], hr_world["subsidiary"])
    bd = _make_bd(db, hr_world["subsidiary"])

    r = client.patch(
        f"/api/v1/employees/{employee.id}",
        json={"base_salary": "99999"},
        headers=auth(bd),
    )
    assert r.status_code == 403


def test_creating_an_employee_mints_no_login(client, hr_world, auth, db):
    """AC-11: adding an employee does not create a platform login account."""
    from backend.db.models.identity import User

    before = db.query(User).count()
    r = client.post(
        "/api/v1/employees",
        json={"company_id": hr_world["subsidiary"].id, "full_name_ar": "موظف جديد"},
        headers=auth(hr_world["owner"]),
    )
    assert r.status_code == 201, r.text
    assert db.query(User).count() == before


def _make_bd(db, company):
    from backend.services.auth_service import create_user

    user = create_user(
        db,
        email="bd.hr@corp.sa",
        password="Passw0rd!23",
        full_name_ar="تطوير الأعمال",
        full_name_en=None,
        role_code="business_development",
    )
    db.commit()
    db.refresh(user)
    return user
