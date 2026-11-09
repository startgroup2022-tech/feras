"""AI knowledge base (RAG): scoped retrieval, curation and the learning loop.

The properties these tests defend, in order of importance:

1. **Isolation before scoring.** A company-scoped caller never retrieves another
   company's knowledge, and a non-owner never retrieves confidential knowledge
   -- not because it is filtered out of the answer, but because it is never
   loaded.
2. **Only approved knowledge is retrievable.** A draft is invisible; approving a
   version indexes it; archiving removes it.
3. **The assistant cites its sources** and never answers from a document the
   caller could not open directly.
4. **The usage monitor stores counters, never content.**
"""

from __future__ import annotations

import pytest

from backend.ai import OpenRouterProvider
from backend.ai.base import PaidModelError
from backend.ai.openrouter import OpenRouterClient, pricing_is_zero
from backend.core.config import settings
from backend.db.models.ai import AIUsageEvent
from backend.db.models.enums import KnowledgeSensitivity
from backend.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.services import ai_usage_service, knowledge_service

CATEGORIES = "/api/v1/ai/knowledge/categories"
DOCUMENTS = "/api/v1/ai/knowledge/documents"
SEARCH = "/api/v1/ai/knowledge/search"
PROPOSALS = "/api/v1/ai/knowledge/proposals"
ASK = "/api/v1/ai/knowledge"


def _create_document(client, auth, user, **overrides) -> dict:
    payload = {
        "slug": "leave-policy",
        "title_ar": "سياسة الإجازات",
        "title_en": "Leave policy",
        "body_ar": "يمنح الموظف إجازة سنوية مدفوعة مدتها ثلاثون يوماً. تُقدَّم طلبات الإجازة قبل أسبوع.",
        "sensitivity": "holding",
    }
    payload.update(overrides)
    response = client.post(DOCUMENTS, headers=auth(user), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _approve_latest(client, auth, user, document_id: int) -> dict:
    versions = client.get(
        f"{DOCUMENTS}/{document_id}/versions", headers=auth(user)
    ).json()
    version_id = versions[0]["id"]
    response = client.post(
        f"/api/v1/ai/knowledge/versions/{version_id}/approve",
        headers=auth(user),
        json={},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------
# curation and lifecycle
# --------------------------------------------------------------------------
def test_owner_can_create_and_approve_a_document(client, world, auth):
    document = _create_document(client, auth, world["owner"])
    assert document["status"] == "draft"

    version = _approve_latest(client, auth, world["owner"], document["id"])
    assert version["status"] == "approved"


def test_draft_is_not_retrievable_until_approved(client, world, auth):
    document = _create_document(client, auth, world["owner"])

    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "إجازة سنوية"}
    ).json()
    assert hits == []

    _approve_latest(client, auth, world["owner"], document["id"])
    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "إجازة سنوية"}
    ).json()
    assert hits
    assert hits[0]["title_ar"] == "سياسة الإجازات"


def test_archive_removes_a_document_from_retrieval(client, world, auth):
    document = _create_document(client, auth, world["owner"])
    _approve_latest(client, auth, world["owner"], document["id"])

    response = client.post(
        f"{DOCUMENTS}/{document['id']}/archive", headers=auth(world["owner"])
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"

    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "إجازة سنوية"}
    ).json()
    assert hits == []


def test_approving_a_new_version_replaces_the_old_chunks(client, world, auth):
    document = _create_document(client, auth, world["owner"])
    _approve_latest(client, auth, world["owner"], document["id"])

    client.post(
        f"{DOCUMENTS}/{document['id']}/versions",
        headers=auth(world["owner"]),
        json={"body_ar": "سياسة محدثة: الإجازة السنوية أصبحت عشرين يوماً فقط."},
    )
    _approve_latest(client, auth, world["owner"], document["id"])

    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "عشرين"}
    ).json()
    assert hits
    # The superseded text must no longer be retrievable.
    stale = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "ثلاثون"}
    ).json()
    assert stale == []


# --------------------------------------------------------------------------
# isolation
# --------------------------------------------------------------------------
def test_company_scope_hides_another_companys_knowledge(client, world, auth):
    _create_document(
        client, auth, world["owner"],
        slug="alpha-only", title_ar="تعليمات ألفا",
        body_ar="إجراء خاص بشركة ألفا لاعتماد المشتريات.",
        sensitivity=KnowledgeSensitivity.COMPANY.value,
        company_id=world["alpha"].id,
    )
    _approve_latest(
        client, auth, world["owner"],
        client.get(DOCUMENTS, headers=auth(world["owner"])).json()[0]["id"],
    )

    alpha_hits = client.get(
        SEARCH, headers=auth(world["alpha_mgr"]), params={"q": "اعتماد المشتريات"}
    ).json()
    beta_hits = client.get(
        SEARCH, headers=auth(world["beta_mgr"]), params={"q": "اعتماد المشتريات"}
    ).json()

    assert alpha_hits
    assert beta_hits == []


def test_confidential_knowledge_is_hidden_from_a_company_manager(client, world, auth):
    document = _create_document(
        client, auth, world["owner"],
        slug="board-minutes", title_ar="محضر اجتماع مجلس الإدارة",
        body_ar="قرارات مجلس الإدارة السرية بشأن إعادة الهيكلة.",
        sensitivity=KnowledgeSensitivity.CONFIDENTIAL.value,
    )
    _approve_latest(client, auth, world["owner"], document["id"])

    owner_hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "إعادة الهيكلة"}
    ).json()
    manager_hits = client.get(
        SEARCH, headers=auth(world["alpha_mgr"]), params={"q": "إعادة الهيكلة"}
    ).json()

    assert owner_hits
    assert manager_hits == []


def test_company_scoped_user_cannot_open_another_companys_document(client, world, auth):
    document = _create_document(
        client, auth, world["owner"],
        slug="beta-doc", title_ar="مستند بيتا",
        sensitivity=KnowledgeSensitivity.COMPANY.value,
        company_id=world["beta"].id,
    )
    response = client.get(
        f"{DOCUMENTS}/{document['id']}", headers=auth(world["alpha_mgr"])
    )
    assert response.status_code == 404


def test_external_consultant_cannot_ask_the_knowledge_assistant(client, world, auth, make_user):
    consultant = make_user("consultant@outside.sa", "external_consultant")
    response = client.post(
        ASK, headers=auth(consultant), json={"question": "سياسة الإجازات؟"}
    )
    assert response.status_code == 403


def test_company_manager_cannot_curate_the_knowledge_base(client, world, auth):
    response = client.post(
        DOCUMENTS,
        headers=auth(world["alpha_mgr"]),
        json={"slug": "denied-doc", "title_ar": "عنوان", "body_ar": "نص"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# knowledge-scope answering
# --------------------------------------------------------------------------
def test_knowledge_answer_cites_its_sources(client, world, auth):
    document = _create_document(client, auth, world["owner"])
    _approve_latest(client, auth, world["owner"], document["id"])

    body = client.post(
        ASK, headers=auth(world["owner"]), json={"question": "كم مدة الإجازة السنوية؟"}
    ).json()

    assert body["scope"] == "knowledge"
    assert body["sources"], "a knowledge answer must cite its sources"
    assert body["sources"][0]["document_id"] == document["id"]
    assert body["sources"][0]["title_ar"] == "سياسة الإجازات"


def test_knowledge_answer_never_cites_an_invisible_document(client, world, auth):
    _create_document(
        client, auth, world["owner"],
        slug="secret-plan", title_ar="الخطة السرية",
        body_ar="الخطة السرية لإعادة الهيكلة المالية للمجموعة.",
        sensitivity=KnowledgeSensitivity.CONFIDENTIAL.value,
    )
    _approve_latest(
        client, auth, world["owner"],
        client.get(DOCUMENTS, headers=auth(world["owner"])).json()[0]["id"],
    )

    body = client.post(
        ASK, headers=auth(world["alpha_mgr"]), json={"question": "الخطة السرية"}
    ).json()

    cited = {s["document_id"] for s in body["sources"]}
    assert cited == set(), "an invisible document must never be cited"


def test_conversation_cannot_pivot_between_scopes(client, world, auth):
    holding = client.post(
        "/api/v1/ai/holding?year=2027&month=10",
        headers=auth(world["owner"]),
        json={"question": "ملخص"},
    ).json()

    response = client.post(
        ASK,
        headers=auth(world["owner"]),
        json={"question": "سياسة", "conversation_id": holding["conversation_id"]},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------
# learning proposals
# --------------------------------------------------------------------------
def test_proposal_needs_owner_resolution_and_does_not_self_apply(client, world, auth):
    document = _create_document(client, auth, world["owner"])
    _approve_latest(client, auth, world["owner"], document["id"])

    proposal = client.post(
        PROPOSALS,
        headers=auth(world["owner"]),
        json={
            "title": "تصحيح مدة الإجازة",
            "proposed_body": "الإجازة السنوية أصبحت خمسة وعشرون يوماً.",
            "document_id": document["id"],
        },
    ).json()
    assert proposal["status"] == "pending"

    # The proposal text must not be retrievable before it is approved.
    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "خمسة وعشرون"}
    ).json()
    assert hits == []

    resolved = client.post(
        f"{PROPOSALS}/{proposal['id']}/resolve",
        headers=auth(world["owner"]),
        json={"approve": True, "resolution_note": "موافق"},
    ).json()
    assert resolved["status"] == "approved"
    assert resolved["applied_version_id"] is not None


# --------------------------------------------------------------------------
# chunking and normalisation (pure functions)
# --------------------------------------------------------------------------
def test_chunking_covers_the_whole_body():
    body = ". ".join(f"الجملة رقم {i}" for i in range(200))
    chunks = knowledge_service.chunk_text(body, size=400, overlap=50)
    assert len(chunks) > 1
    # Every sentence survives somewhere in the chunk set.
    joined = " ".join(chunks)
    assert "الجملة رقم 0" in joined
    assert "الجملة رقم 199" in joined


def test_arabic_normalisation_folds_variants():
    assert knowledge_service.normalize_arabic("إجازة") == knowledge_service.normalize_arabic("اجازه")
    assert "ال" in knowledge_service.normalize_arabic("الأجازة")


def test_empty_query_returns_nothing(client, world, auth):
    hits = client.get(SEARCH, headers=auth(world["owner"]), params={"q": "   "}).json()
    assert hits == []


def test_multi_term_query_matches_on_any_term_not_all(client, world, auth):
    """A multi-word query must match a chunk containing only one of its terms.

    The lexical fallback (SQLite) scores on *any* shared token, and the suite's
    own isolation test relies on this: the query "اعتماد المشتريات" must match a
    body that contains only "المشتريات". The PostgreSQL full-text path must use
    the same any-term semantics -- ``plainto_tsquery`` ANDs its terms and would
    return nothing here, diverging from the documented cross-backend contract.
    """
    _create_document(
        client, auth, world["owner"],
        slug="any-term",
        title_ar="تعليمات عامة",
        body_ar="إجراء خاص بشركة ألفا لاعتماد المشتريات.",
        sensitivity="holding",
    )
    _approve_latest(
        client, auth, world["owner"],
        client.get(DOCUMENTS, headers=auth(world["owner"])).json()[0]["id"],
    )

    # Only "المشتريات" is present in the body; "اعتماد" is a variant of
    # "لاعتماد" and must not be required.
    hits = client.get(
        SEARCH, headers=auth(world["owner"]), params={"q": "اعتماد المشتريات"}
    ).json()
    assert hits, "a query whose terms are only partially present must still match"


def test_fts_query_or_joins_terms():
    """The PostgreSQL tsquery must OR its terms, never AND them.

    This is the backend-independent guard: the SQLite suite cannot exercise the
    PostgreSQL ``to_tsquery`` path, so the string it builds is asserted directly.
    """
    assert knowledge_service._fts_query({"اعتماد", "المشتريات"}) == "اعتماد | المشتريات"
    assert "&" not in knowledge_service._fts_query({"a", "b", "c"})
    assert knowledge_service._fts_query(set()) == ""


# --------------------------------------------------------------------------
# OpenRouter provider: never a paid model
# --------------------------------------------------------------------------
CATALOGUE = {
    "data": [
        {"id": "openrouter/free", "name": "Free Router", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "free/model:free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "paid/model", "name": "Paid", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        {"id": "unknown/model", "name": "Unknown", "pricing": {"prompt": "0"}},
    ]
}


def _transport(method, url, headers, body, timeout):
    import json

    if method == "GET" and url.endswith("/models"):
        return CATALOGUE
    request = json.loads(body.decode())
    model = request["model"]
    if model == "openrouter/free":
        return {
            "model": "free/model:free",
            "choices": [{"message": {"content": "جواب"}}],
            "usage": {"total_tokens": 7},
        }
    return {
        "model": model,
        "choices": [{"message": {"content": "جواب"}}],
        "usage": {"total_tokens": 7},
    }


def _provider(model: str) -> OpenRouterProvider:
    client = OpenRouterClient(api_key="k", base_url="https://x/api/v1", transport=_transport)
    return OpenRouterProvider(api_key="k", base_url="https://x", model=model, client=client)


def test_pricing_is_zero_only_for_a_complete_zero_block():
    assert pricing_is_zero({"prompt": "0", "completion": "0"})
    assert not pricing_is_zero({"prompt": "0"})
    assert not pricing_is_zero({"prompt": "0.01", "completion": "0"})
    assert not pricing_is_zero(None)


def test_openrouter_refuses_a_paid_model():
    with pytest.raises(PaidModelError):
        _provider("paid/model").answer(question="q", context={})


def test_openrouter_refuses_a_model_with_unknown_price():
    with pytest.raises(PaidModelError):
        _provider("unknown/model").answer(question="q", context={})


def test_openrouter_free_router_returns_the_concrete_model():
    answer = _provider("openrouter/free").answer(question="q", context={})
    assert answer.model == "free/model:free"
    assert answer.cost_usd == 0.0


def test_openrouter_free_model_listing_excludes_paid():
    ids = {m.id for m in _provider("openrouter/free").free_models()}
    assert "free/model:free" in ids
    assert "paid/model" not in ids
    assert "unknown/model" not in ids


# --------------------------------------------------------------------------
# usage monitor
# --------------------------------------------------------------------------
def test_usage_monitor_records_counters_not_content(client, world, auth, db):
    document = _create_document(client, auth, world["owner"])
    _approve_latest(client, auth, world["owner"], document["id"])
    client.post(ASK, headers=auth(world["owner"]), json={"question": "الإجازة"})

    columns = {c.name for c in AIUsageEvent.__table__.columns}
    # The monitor must never have a column that could hold a prompt or answer.
    assert "prompt" not in columns
    assert "content" not in columns
    assert "answer" not in columns


def test_usage_summary_reports_limits(db):
    summary = ai_usage_service.summary(db)
    assert "totals" in summary
    assert summary["rate_limit"]["requests"] == settings.AI_RATE_LIMIT_REQUESTS


def test_deterministic_provider_is_not_metered(client, world, auth, db):
    client.post(
        "/api/v1/ai/holding?year=2027&month=10",
        headers=auth(world["owner"]),
        json={"question": "ملخص"},
    )
    # The offline provider costs nothing and must not create usage rows.
    assert db.query(AIUsageEvent).count() == 0


def test_usage_endpoint_requires_ai_admin(client, world, auth):
    denied = client.get("/api/v1/ai/usage", headers=auth(world["alpha_mgr"]))
    assert denied.status_code == 403

    allowed = client.get("/api/v1/ai/usage", headers=auth(world["owner"]))
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["provider"] == "none"
    assert "usage" in body


def test_document_slug_must_be_unique(client, world, auth):
    _create_document(client, auth, world["owner"])
    response = client.post(
        DOCUMENTS,
        headers=auth(world["owner"]),
        json={"slug": "leave-policy", "title_ar": "أخرى", "body_ar": "نص آخر"},
    )
    assert response.status_code == 409


def test_chunks_are_indexed_only_for_the_approved_version(db, client, world, auth):
    document = _create_document(client, auth, world["owner"])
    assert db.query(KnowledgeChunk).filter_by(document_id=document["id"]).count() == 0
    _approve_latest(client, auth, world["owner"], document["id"])
    assert db.query(KnowledgeChunk).filter_by(document_id=document["id"]).count() >= 1
