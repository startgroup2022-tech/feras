"""Website Management (CMS) admin API under ``/api/v1/website``.

Authenticated and permission gated. It is the writing counterpart to the
public website: every route requires a ``website.*`` permission, and the
service layer re-checks authorization so the router stays a thin adapter.

The raw media-file endpoint serves *private* assets to a holder of
``website.content.read``; public assets are streamed by
``/api/v1/public/website/media`` instead, so the visibility boundary is
enforced at the HTTP layer too.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.schemas.website_cms import (
    WebsiteCmsOverviewOut,
    WebsiteCompanyIn,
    WebsiteCompanyOut,
    WebsiteMediaOut,
    WebsiteMediaUpdate,
    WebsiteMenuIn,
    WebsiteMenuOut,
    WebsitePageIn,
    WebsitePageOut,
    WebsiteRevisionOut,
    WebsiteSeoIn,
    WebsiteSeoOut,
    WebsiteServiceIn,
    WebsiteServiceOut,
    WebsiteSettingsOut,
    WebsiteSettingsUpdate,
    WebsiteSlideIn,
    WebsiteSlideOut,
)
from backend.services import audit_service, website_cms_service as cms

router = APIRouter(prefix="/website", tags=["website-cms"])


def _ctx(request: Request) -> dict:
    return audit_service.request_context(request)


# --------------------------------------------------------------------------
# overview + settings
# --------------------------------------------------------------------------
@router.get("/overview", response_model=WebsiteCmsOverviewOut)
def get_overview(db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))) -> WebsiteCmsOverviewOut:
    return WebsiteCmsOverviewOut(**cms.overview(db, actor=user))


@router.get("/settings", response_model=WebsiteSettingsOut)
def get_settings(db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))) -> WebsiteSettingsOut:
    return WebsiteSettingsOut(**cms.settings_out(db, cms.get_settings(db)))


@router.patch("/settings", response_model=WebsiteSettingsOut)
def update_settings(
    request: Request,
    db: DbSession,
    payload: WebsiteSettingsUpdate,
    actor=Depends(require(Perm.WEBSITE_SETTINGS_MANAGE)),
) -> WebsiteSettingsOut:
    ctx = _ctx(request)
    row = cms.update_settings(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **ctx
    )
    return WebsiteSettingsOut(**cms.settings_out(db, row))


# --------------------------------------------------------------------------
# media
# --------------------------------------------------------------------------
@router.get("/media", response_model=list[WebsiteMediaOut])
def list_media(
    db: DbSession,
    user=Depends(require(Perm.WEBSITE_CONTENT_READ)),
    visibility: str | None = Query(default=None),
    usage: str | None = Query(default=None),
) -> list[WebsiteMediaOut]:
    rows = cms.list_media(db, actor=user, visibility=visibility, usage=usage)
    return [WebsiteMediaOut(**cms.media_out(db, row)) for row in rows]


@router.post("/media", response_model=WebsiteMediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WEBSITE_MEDIA_MANAGE)),
    file: UploadFile = File(...),
    visibility: str = Form(default="public"),
    usage: str | None = Form(default=None),
    alt_text_ar: str | None = Form(default=None),
    alt_text_en: str | None = Form(default=None),
) -> WebsiteMediaOut:
    data = await file.read()
    ctx = _ctx(request)
    row = cms.record_media(
        db,
        actor=actor,
        data=data,
        filename=file.filename or "",
        content_type=file.content_type,
        visibility=visibility,
        usage=usage,
        alt_text_ar=alt_text_ar,
        alt_text_en=alt_text_en,
        **ctx,
    )
    return WebsiteMediaOut(**cms.media_out(db, row))


@router.patch("/media/{media_id}", response_model=WebsiteMediaOut)
def update_media(
    request: Request,
    db: DbSession,
    media_id: int,
    payload: WebsiteMediaUpdate,
    actor=Depends(require(Perm.WEBSITE_MEDIA_MANAGE)),
) -> WebsiteMediaOut:
    ctx = _ctx(request)
    row = cms.update_media(
        db, actor=actor, media_id=media_id, payload=payload.model_dump(exclude_unset=True), **ctx
    )
    return WebsiteMediaOut(**cms.media_out(db, row))


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    request: Request,
    db: DbSession,
    media_id: int,
    actor=Depends(require(Perm.WEBSITE_MEDIA_MANAGE)),
) -> Response:
    cms.delete_media(db, actor=actor, media_id=media_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/media/{media_id}/file", include_in_schema=False)
def media_file(
    db: DbSession,
    media_id: int,
    user=Depends(require(Perm.WEBSITE_CONTENT_READ)),
) -> FileResponse:
    path, content_type = cms.resolve_media_for_admin(db, actor=user, media_id=media_id)
    return FileResponse(str(path), media_type=content_type or "application/octet-stream")


# --------------------------------------------------------------------------
# slides
# --------------------------------------------------------------------------
@router.get("/slides", response_model=list[WebsiteSlideOut])
def list_slides(db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))) -> list[WebsiteSlideOut]:
    return [WebsiteSlideOut(**cms.slide_out(db, row)) for row in cms.list_slides(db, actor=user)]


@router.post("/slides", response_model=WebsiteSlideOut, status_code=status.HTTP_201_CREATED)
def create_slide(
    request: Request,
    db: DbSession,
    payload: WebsiteSlideIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteSlideOut:
    row = cms.create_slide(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteSlideOut(**cms.slide_out(db, row))


@router.patch("/slides/{slide_id}", response_model=WebsiteSlideOut)
def update_slide(
    request: Request,
    db: DbSession,
    slide_id: int,
    payload: WebsiteSlideIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteSlideOut:
    row = cms.update_slide(
        db, actor=actor, slide_id=slide_id, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteSlideOut(**cms.slide_out(db, row))


@router.delete("/slides/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slide(
    request: Request,
    db: DbSession,
    slide_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> Response:
    cms.delete_slide(db, actor=actor, slide_id=slide_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------
@router.get("/pages", response_model=list[WebsitePageOut])
def list_pages(db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))) -> list[WebsitePageOut]:
    return [WebsitePageOut(**cms.page_out(db, row)) for row in cms.list_pages(db, actor=user)]


@router.get("/pages/{page_id}", response_model=WebsitePageOut)
def get_page(
    db: DbSession, page_id: int, user=Depends(require(Perm.WEBSITE_CONTENT_READ))
) -> WebsitePageOut:
    return WebsitePageOut(**cms.page_out(db, cms.get_page(db, actor=user, page_id=page_id)))


@router.post("/pages", response_model=WebsitePageOut, status_code=status.HTTP_201_CREATED)
def create_page(
    request: Request,
    db: DbSession,
    payload: WebsitePageIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsitePageOut:
    row = cms.create_page(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsitePageOut(**cms.page_out(db, row))


@router.patch("/pages/{page_id}", response_model=WebsitePageOut)
def update_page(
    request: Request,
    db: DbSession,
    page_id: int,
    payload: WebsitePageIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsitePageOut:
    row = cms.update_page(
        db, actor=actor, page_id=page_id, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsitePageOut(**cms.page_out(db, row))


@router.post("/pages/{page_id}/publish", response_model=WebsitePageOut)
def publish_page(
    request: Request,
    db: DbSession,
    page_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_PUBLISH)),
) -> WebsitePageOut:
    row = cms.set_page_status(db, actor=actor, page_id=page_id, status="published", **_ctx(request))
    return WebsitePageOut(**cms.page_out(db, row))


@router.post("/pages/{page_id}/unpublish", response_model=WebsitePageOut)
def unpublish_page(
    request: Request,
    db: DbSession,
    page_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_PUBLISH)),
) -> WebsitePageOut:
    row = cms.set_page_status(db, actor=actor, page_id=page_id, status="draft", **_ctx(request))
    return WebsitePageOut(**cms.page_out(db, row))


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(
    request: Request,
    db: DbSession,
    page_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> Response:
    cms.delete_page(db, actor=actor, page_id=page_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# menus
# --------------------------------------------------------------------------
@router.get("/menus", response_model=list[WebsiteMenuOut])
def list_menus(
    db: DbSession,
    user=Depends(require(Perm.WEBSITE_CONTENT_READ)),
    location: str | None = Query(default=None),
) -> list[WebsiteMenuOut]:
    return [WebsiteMenuOut.model_validate(row) for row in cms.list_menus(db, actor=user, location=location)]


@router.post("/menus", response_model=WebsiteMenuOut, status_code=status.HTTP_201_CREATED)
def create_menu(
    request: Request,
    db: DbSession,
    payload: WebsiteMenuIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteMenuOut:
    row = cms.create_menu(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteMenuOut.model_validate(row)


@router.patch("/menus/{menu_id}", response_model=WebsiteMenuOut)
def update_menu(
    request: Request,
    db: DbSession,
    menu_id: int,
    payload: WebsiteMenuIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteMenuOut:
    row = cms.update_menu(
        db, actor=actor, menu_id=menu_id, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteMenuOut.model_validate(row)


@router.delete("/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu(
    request: Request,
    db: DbSession,
    menu_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> Response:
    cms.delete_menu(db, actor=actor, menu_id=menu_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
@router.get("/companies", response_model=list[WebsiteCompanyOut])
def list_companies(
    db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))
) -> list[WebsiteCompanyOut]:
    out = []
    for row in cms.list_companies(db, actor=user):
        data = WebsiteCompanyOut.model_validate(row).model_dump()
        data["logo_url"] = cms.media_display_url(db, row.logo_media_id)
        out.append(WebsiteCompanyOut(**data))
    return out


@router.post("/companies", response_model=WebsiteCompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    request: Request,
    db: DbSession,
    payload: WebsiteCompanyIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteCompanyOut:
    row = cms.create_company(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteCompanyOut(**cms.company_out(db, row))


@router.patch("/companies/{company_id}", response_model=WebsiteCompanyOut)
def update_company(
    request: Request,
    db: DbSession,
    company_id: int,
    payload: WebsiteCompanyIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteCompanyOut:
    row = cms.update_company(
        db, actor=actor, company_id=company_id, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteCompanyOut(**cms.company_out(db, row))


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    request: Request,
    db: DbSession,
    company_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> Response:
    cms.delete_company(db, actor=actor, company_id=company_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/companies/seed", response_model=dict)
def seed_companies(
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> dict:
    """Idempotently import the approved handoff company dataset."""
    created = cms.seed_companies_from_handoff(db, actor=actor, **_ctx(request))
    return {"created": created}


# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------
@router.get("/services", response_model=list[WebsiteServiceOut])
def list_services(
    db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))
) -> list[WebsiteServiceOut]:
    out = []
    for row in cms.list_services(db, actor=user):
        data = WebsiteServiceOut.model_validate(row).model_dump()
        data["image_url"] = cms.media_display_url(db, row.image_media_id)
        out.append(WebsiteServiceOut(**data))
    return out


@router.post("/services", response_model=WebsiteServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    request: Request,
    db: DbSession,
    payload: WebsiteServiceIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteServiceOut:
    row = cms.create_service(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    data = WebsiteServiceOut.model_validate(row).model_dump()
    data["image_url"] = cms.media_display_url(db, row.image_media_id)
    return WebsiteServiceOut(**data)


@router.patch("/services/{service_id}", response_model=WebsiteServiceOut)
def update_service(
    request: Request,
    db: DbSession,
    service_id: int,
    payload: WebsiteServiceIn,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> WebsiteServiceOut:
    row = cms.update_service(
        db, actor=actor, service_id=service_id, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    data = WebsiteServiceOut.model_validate(row).model_dump()
    data["image_url"] = cms.media_display_url(db, row.image_media_id)
    return WebsiteServiceOut(**data)


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    request: Request,
    db: DbSession,
    service_id: int,
    actor=Depends(require(Perm.WEBSITE_CONTENT_WRITE)),
) -> Response:
    cms.delete_service(db, actor=actor, service_id=service_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# seo
# --------------------------------------------------------------------------
@router.get("/seo", response_model=list[WebsiteSeoOut])
def list_seo(db: DbSession, user=Depends(require(Perm.WEBSITE_CONTENT_READ))) -> list[WebsiteSeoOut]:
    return [WebsiteSeoOut.model_validate(row) for row in cms.list_seo(db, actor=user)]


@router.put("/seo", response_model=WebsiteSeoOut)
def upsert_seo(
    request: Request,
    db: DbSession,
    payload: WebsiteSeoIn,
    actor=Depends(require(Perm.WEBSITE_SETTINGS_MANAGE)),
) -> WebsiteSeoOut:
    row = cms.upsert_seo(
        db, actor=actor, payload=payload.model_dump(exclude_unset=True), **_ctx(request)
    )
    return WebsiteSeoOut.model_validate(row)


@router.delete("/seo/{seo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_seo(
    request: Request,
    db: DbSession,
    seo_id: int,
    actor=Depends(require(Perm.WEBSITE_SETTINGS_MANAGE)),
) -> Response:
    cms.delete_seo(db, actor=actor, seo_id=seo_id, **_ctx(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# revisions
# --------------------------------------------------------------------------
@router.get("/revisions", response_model=list[WebsiteRevisionOut])
def list_revisions(
    db: DbSession,
    user=Depends(require(Perm.WEBSITE_CONTENT_READ)),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebsiteRevisionOut]:
    rows = cms.list_revisions(db, actor=user, entity_type=entity_type, limit=limit)
    return [WebsiteRevisionOut.model_validate(row) for row in rows]
