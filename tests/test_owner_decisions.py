"""S22 / AC-22 -- owner decisions, directives, and the archive trail.

The specification reserves *issuing* a decision or a binding directive to the
owner. Business development and the company manager can read the decisions that
concern them and a manager may reply to a directive, but neither may create or
re-target one. An archived (cancelled) decision is never deleted: its history
survives.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def decision_world(world, make_user):
    """The shared world plus a BD manager and a write-granted owner."""
    bd = make_user("bd.dec@corp.sa", "business_development")
    owner_all = make_user(
        "owner.dec@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    data = dict(world)
    data["bd"] = bd
    data["owner_all"] = owner_all
    return data


def _create(client, auth, user, **overrides):
    payload = {
        "number": "D-001",
        "title": "اعتماد خطة التوسع",
        "body": "توسيع النشاط إلى السوق الشرقية.",
        "company_id": None,
    }
    payload.update(overrides)
    return client.post(
        "/api/v1/operations/owner-decisions", json=payload, headers=auth(user)
    )


def test_owner_can_issue_a_decision(client, decision_world, auth):
    r = _create(client, auth, decision_world["owner_all"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["number"] == "D-001"
    assert body["status"] == "open"


def test_bd_cannot_issue_a_binding_directive(client, decision_world, auth):
    """AC-22: business development never issues a decision or a directive."""
    r = _create(client, auth, decision_world["bd"])
    assert r.status_code == 403


def test_company_manager_cannot_issue_a_binding_directive(client, decision_world, auth):
    r = _create(client, auth, decision_world["alpha_mgr"])
    assert r.status_code == 403


def test_owner_can_direct_a_subsidiary_company(client, decision_world, auth):
    """The owner issues a formal directive aimed at one company's manager."""
    r = _create(
        client,
        auth,
        decision_world["owner_all"],
        number="DIR-7",
        title="توجيه للشركة ألفا",
        company_id=decision_world["alpha"].id,
    )
    assert r.status_code == 201, r.text
    assert r.json()["company_id"] == decision_world["alpha"].id


def test_archiving_preserves_the_trail_and_deletes_nothing(
    client, decision_world, auth, db
):
    """AC-22: the archive keeps the record and its follow-up history."""
    from backend.db.models.operations import OwnerDecision, OwnerDecisionEvent

    created = _create(client, auth, decision_world["owner_all"])
    decision_id = created.json()["id"]

    progressed = client.patch(
        f"/api/v1/operations/owner-decisions/{decision_id}",
        json={"status": "in_progress", "follow_up_note": "بدأ التنفيذ."},
        headers=auth(decision_world["owner_all"]),
    )
    assert progressed.status_code == 200, progressed.text

    archived = client.patch(
        f"/api/v1/operations/owner-decisions/{decision_id}",
        json={"status": "cancelled", "follow_up_note": "أُرشف دون حذف."},
        headers=auth(decision_world["owner_all"]),
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "cancelled"

    # The record still exists and its full history is retained.
    assert db.get(OwnerDecision, decision_id) is not None
    events = (
        db.query(OwnerDecisionEvent)
        .filter(OwnerDecisionEvent.decision_id == decision_id)
        .all()
    )
    assert len(events) == 2
    assert archived.json()["history"]  # history is returned on the serialised row


def _create_for_executor(client, auth, owner, executor_id, **overrides):
    payload = {
        "number": "DIR-1",
        "title": "توجيه تنفيذي",
        "body": "نفّذ الخطة.",
        "company_id": None,
        "executor_user_id": executor_id,
    }
    payload.update(overrides)
    return client.post(
        "/api/v1/operations/owner-decisions", json=payload, headers=auth(owner)
    )


def test_executor_reply_records_follow_up_and_notifies_owner(
    client, decision_world, auth, db
):
    """S22: the person a directive names replies with an execution update."""
    from backend.db.models.notifications import Notification
    from backend.db.models.operations import OwnerDecisionEvent

    mgr = decision_world["alpha_mgr"]
    created = _create_for_executor(
        client, auth, decision_world["owner_all"], mgr.id
    )
    assert created.status_code == 201, created.text
    decision_id = created.json()["id"]
    assert created.json()["status"] == "open"

    reply = client.post(
        f"/api/v1/operations/owner-decisions/{decision_id}/respond",
        json={"note": "بدأ التنفيذ الفعلي."},
        headers=auth(mgr),
    )
    assert reply.status_code == 200, reply.text
    body = reply.json()
    # A reply advances an open decision but can never close it.
    assert body["status"] == "in_progress"

    events = (
        db.query(OwnerDecisionEvent)
        .filter(OwnerDecisionEvent.decision_id == decision_id)
        .all()
    )
    assert any("بدأ التنفيذ الفعلي." in (e.note or "") for e in events)

    # The owner is told; the reply does not silently disappear.
    notes = db.query(Notification).all()
    assert any(n.entity_type == "owner_decision" for n in notes)


def test_a_reply_cannot_close_a_decision(client, decision_world, auth):
    """Only the owner closes a decision; a reply never reaches ``done``."""
    mgr = decision_world["alpha_mgr"]
    decision_id = _create_for_executor(
        client, auth, decision_world["owner_all"], mgr.id
    ).json()["id"]

    reply = client.post(
        f"/api/v1/operations/owner-decisions/{decision_id}/respond",
        json={"note": "انتهى العمل."},
        headers=auth(mgr),
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["status"] in {"open", "in_progress"}


def test_a_non_executor_cannot_reply_and_cannot_learn_it_exists(
    client, decision_world, auth
):
    """Isolation: a stranger gets 404, never a hint that the decision exists."""
    mgr = decision_world["alpha_mgr"]
    decision_id = _create_for_executor(
        client, auth, decision_world["owner_all"], mgr.id
    ).json()["id"]

    r = client.post(
        f"/api/v1/operations/owner-decisions/{decision_id}/respond",
        json={"note": "محاولة غير مصرح بها."},
        headers=auth(decision_world["beta_mgr"]),
    )
    assert r.status_code == 404


def test_a_reply_requires_a_note(client, decision_world, auth):
    mgr = decision_world["alpha_mgr"]
    decision_id = _create_for_executor(
        client, auth, decision_world["owner_all"], mgr.id
    ).json()["id"]

    r = client.post(
        f"/api/v1/operations/owner-decisions/{decision_id}/respond",
        json={"note": ""},
        headers=auth(mgr),
    )
    assert r.status_code == 422
