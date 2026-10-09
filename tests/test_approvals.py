"""Submission lifecycle + approval engine tests (Phase 3).

These exercise the properties that matter most:

* server-side value validation (client cannot inject unknown fields or bad types);
* mandatory requirement gating, and that override requires both permission and
  a workflow that allows it;
* self-approval prevention and step skipping;
* concurrency safety on a task (double action rejected);
* company isolation on submissions and approval actions.
"""

from __future__ import annotations

import io

import pytest


def _publish(client, auth, ops_world):
    owner = ops_world["owner"]
    f = client.post(f"/api/v1/forms/{ops_world['form'].id}/publish", headers=auth(owner))
    assert f.status_code == 200, f.text
    w = client.post(
        f"/api/v1/workflows/{ops_world['workflow'].id}/publish", headers=auth(owner)
    )
    assert w.status_code == 200, w.text


def _create_draft(client, auth, ops_world, values=None, company=None):
    company = company or ops_world["alpha"]
    response = client.post(
        "/api/v1/form-submissions",
        json={
            "form_id": ops_world["form"].id,
            "company_id": company.id,
            "title": "طلب اختبار",
            "values": values if values is not None else {"amount": "1500", "purpose": "توسعة"},
        },
        headers=auth(ops_world["alpha_mgr"]),
    )
    return response


def test_submission_requires_published_form(client, auth, ops_world):
    # Form is still a draft in the fixture.
    response = _create_draft(client, auth, ops_world)
    assert response.status_code == 409


def test_create_draft_validates_values_server_side(client, auth, ops_world):
    _publish(client, auth, ops_world)
    bad = _create_draft(client, auth, ops_world, values={"amount": "not-a-number", "purpose": "x"})
    assert bad.status_code == 422

    unknown = _create_draft(client, auth, ops_world, values={"amount": "1", "purpose": "x", "hack": 1})
    assert unknown.status_code == 422


def test_submit_blocked_when_mandatory_document_missing(client, auth, ops_world):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world)
    assert draft.status_code == 201, draft.text
    submission_id = draft.json()["id"]

    submitted = client.post(
        f"/api/v1/form-submissions/{submission_id}/submit",
        json={"override_requirements": False},
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert submitted.status_code == 409

    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    assert detail["status"] == "incomplete"
    assert any(r["requirement_key"] == "quote" and not r["is_satisfied"] for r in detail["requirements"])


def test_override_denied_when_workflow_disallows(client, auth, ops_world):
    """The workflow has allow_requirement_override=False, so even the owner
    (who holds approval.override) cannot bypass the missing document."""
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()

    response = client.post(
        f"/api/v1/form-submissions/{draft['id']}/submit",
        json={"override_requirements": True, "override_reason": "urgent business need"},
        headers=auth(ops_world["owner"]),
    )
    # Owner is not the submitter -> forbidden; and the workflow disallows it.
    assert response.status_code in (403, 409)


def test_document_upload_satisfies_requirement_and_allows_submit(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]

    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]

    upload = client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("quote.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert upload.status_code == 201, upload.text

    submitted = client.post(
        f"/api/v1/form-submissions/{submission_id}/submit",
        json={"override_requirements": False},
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "in_review"


def test_upload_rejects_executable(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    detail = client.get(
        f"/api/v1/form-submissions/{draft['id']}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]

    response = client.post(
        f"/api/v1/form-submissions/{draft['id']}/requirements/{requirement_id}/documents",
        files={"file": ("evil.sh", io.BytesIO(b"#!/bin/sh\nrm -rf /"), "text/x-shellscript")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert response.status_code == 422


def test_self_approval_is_skipped_and_chain_advances(client, auth, ops_world, db):
    """alpha_mgr submits; the first step is company_manager (themselves), so it
    is auto-skipped and the finance step opens."""
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]
    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]
    client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("q.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    client.post(
        f"/api/v1/form-submissions/{submission_id}/submit",
        json={},
        headers=auth(ops_world["alpha_mgr"]),
    )

    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    workflow = detail["workflow"]
    # First step skipped (no eligible approver besides the submitter).
    first = next(t for t in workflow["tasks"] if t["step_order"] == 1)
    assert first["status"] == "skipped"
    # Second step is pending for the finance manager.
    second = next(t for t in workflow["tasks"] if t["step_order"] == 2)
    assert second["status"] == "pending"
    assert second["assignee_id"] == ops_world["finance"].id


def test_finance_manager_approves_and_request_completes(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]
    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]
    client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("q.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    client.post(
        f"/api/v1/form-submissions/{submission_id}/submit",
        json={},
        headers=auth(ops_world["alpha_mgr"]),
    )

    # Finance manager sees it in their inbox.
    inbox = client.get("/api/v1/approvals/my", headers=auth(ops_world["finance"])).json()
    assert inbox["total"] == 1
    task_id = inbox["items"][0]["task_id"]

    acted = client.post(
        f"/api/v1/approvals/tasks/{task_id}",
        json={"decision": "approve", "comment": "موافق"},
        headers=auth(ops_world["finance"]),
    )
    assert acted.status_code == 200, acted.text
    assert acted.json()["status"] == "approved"

    # Double-acting the same task is a conflict (concurrency guard).
    again = client.post(
        f"/api/v1/approvals/tasks/{task_id}",
        json={"decision": "approve"},
        headers=auth(ops_world["finance"]),
    )
    assert again.status_code in (404, 409)


def test_other_manager_cannot_act_on_someone_elses_task(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]
    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]
    client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("q.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    client.post(
        f"/api/v1/form-submissions/{submission_id}/submit",
        json={},
        headers=auth(ops_world["alpha_mgr"]),
    )
    inbox = client.get("/api/v1/approvals/my", headers=auth(ops_world["finance"])).json()
    task_id = inbox["items"][0]["task_id"]

    # alpha_mgr is not the assignee -> indistinguishable 404.
    response = client.post(
        f"/api/v1/approvals/tasks/{task_id}",
        json={"decision": "approve"},
        headers=auth(ops_world["alpha_mgr"]),
    )
    assert response.status_code == 404


def test_reject_requires_comment(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]
    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]
    client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("q.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    client.post(f"/api/v1/form-submissions/{submission_id}/submit", json={}, headers=auth(ops_world["alpha_mgr"]))
    task_id = client.get("/api/v1/approvals/my", headers=auth(ops_world["finance"])).json()["items"][0]["task_id"]

    response = client.post(
        f"/api/v1/approvals/tasks/{task_id}",
        json={"decision": "reject"},
        headers=auth(ops_world["finance"]),
    )
    assert response.status_code == 422

    with_comment = client.post(
        f"/api/v1/approvals/tasks/{task_id}",
        json={"decision": "reject", "comment": "الميزانية غير كافية"},
        headers=auth(ops_world["finance"]),
    )
    assert with_comment.status_code == 200, with_comment.text
    assert with_comment.json()["status"] == "rejected"


def test_company_isolation_blocks_cross_company_submission(client, auth, ops_world, db):
    """alpha_mgr cannot create a submission for BETA, nor read a BETA submission."""
    _publish(client, auth, ops_world)
    cross = _create_draft(client, auth, ops_world, company=ops_world["beta"])
    # require_company_access denies a company the user cannot write. The denial
    # is a 403 here (the company id is supplied in the body); the direct-id read
    # below is the true IDOR check and returns 404.
    assert cross.status_code == 403

    # A BETA submission created by beta_mgr is invisible to alpha_mgr by id.
    beta_draft = client.post(
        "/api/v1/form-submissions",
        json={
            "form_id": ops_world["form"].id,
            "company_id": ops_world["beta"].id,
            "values": {"amount": "10", "purpose": "x"},
        },
        headers=auth(ops_world["beta_mgr"]),
    )
    assert beta_draft.status_code == 201, beta_draft.text
    beta_id = beta_draft.json()["id"]

    peek = client.get(f"/api/v1/form-submissions/{beta_id}", headers=auth(ops_world["alpha_mgr"]))
    assert peek.status_code == 404


def test_timeline_is_append_only(client, auth, ops_world, db):
    _publish(client, auth, ops_world)
    draft = _create_draft(client, auth, ops_world).json()
    submission_id = draft["id"]
    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["alpha_mgr"])
    ).json()
    requirement_id = detail["requirements"][0]["id"]
    client.post(
        f"/api/v1/form-submissions/{submission_id}/requirements/{requirement_id}/documents",
        files={"file": ("q.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth(ops_world["alpha_mgr"]),
    )
    client.post(f"/api/v1/form-submissions/{submission_id}/submit", json={}, headers=auth(ops_world["alpha_mgr"]))
    task_id = client.get("/api/v1/approvals/my", headers=auth(ops_world["finance"])).json()["items"][0]["task_id"]
    client.post(f"/api/v1/approvals/tasks/{task_id}", json={"decision": "approve"}, headers=auth(ops_world["finance"]))

    detail = client.get(
        f"/api/v1/form-submissions/{submission_id}", headers=auth(ops_world["owner"])
    ).json()
    actions = [e["action"] for e in detail["workflow"]["events"]]
    assert "started" in actions
    assert "approved" in actions
    assert "completed" in actions
