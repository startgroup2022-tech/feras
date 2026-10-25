"""S20: projects & opportunities register.

Verifies the vertical slice end to end: RBAC (server-side), company isolation,
validation, persistence, status updates, the audit trail and the owner-decision
link. The spec deliberately has *no* automatic feasibility decision and no
automatic opportunity->project transition (D03), so those are asserted absent by
construction -- ``record_type`` is only ever set explicitly.
"""

from __future__ import annotations

import pytest

from backend.db.models import ProjectRecord


@pytest.fixture
def proj_world(world, make_user):
    """BD scoped to alpha, an owner with both companies, and a marketing reader
    with no project permission at all."""
    owner_all = make_user("owner.proj@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    bd_alpha = make_user("bd.alpha@corp.sa", "business_development", [world["alpha"]])
    marketer = make_user("mkt.proj@corp.sa", "marketing", [world["alpha"]])
    world = dict(world)
    world["owner_all"] = owner_all
    world["bd_alpha"] = bd_alpha
    world["marketer"] = marketer
    return world


def test_bd_creates_and_reads_a_project_record(client, proj_world, auth, db):
    created = client.post(
        "/api/v1/operations/projects",
        json={
            "record_type": "opportunity",
            "name": "فرصة توسّع",
            "company_id": proj_world["alpha"].id,
            "objective": "دراسة توسّع السوق",
            "estimated_value": "1500000.00",
            "currency": "SAR",
            "period_start": "2027-01-01",
            "period_end": "2027-06-30",
        },
        headers=auth(proj_world["bd_alpha"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["record_type"] == "opportunity"
    assert body["status"] == "open"
    assert body["currency"] == "SAR"
    assert body["company_id"] == proj_world["alpha"].id

    listed = client.get(
        "/api/v1/operations/projects", headers=auth(proj_world["bd_alpha"])
    )
    assert listed.status_code == 200, listed.text
    ids = [r["id"] for r in listed.json()]
    assert body["id"] in ids


def test_marketing_without_project_permission_is_forbidden(client, proj_world, auth):
    created = client.post(
        "/api/v1/operations/projects",
        json={"name": "محاولة", "company_id": proj_world["alpha"].id},
        headers=auth(proj_world["marketer"]),
    )
    assert created.status_code == 403, created.text

    listed = client.get(
        "/api/v1/operations/projects", headers=auth(proj_world["marketer"])
    )
    assert listed.status_code == 403, listed.text


def test_bd_cannot_write_a_project_for_another_company(client, proj_world, auth):
    # BD has write access to alpha only; a beta-scoped record must be refused.
    refused = client.post(
        "/api/v1/operations/projects",
        json={"name": "خارج النطاق", "company_id": proj_world["beta"].id},
        headers=auth(proj_world["bd_alpha"]),
    )
    assert refused.status_code == 403, refused.text


def test_company_scoped_custom_role_sees_only_its_company(
    client, proj_world, auth, make_user
):
    """A custom role granted only ``project.read`` is not holding-wide, so it
    sees its own company's records (and group-wide ones) but not another
    company's."""
    owner = proj_world["owner_all"]
    created = client.post(
        "/api/v1/admin/roles",
        json={
            "code": "proj_reader_alpha",
            "name_ar": "قارئ مشاريع",
            "name_en": "Project reader",
            "permissions": ["project.read"],
        },
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text

    alpha_record = client.post(
        "/api/v1/operations/projects",
        json={"name": "فرصة ألفا", "company_id": proj_world["alpha"].id},
        headers=auth(owner),
    ).json()
    beta_record = client.post(
        "/api/v1/operations/projects",
        json={"name": "فرصة بيتا", "company_id": proj_world["beta"].id},
        headers=auth(owner),
    ).json()

    reader = make_user("proj.reader@corp.sa", "proj_reader_alpha", [proj_world["alpha"]])
    rows = client.get("/api/v1/operations/projects", headers=auth(reader)).json()
    ids = [r["id"] for r in rows]
    assert alpha_record["id"] in ids
    assert beta_record["id"] not in ids

    # The same reader may not create (no project.manage).
    denied = client.post(
        "/api/v1/operations/projects",
        json={"name": "محاولة", "company_id": proj_world["alpha"].id},
        headers=auth(reader),
    )
    assert denied.status_code == 403, denied.text


def test_update_is_refused_for_another_company(client, proj_world, auth, make_user):
    """A record created for beta must not be editable by a manager scoped to
    alpha, even when that manager holds ``project.manage``."""
    owner = proj_world["owner_all"]
    beta_record = client.post(
        "/api/v1/operations/projects",
        json={"name": "مشروع بيتا", "company_id": proj_world["beta"].id},
        headers=auth(owner),
    ).json()

    # Give an alpha-scoped manager the project-manage capability via a custom role.
    role = client.post(
        "/api/v1/admin/roles",
        json={
            "code": "proj_mgr_alpha",
            "name_ar": "مدير مشاريع",
            "name_en": "Project manager",
            "permissions": ["project.read", "project.manage"],
        },
        headers=auth(owner),
    )
    assert role.status_code == 201, role.text
    scoped_mgr = make_user("proj.scoped.mgr@corp.sa", "proj_mgr_alpha", [proj_world["alpha"]])

    refused = client.patch(
        f"/api/v1/operations/projects/{beta_record['id']}",
        json={"status": "closed"},
        headers=auth(scoped_mgr),
    )
    assert refused.status_code == 403, refused.text


def test_detail_is_scoped_like_the_list(client, proj_world, auth, make_user):
    owner = proj_world["owner_all"]
    beta_record = client.post(
        "/api/v1/operations/projects",
        json={"name": "مشروع بيتا", "company_id": proj_world["beta"].id},
        headers=auth(owner),
    ).json()

    # The owner reads the detail.
    own = client.get(
        f"/api/v1/operations/projects/{beta_record['id']}",
        headers=auth(owner),
    )
    assert own.status_code == 200, own.text
    assert own.json()["id"] == beta_record["id"]

    # A reader scoped to alpha cannot reach a beta record, and gets the same
    # error as a missing record (no existence leak).
    role = client.post(
        "/api/v1/admin/roles",
        json={
            "code": "proj_reader_only",
            "name_ar": "قارئ فقط",
            "name_en": "Reader only",
            "permissions": ["project.read"],
        },
        headers=auth(owner),
    )
    assert role.status_code == 201, role.text
    reader = make_user("proj.only@corp.sa", "proj_reader_only", [proj_world["alpha"]])
    denied = client.get(
        f"/api/v1/operations/projects/{beta_record['id']}",
        headers=auth(reader),
    )
    assert denied.status_code == 404, denied.text

    missing = client.get(
        "/api/v1/operations/projects/99999999",
        headers=auth(reader),
    )
    assert missing.status_code == 404, missing.text


def test_period_end_before_start_is_rejected(client, proj_world, auth):
    bad = client.post(
        "/api/v1/operations/projects",
        json={
            "name": "فترة خاطئة",
            "company_id": proj_world["alpha"].id,
            "period_start": "2027-06-01",
            "period_end": "2027-01-01",
        },
        headers=auth(proj_world["bd_alpha"]),
    )
    assert bad.status_code == 422, bad.text


def test_status_update_persists_and_is_audited(client, proj_world, auth, db):
    from backend.db.models.ai import AuditLog

    created = client.post(
        "/api/v1/operations/projects",
        json={"name": "مشروع متابعة", "company_id": proj_world["alpha"].id},
        headers=auth(proj_world["bd_alpha"]),
    )
    record_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/operations/projects/{record_id}",
        json={"status": "in_progress", "results": "تقدّم أولي"},
        headers=auth(proj_world["bd_alpha"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["results"] == "تقدّم أولي"

    db.expire_all()
    persisted = db.get(ProjectRecord, record_id)
    assert persisted.status == "in_progress"

    actions = {a.action for a in db.query(AuditLog).filter_by(entity_type="project_record")}
    assert "project_record.created" in actions
    assert "project_record.updated" in actions


def test_record_can_link_to_an_owner_decision(client, proj_world, auth):
    decision = client.post(
        "/api/v1/operations/owner-decisions",
        json={"number": "D-100", "title": "قرار اعتماد"},
        headers=auth(proj_world["owner_all"]),
    )
    assert decision.status_code == 201, decision.text
    decision_id = decision.json()["id"]

    created = client.post(
        "/api/v1/operations/projects",
        json={
            "name": "مشروع مرتبط بقرار",
            "company_id": proj_world["alpha"].id,
            "owner_decision_id": decision_id,
        },
        headers=auth(proj_world["bd_alpha"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner_decision_id"] == decision_id
