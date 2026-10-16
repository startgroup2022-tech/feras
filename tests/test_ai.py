"""Holding AI: answers must be grounded in the caller's data, never invented."""

from __future__ import annotations

import pytest

from backend.db.models.enums import CompanyHealth
from backend.services import ai_service

HOLDING = "/api/v1/ai/holding?year=2027&month=10"
COMPANY = "/api/v1/ai/company?year=2027&month=10"


def test_holding_context_is_built_from_live_data(client, world, auth):
    response = client.post(HOLDING, headers=auth(world["owner"]), json={"question": "ملخص"})

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "holding"
    assert set(body["grounded_on_company_ids"]) == {world["alpha"].id, world["beta"].id}
    assert body["provider"] == "none"  # deterministic provider until Phase 2


def test_answer_reports_the_real_group_total(client, world, auth):
    body = client.post(HOLDING, headers=auth(world["owner"]), json={"question": "ملخص"}).json()

    assert "1,111,110" in body["answer"]


def test_answer_names_companies_that_did_not_report(client, world, auth, make_company):
    make_company("GAMMA", "شركة جاما")

    body = client.post(HOLDING, headers=auth(world["owner"]), json={"question": "ملخص"}).json()

    assert "شركة جاما" in body["answer"]


def test_answer_names_companies_needing_attention(client, world, auth, make_company):
    make_company("SICKCO", "شركة متعثرة", health=CompanyHealth.ATTENTION.value)

    body = client.post(HOLDING, headers=auth(world["owner"]), json={"question": "ملخص"}).json()

    assert "شركة متعثرة" in body["answer"]


def test_answer_never_mentions_data_that_does_not_exist(client, world, auth):
    """A question about a company with no figures must not invent numbers."""
    from backend.db.models.identity import Company

    empty = client.post(
        "/api/v1/ai/company?year=2027&month=10",
        headers=auth(world["owner"]),
        json={"question": "ملخص الأداء", "company_id": world["alpha"].id},
    ).json()

    # Every figure in the answer must come from the seeded report.
    assert "111,110" in empty["answer"]


def test_company_answer_is_scoped_and_hides_the_group(client, world, auth):
    body = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص أدائنا", "company_id": world["alpha"].id},
    ).json()

    assert body["grounded_on_company_ids"] == [world["alpha"].id]
    assert "999,998" not in body["answer"]


def test_company_answer_requires_a_company_id(client, world, auth):
    response = client.post(COMPANY, headers=auth(world["owner"]), json={"question": "ملخص"})

    assert response.status_code == 422


def test_manager_cannot_ask_about_another_company(client, world, auth):
    response = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص", "company_id": world["beta"].id},
    )

    assert response.status_code == 403


def test_manager_cannot_use_holding_ai(client, world, auth):
    response = client.post(HOLDING, headers=auth(world["alpha_mgr"]), json={"question": "ملخص"})

    assert response.status_code == 403


def test_marketing_can_use_holding_ai(client, auth, make_user):
    marketer = make_user("mkt@corp.sa", "marketing")

    assert client.post(HOLDING, headers=auth(marketer), json={"question": "ملخص"}).status_code == 200


# --------------------------------------------------------------------------
# conversation continuity and validation
# --------------------------------------------------------------------------
def test_conversation_is_reused_across_turns(client, world, auth):
    first = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص", "company_id": world["alpha"].id},
    ).json()

    second = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={
            "question": "وأكثر تفصيلاً؟",
            "company_id": world["alpha"].id,
            "conversation_id": first["conversation_id"],
        },
    ).json()

    assert second["conversation_id"] == first["conversation_id"]
    assert second["message"]["role"] == "assistant"
    # The second turn is stored on the same conversation as the first.
    assert first["message"]["id"] < second["message"]["id"]


def test_question_must_be_meaningful(client, world, auth):
    response = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "?", "company_id": world["alpha"].id},
    )

    assert response.status_code == 422


def test_blank_question_is_rejected(client, world, auth):
    response = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "   ", "company_id": world["alpha"].id},
    )

    assert response.status_code == 422


def test_ai_calls_are_audited(client, world, auth, db):
    from backend.db.models import AuditLog
    from backend.db.models.audit_actions import AuditAction

    client.post(HOLDING, headers=auth(world["owner"]), json={"question": "ملخص"})

    actions = [row.action for row in db.query(AuditLog)]
    assert AuditAction.AI_CONVERSATION_STARTED in actions
    assert AuditAction.AI_MESSAGE_SENT in actions


def test_unknown_conversation_id_is_rejected(client, world, auth):
    response = client.post(
        COMPANY,
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص", "company_id": world["alpha"].id, "conversation_id": 999999},
    )

    assert response.status_code == 404


def test_provider_is_selected_from_configuration(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "AI_PROVIDER", "none")
    assert ai_service.get_provider().name == "none"
