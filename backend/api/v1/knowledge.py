"""Knowledge-base API: curated documents, retrieval and the learning loop.

Routes are thin; every rule lives in :mod:`backend.services.knowledge_service`,
which applies the caller's company scope and the document sensitivity ladder as
part of the query. "Not yours" and "does not exist" are both a 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from backend.api.deps import CurrentUser, DbSession
from backend.schemas import (
    KnowledgeApproveRequest,
    KnowledgeCategoryCreate,
    KnowledgeCategoryOut,
    KnowledgeDocumentCreate,
    KnowledgeDocumentOut,
    KnowledgeProposalCreate,
    KnowledgeProposalOut,
    KnowledgeProposalResolve,
    KnowledgeSearchHitOut,
    KnowledgeVersionCreate,
    KnowledgeVersionOut,
)
from backend.services import audit_service, knowledge_service

router = APIRouter(prefix="/ai/knowledge", tags=["ai-knowledge"])


@router.get("/search", response_model=list[KnowledgeSearchHitOut])
def search(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=2, max_length=500),
    company_id: int | None = None,
    top_k: int | None = Query(default=None, ge=1, le=50),
) -> list[KnowledgeSearchHitOut]:
    """Retrieve the approved knowledge chunks the caller may see."""
    chunks = knowledge_service.retrieve(
        db, user, query=q, top_k=top_k, company_id=company_id
    )
    return [KnowledgeSearchHitOut(**chunk.citation()) for chunk in chunks]


@router.get("/categories", response_model=list[KnowledgeCategoryOut])
def list_categories(
    user: CurrentUser, db: DbSession, include_inactive: bool = False
) -> list[KnowledgeCategoryOut]:
    rows = knowledge_service.list_categories(db, user, include_inactive=include_inactive)
    return [KnowledgeCategoryOut.model_validate(row) for row in rows]


@router.post(
    "/categories", response_model=KnowledgeCategoryOut, status_code=201
)
def create_category(
    payload: KnowledgeCategoryCreate, user: CurrentUser, db: DbSession
) -> KnowledgeCategoryOut:
    category = knowledge_service.create_category(
        db,
        user,
        code=payload.code,
        name_ar=payload.name_ar,
        name_en=payload.name_en,
        description=payload.description,
        display_order=payload.display_order,
    )
    return KnowledgeCategoryOut.model_validate(category)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    include_archived: bool = False,
) -> list[KnowledgeDocumentOut]:
    rows = knowledge_service.list_documents(
        db, user, company_id=company_id, include_unapproved=include_archived
    )
    return [KnowledgeDocumentOut.model_validate(row) for row in rows]


@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=201)
def create_document(
    payload: KnowledgeDocumentCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeDocumentOut:
    ctx = audit_service.request_context(request)
    document = knowledge_service.create_document(
        db,
        user,
        slug=payload.slug,
        title_ar=payload.title_ar,
        title_en=payload.title_en,
        body_ar=payload.body_ar,
        body_en=payload.body_en,
        category_id=payload.category_id,
        company_id=payload.company_id,
        sensitivity=payload.sensitivity,
        summary_ar=payload.summary_ar,
        summary_en=payload.summary_en,
        source_reference=payload.source_reference,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeDocumentOut.model_validate(document)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def get_document(
    document_id: int, user: CurrentUser, db: DbSession
) -> KnowledgeDocumentOut:
    document = knowledge_service.get_document(db, user, document_id)
    return KnowledgeDocumentOut.model_validate(document)


@router.get(
    "/documents/{document_id}/versions", response_model=list[KnowledgeVersionOut]
)
def list_versions(
    document_id: int, user: CurrentUser, db: DbSession
) -> list[KnowledgeVersionOut]:
    rows = knowledge_service.versions_for(db, user, document_id)
    return [KnowledgeVersionOut.model_validate(row) for row in rows]


@router.post(
    "/documents/{document_id}/versions",
    response_model=KnowledgeVersionOut,
    status_code=201,
)
def add_version(
    document_id: int,
    payload: KnowledgeVersionCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeVersionOut:
    ctx = audit_service.request_context(request)
    version = knowledge_service.add_version(
        db,
        user,
        document_id=document_id,
        body_ar=payload.body_ar,
        body_en=payload.body_en,
        source_reference=payload.source_reference,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeVersionOut.model_validate(version)


@router.post("/versions/{version_id}/approve", response_model=KnowledgeVersionOut)
def approve_version(
    version_id: int,
    payload: KnowledgeApproveRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeVersionOut:
    """Approve a version, which indexes it and makes it retrievable."""
    ctx = audit_service.request_context(request)
    version = knowledge_service.approve_version(
        db,
        user,
        version_id=version_id,
        review_note=payload.review_note,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeVersionOut.model_validate(version)


@router.post("/documents/{document_id}/archive", response_model=KnowledgeDocumentOut)
def archive_document(
    document_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeDocumentOut:
    ctx = audit_service.request_context(request)
    document = knowledge_service.archive_document(
        db,
        user,
        document_id=document_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeDocumentOut.model_validate(document)


@router.get("/proposals", response_model=list[KnowledgeProposalOut])
def list_proposals(
    user: CurrentUser, db: DbSession, status: str | None = None
) -> list[KnowledgeProposalOut]:
    rows = knowledge_service.list_proposals(db, user, status=status)
    return [KnowledgeProposalOut.model_validate(row) for row in rows]


@router.post("/proposals", response_model=KnowledgeProposalOut, status_code=201)
def raise_proposal(
    payload: KnowledgeProposalCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeProposalOut:
    ctx = audit_service.request_context(request)
    proposal = knowledge_service.raise_proposal(
        db,
        user,
        title=payload.title,
        proposed_body=payload.proposed_body,
        document_id=payload.document_id,
        kind=payload.kind,
        rationale=payload.rationale,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeProposalOut.model_validate(proposal)


@router.post("/proposals/{proposal_id}/resolve", response_model=KnowledgeProposalOut)
def resolve_proposal(
    proposal_id: int,
    payload: KnowledgeProposalResolve,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> KnowledgeProposalOut:
    ctx = audit_service.request_context(request)
    proposal = knowledge_service.resolve_proposal(
        db,
        user,
        proposal_id=proposal_id,
        approve=payload.approve,
        resolution_note=payload.resolution_note,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return KnowledgeProposalOut.model_validate(proposal)
