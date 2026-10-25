"""Support requests: routing, status transitions, comments, and visibility."""

from __future__ import annotations

import pytest

from backend.db.models.enums import SupportCategory, SupportStatus

BASE = "/api/v1/support-requests"


@pytest.fixture
def bd_user(db, make_user):
    return make_user("bd@corp.sa", "business_development")


# --------------------------------------------------------------------------
# creation and routing
# --------------------------------------------------------------------------
def test_manager_raises_a_request_for_its_company(client, world, auth):
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "title": "نحتاج دعم تسويقي",
            "description": "حملة إطلاق منتج جديد",
            "category": SupportCategory.MARKETING.value,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == SupportStatus.NEW.value
    assert body["company_id"] == world["alpha"].id


def test_manager_cannot_raise_a_request_for_another_company(client, world, auth):
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["beta"].id, "title": "طلب غير مصرح"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "category,department",
    [
        (SupportCategory.ACCOUNTING.value, "accountant"),
        (SupportCategory.BUSINESS_DEVELOPMENT.value, "business_development"),
        (SupportCategory.MARKETING.value, "marketing"),
        (SupportCategory.DESIGN.value, "designer"),
        (SupportCategory.GENERAL.value, "holding_owner"),
    ],
)
def test_category_routes_to_the_owning_department(client, world, auth, category, department):
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "title": "طلب", "category": category},
    )

    assert response.status_code == 201
    assert response.json()["responsible_department"] == department


def test_holding_departments_cannot_raise_requests(client, world, auth, bd_user):
    """Departments respond to subsidiaries; they do not raise requests."""
    response = client.post(
        BASE,
        headers=auth(bd_user),
        json={"company_id": world["alpha"].id, "title": "طلب داخلي"},
    )

    assert response.status_code == 403


def test_title_is_required(client, world, auth):
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "title": "x"},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# S16/AC-16: a new request reaches the specialist directly and informs BD
# --------------------------------------------------------------------------
def _inbox(db, user):
    from backend.db.models.notifications import Notification

    return (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id)
        .order_by(Notification.id)
        .all()
    )


def test_new_request_notifies_the_owning_specialist(client, world, auth, db, make_user):
    designer = make_user("designer.notify@corp.sa", "designer")

    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "title": "تصميم حملة",
            "category": SupportCategory.DESIGN.value,
        },
    )

    assert response.status_code == 201
    rows = _inbox(db, designer)
    assert len(rows) == 1
    assert rows[0].type == "support.assigned"
    assert rows[0].entity_type == "support_request"
    assert rows[0].entity_id == response.json()["id"]


def test_new_request_informs_bd_without_gating_it(client, world, auth, db, bd_user):
    """AC-16: BD is informed for visibility; the request is not pending BD approval."""
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "title": "تصميم حملة",
            "category": SupportCategory.DESIGN.value,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == SupportStatus.NEW.value
    rows = _inbox(db, bd_user)
    assert len(rows) == 1
    assert rows[0].type == "support.created"


def test_requester_is_not_notified_of_its_own_request(client, world, auth, db):
    """The subsidiary manager who raised the request is not notified of it."""
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "title": "طلب داخلي",
            "category": SupportCategory.MARKETING.value,
        },
    )

    assert response.status_code == 201
    assert _inbox(db, world["alpha_mgr"]) == []


# --------------------------------------------------------------------------
# visibility
# --------------------------------------------------------------------------
def test_manager_sees_only_its_company_requests(client, world, auth):
    response = client.get(BASE, headers=auth(world["alpha_mgr"]))

    assert response.status_code == 200
    assert [r["company_id"] for r in response.json()] == [world["alpha"].id]


def test_department_sees_all_requests(client, world, auth, bd_user):
    response = client.get(BASE, headers=auth(bd_user))

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_filter_by_status(client, world, auth, bd_user):
    response = client.get(f"{BASE}?status={SupportStatus.NEW.value}", headers=auth(bd_user))

    assert response.status_code == 200
    assert all(r["status"] == SupportStatus.NEW.value for r in response.json())


# --------------------------------------------------------------------------
# status transitions
# --------------------------------------------------------------------------
def test_department_advances_the_status(client, world, auth, bd_user):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=auth(bd_user),
        json={"status": SupportStatus.IN_PROGRESS.value},
    )

    assert response.status_code == 200
    assert response.json()["status"] == SupportStatus.IN_PROGRESS.value


def test_illegal_transition_is_rejected(client, world, auth, bd_user):
    """new -> completed is not an allowed step."""
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=auth(bd_user),
        json={"status": SupportStatus.COMPLETED.value},
    )

    assert response.status_code == 422


def test_closing_stamps_closed_at(client, world, auth, bd_user):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=auth(bd_user),
        json={"status": SupportStatus.CLOSED.value},
    )

    assert response.status_code == 200
    assert response.json()["closed_at"] is not None


def test_reopening_clears_closed_at(client, world, auth, bd_user):
    headers = auth(bd_user)
    client.patch(f"{BASE}/{world['alpha_req'].id}/status", headers=headers, json={"status": "closed"})

    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status", headers=headers, json={"status": "in_progress"}
    )

    assert response.status_code == 200
    assert response.json()["closed_at"] is None


def test_manager_cannot_change_status(client, world, auth):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=auth(world["alpha_mgr"]),
        json={"status": SupportStatus.IN_PROGRESS.value},
    )

    assert response.status_code == 403


def test_status_cannot_be_set_to_the_same_value(client, world, auth, bd_user):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=auth(bd_user),
        json={"status": SupportStatus.NEW.value},
    )

    assert response.status_code == 409


# --------------------------------------------------------------------------
# comments
# --------------------------------------------------------------------------
def test_manager_comments_on_its_own_request(client, world, auth):
    response = client.post(
        f"{BASE}/{world['alpha_req'].id}/comments",
        headers=auth(world["alpha_mgr"]),
        json={"body": "هل من مستجدات؟"},
    )

    assert response.status_code == 201
    assert response.json()["body"] == "هل من مستجدات؟"


def test_manager_cannot_comment_on_another_companys_request(client, world, auth):
    response = client.post(
        f"{BASE}/{world['beta_req'].id}/comments",
        headers=auth(world["alpha_mgr"]),
        json={"body": "تدخل غير مصرح"},
    )

    assert response.status_code == 404


def test_internal_comments_are_hidden_from_the_company(client, world, auth, bd_user):
    """An internal note must not be visible to the requesting subsidiary."""
    client.post(
        f"{BASE}/{world['alpha_req'].id}/comments",
        headers=auth(bd_user),
        json={"body": "ملاحظة داخلية", "is_internal": True},
    )
    client.post(
        f"{BASE}/{world['alpha_req'].id}/comments",
        headers=auth(bd_user),
        json={"body": "رد علني", "is_internal": False},
    )

    company_view = client.get(
        f"{BASE}/{world['alpha_req'].id}/comments", headers=auth(world["alpha_mgr"])
    ).json()
    staff_view = client.get(
        f"{BASE}/{world['alpha_req'].id}/comments", headers=auth(bd_user)
    ).json()

    assert [c["body"] for c in company_view] == ["رد علني"]
    assert {c["body"] for c in staff_view} == {"ملاحظة داخلية", "رد علني"}


def test_empty_comment_is_rejected(client, world, auth):
    response = client.post(
        f"{BASE}/{world['alpha_req'].id}/comments",
        headers=auth(world["alpha_mgr"]),
        json={"body": ""},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Phase 2: assignment
# --------------------------------------------------------------------------
def test_owner_assigns_a_request(client, world, auth):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/assign",
        headers=auth(world["owner"]),
        json={"assigned_to_id": world["owner"].id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["assigned_to_id"] == world["owner"].id


def test_manager_cannot_assign(client, world, auth):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/assign",
        headers=auth(world["alpha_mgr"]),
        json={"assigned_to_id": world["alpha_mgr"].id},
    )
    assert response.status_code == 403


def test_assign_to_unknown_user_is_rejected(client, world, auth):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/assign",
        headers=auth(world["owner"]),
        json={"assigned_to_id": 999999},
    )
    assert response.status_code == 422


def test_assignment_is_audited(client, world, auth, db):
    from backend.db.models.ai import AuditLog

    client.patch(
        f"{BASE}/{world['alpha_req'].id}/assign",
        headers=auth(world["owner"]),
        json={
            "assigned_to_id": world["owner"].id,
            "responsible_department": "business_development",
        },
    )
    assert "support_request.assigned" in [row.action for row in db.query(AuditLog).all()]


# --------------------------------------------------------------------------
# design metadata and external delivery (S16 Tables 48-49)
# --------------------------------------------------------------------------
def test_design_request_keeps_sizes_platform_and_reference(client, world, auth):
    response = client.post(
        BASE,
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "title": "تصميم هوية",
            "category": SupportCategory.DESIGN.value,
            "platform": "Instagram",
            "dimensions": "1080x1080",
            "reference_link": "https://example.com/ref",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["platform"] == "Instagram"
    assert body["dimensions"] == "1080x1080"
    assert body["reference_link"] == "https://example.com/ref"
    # No design file is required to raise the request.
    assert body["delivery_link"] is None


def test_delivery_records_an_external_link(client, world, auth, bd_user):
    headers = auth(bd_user)
    client.patch(
        f"{BASE}/{world['alpha_req'].id}/status",
        headers=headers,
        json={"status": SupportStatus.IN_PROGRESS.value},
    )
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/delivery",
        headers=headers,
        json={"delivery_link": "https://drive.example.com/handoff"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["delivery_link"] == "https://drive.example.com/handoff"
    assert response.json()["delivered_at"] is not None


def test_delivery_refused_before_work_starts(client, world, auth, bd_user):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/delivery",
        headers=auth(bd_user),
        json={"delivery_link": "https://drive.example.com/handoff"},
    )

    assert response.status_code == 422


def test_delivery_requires_the_status_permission(client, world, auth):
    response = client.patch(
        f"{BASE}/{world['alpha_req'].id}/delivery",
        headers=auth(world["alpha_mgr"]),
        json={"delivery_link": "https://drive.example.com/handoff"},
    )

    assert response.status_code == 403


def test_delivery_cannot_cross_company_scope(client, world, auth, bd_user):
    """A department actor cannot record delivery on a request it cannot see."""
    response = client.patch(
        f"{BASE}/999999/delivery",
        headers=auth(bd_user),
        json={"delivery_link": "https://drive.example.com/x"},
    )

    assert response.status_code == 404


def test_delivery_is_audited(client, world, auth, db, bd_user):
    from backend.db.models.ai import AuditLog

    headers = auth(bd_user)
    client.patch(
        f"{BASE}/{world['alpha_req'].id}/status", headers=headers, json={"status": "in_progress"}
    )
    client.patch(
        f"{BASE}/{world['alpha_req'].id}/delivery",
        headers=headers,
        json={"delivery_link": "https://drive.example.com/handoff"},
    )
    assert "support_request.delivered" in [row.action for row in db.query(AuditLog).all()]

