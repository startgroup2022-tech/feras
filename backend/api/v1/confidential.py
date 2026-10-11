"""Delegated confidential access endpoints (D04)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.domain import ConfidentialGrantCreateRequest
from backend.services import audit_service, confidential_access_service

router = APIRouter(prefix="/confidential-access", tags=["confidential-access"])


@router.get("/grants")
def list_grants(
    subject_type: str, subject_id: int, user: CurrentUser, db: DbSession
) -> list[dict]:
    return [
        confidential_access_service.serialise(g)
        for g in confidential_access_service.list_grants(
            db, actor=user, subject_type=subject_type, subject_id=subject_id
        )
    ]


@router.post("/grants", status_code=status.HTTP_201_CREATED)
def create_grant(
    payload: ConfidentialGrantCreateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    grant = confidential_access_service.grant_access(db, actor=user, **payload.model_dump(), **ctx)
    return confidential_access_service.serialise(grant)


@router.delete("/grants/{grant_id}")
def revoke_grant(grant_id: int, request: Request, user: CurrentUser, db: DbSession) -> dict:
    ctx = audit_service.request_context(request)
    grant = confidential_access_service.revoke_access(db, actor=user, grant_id=grant_id, **ctx)
    return confidential_access_service.serialise(grant)
