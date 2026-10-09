"""Workflow builder tests (Phase 3).

Covers step assignment validation, version forking (published chain frozen),
publish requirements, and reorder integrity.
"""

from __future__ import annotations

import pytest


def test_create_workflow_links_form_and_seeds_draft(client, auth, ops_world):
    owner = ops_world["owner"]
    response = client.post(
        "/api/v1/workflows",
        json={
            "code": "second_flow",
            "name_ar": "مسار ثاني",
            "name_en": "Second Flow",
            "form_id": ops_world["form"].id,
            "scope": "holding",
        },
        headers=auth(owner),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["latest_version_number"] == 1
    assert body["form_id"] == ops_world["form"].id


def test_user_step_requires_valid_user(client, auth, ops_world, db):
    owner = ops_world["owner"]
    response = client.post(
        f"/api/v1/workflows/{ops_world['workflow'].id}/steps",
        json={
            "key": "bad",
            "name_ar": "سيء",
            "name_en": "Bad",
            "assignment_type": "user",
            "assignment_config": {},
        },
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_role_step_requires_real_role(client, auth, ops_world):
    owner = ops_world["owner"]
    response = client.post(
        f"/api/v1/workflows/{ops_world['workflow'].id}/steps",
        json={
            "key": "ghost",
            "name_ar": "وهمي",
            "name_en": "Ghost",
            "assignment_type": "role",
            "assignment_config": {"role_code": "not_a_role"},
        },
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_publish_requires_at_least_one_step(client, auth, ops_world, db):
    from backend.db.models.enums import FormScope, WorkflowStatus
    from backend.db.models.workflows import WorkflowDefinition, WorkflowVersion

    owner = ops_world["owner"]
    empty = WorkflowDefinition(
        code="empty_flow", name_ar="فارغ", name_en="Empty",
        form_id=ops_world["form"].id, scope=FormScope.HOLDING.value,
        status=WorkflowStatus.DRAFT.value, created_by_id=owner.id,
    )
    db.add(empty)
    db.flush()
    db.add(
        WorkflowVersion(
            definition_id=empty.id, version_number=1,
            status=WorkflowStatus.DRAFT.value, created_by_id=owner.id,
        )
    )
    db.commit()

    response = client.post(f"/api/v1/workflows/{empty.id}/publish", headers=auth(owner))
    assert response.status_code == 422


def test_editing_published_workflow_forks_and_freezes(client, auth, ops_world, db):
    owner = ops_world["owner"]
    wf_id = ops_world["workflow"].id

    published = client.post(f"/api/v1/workflows/{wf_id}/publish", headers=auth(owner))
    assert published.status_code == 200, published.text
    published_version_id = published.json()["published_version_id"]

    # Add a step: must fork a draft, leaving the published chain intact.
    added = client.post(
        f"/api/v1/workflows/{wf_id}/steps",
        json={
            "key": "ceo",
            "name_ar": "الرئيس التنفيذي",
            "name_en": "CEO",
            "assignment_type": "role",
            "assignment_config": {"role_code": "ceo"},
        },
        headers=auth(owner),
    )
    assert added.status_code == 201, added.text

    versions = client.get(f"/api/v1/workflows/{wf_id}/versions", headers=auth(owner)).json()
    assert len(versions) == 2
    frozen = next(v for v in versions if v["id"] == published_version_id)
    assert frozen["status"] == "published"
    assert {s["key"] for s in frozen["steps"]} == {"manager", "finance"}

    draft = next(v for v in versions if v["status"] == "draft")
    assert "ceo" in {s["key"] for s in draft["steps"]}


def test_reorder_steps_requires_full_set(client, auth, ops_world):
    owner = ops_world["owner"]
    wf_id = ops_world["workflow"].id
    # The workflow's draft version has two steps.
    current = client.get(f"/api/v1/workflows/{wf_id}/current", headers=auth(owner)).json()
    one_id = current["steps"][0]["id"]
    response = client.post(
        f"/api/v1/workflows/{wf_id}/steps/reorder",
        json={"ordered_ids": [one_id]},
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_company_manager_cannot_publish_workflow(client, auth, ops_world):
    response = client.post(
        f"/api/v1/workflows/{ops_world['workflow'].id}/publish",
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert response.status_code in (403, 404)


def test_duplicate_workflow_copies_steps(client, auth, ops_world, db):
    owner = ops_world["owner"]
    response = client.post(
        f"/api/v1/workflows/{ops_world['workflow'].id}/duplicate?new_code=capex_flow_2",
        headers=auth(owner),
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["id"]
    current = client.get(f"/api/v1/workflows/{new_id}/current", headers=auth(owner)).json()
    assert {s["key"] for s in current["steps"]} == {"manager", "finance"}
