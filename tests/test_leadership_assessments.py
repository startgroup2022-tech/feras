"""S23 -- leadership assessment centre: confidentiality & owner visibility.

The leadership assessment is a confidential, owner-only surface (D04). Two real
defects are locked down here:

* the owner's own leadership assessments were silently hidden from the default
  list endpoint (the type defaulted to "employee");
* a non-owner holding ``assessment.manage`` could *create* a leadership
  assessment, defeating the owner-only rule.

The tests exercise the real API against the real database.
"""

from __future__ import annotations


def _create_leadership(client, auth, actor, company, subject):
    return client.post(
        "/api/v1/employees/assessments",
        json={
            "company_id": company.id,
            "period_label": "2027-Q4",
            "assessment_type": "leadership",
            "subject_user_id": subject.id,
            "summary": "سرّي",
        },
        headers=auth(actor),
    )


def test_owner_sees_own_leadership_assessment_in_default_list(
    client, world, auth, make_user
):
    owner = make_user("owner_ls@corp.sa", "holding_owner", [world["alpha"]])
    created = _create_leadership(client, auth, owner, world["alpha"], world["alpha_mgr"])
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    # No assessment_type filter: the owner's S23 screen reads exactly this.
    listed = client.get("/api/v1/employees/assessments/list", headers=auth(owner))
    assert listed.status_code == 200, listed.text
    assert aid in [a["id"] for a in listed.json()], "owner cannot see own leadership assessment"

    # And the explicit filter still works.
    typed = client.get(
        "/api/v1/employees/assessments/list?assessment_type=leadership",
        headers=auth(owner),
    )
    assert aid in [a["id"] for a in typed.json()]


def test_non_owner_cannot_create_a_leadership_assessment(client, world, auth):
    # The company manager holds assessment.manage but is not the confidential
    # owner, so creating an owner-only record must be refused.
    denied = _create_leadership(
        client, auth, world["alpha_mgr"], world["alpha"], world["beta_mgr"]
    )
    assert denied.status_code == 403, denied.text


def test_non_owner_never_sees_leadership_in_the_default_list(client, world, auth):
    # Even an explicit leadership query yields nothing for a non-owner.
    listed = client.get(
        "/api/v1/employees/assessments/list?assessment_type=leadership",
        headers=auth(world["alpha_mgr"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == []

    default = client.get("/api/v1/employees/assessments/list", headers=auth(world["alpha_mgr"]))
    assert default.status_code == 200, default.text
    assert all(a["assessment_type"] != "leadership" for a in default.json())


def test_owner_can_delegate_leadership_visibility_to_a_grantee(
    client, world, auth, make_user
):
    """D04: the owner may delegate one record; the grantee then sees only it."""
    from datetime import datetime, timedelta, timezone

    owner = make_user("owner_del@corp.sa", "holding_owner", [world["alpha"]])
    created = _create_leadership(client, auth, owner, world["alpha"], world["beta_mgr"])
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    grantee = world["alpha_mgr"]
    grant = client.post(
        "/api/v1/confidential-access/grants",
        json={
            "subject_type": "leadership_assessment",
            "subject_id": aid,
            "grantee_user_id": grantee.id,
            "permission_code": "assessment.read",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth(owner),
    )
    assert grant.status_code == 201, grant.text

    listed = client.get(
        "/api/v1/employees/assessments/list?assessment_type=leadership",
        headers=auth(grantee),
    )
    assert listed.status_code == 200, listed.text
    assert [a["id"] for a in listed.json()] == [aid]


def test_owner_can_save_a_secret_note_on_a_leadership_assessment(
    client, world, auth, make_user, db
):
    """S23: ``ملاحظات المالك`` is secret text the owner saves as later context."""
    from backend.db.models.ai import AuditLog
    from backend.db.models.audit_actions import AuditAction

    owner = make_user("owner_note@corp.sa", "holding_owner", [world["alpha"]])
    created = _create_leadership(client, auth, owner, world["alpha"], world["alpha_mgr"])
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    secret = "ملاحظة سرية: أداء القيادة يحتاج متابعة في الربع القادم"
    saved = client.post(
        f"/api/v1/employees/assessments/{aid}/owner-note",
        json={"note": secret},
        headers=auth(owner),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["owner_note"] == secret

    # The secret must never reach the shared audit log (AC-23).
    logs = list(
        db.query(AuditLog).filter(AuditLog.action == AuditAction.ASSESSMENT_OWNER_NOTE_SAVED)
    )
    assert logs, "the owner-note save must be audited"
    for log in logs:
        assert secret not in (log.meta_json or "")


def test_secret_owner_note_is_never_returned_to_a_grantee(
    client, world, auth, make_user
):
    """AC-23: a delegated reader sees the assessment but not the secret note."""
    from datetime import datetime, timedelta, timezone

    owner = make_user("owner_note2@corp.sa", "holding_owner", [world["alpha"]])
    created = _create_leadership(client, auth, owner, world["alpha"], world["alpha_mgr"])
    aid = created.json()["id"]
    secret = "سياق سري للمالك فقط"
    saved = client.post(
        f"/api/v1/employees/assessments/{aid}/owner-note",
        json={"note": secret},
        headers=auth(owner),
    )
    assert saved.status_code == 200, saved.text

    grantee = world["alpha_mgr"]
    grant = client.post(
        "/api/v1/confidential-access/grants",
        json={
            "subject_type": "leadership_assessment",
            "subject_id": aid,
            "grantee_user_id": grantee.id,
            "permission_code": "assessment.read",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        },
        headers=auth(owner),
    )
    assert grant.status_code == 201, grant.text

    listed = client.get(
        "/api/v1/employees/assessments/list?assessment_type=leadership",
        headers=auth(grantee),
    )
    assert listed.status_code == 200, listed.text
    rows = [a for a in listed.json() if a["id"] == aid]
    assert rows, "the grantee should still see the delegated assessment"
    assert "owner_note" not in rows[0], "the secret note leaked to a grantee"


def test_non_owner_cannot_save_a_secret_owner_note(client, world, auth, make_user):
    owner = make_user("owner_note3@corp.sa", "holding_owner", [world["alpha"]])
    created = _create_leadership(client, auth, owner, world["alpha"], world["alpha_mgr"])
    aid = created.json()["id"]
    denied = client.post(
        f"/api/v1/employees/assessments/{aid}/owner-note",
        json={"note": "محاولة غير مصرح بها"},
        headers=auth(world["alpha_mgr"]),
    )
    assert denied.status_code in (403, 404), denied.text
