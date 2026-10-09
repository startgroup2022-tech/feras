"""Website Management (CMS) service.

All writes funnel through here so authorization, validation, revision history
and audit are applied in one place -- the API router stays thin.

Two design rules shape the module:

* **Additive, never destructive.** Nothing here touches the Phase 10 lead
  tables, the RBAC catalogue, the operational ``Company`` records or the V2
  content module. The public renderer reads CMS rows *when they exist* and
  otherwise falls back to the built-in V2 content, so an empty CMS is a no-op.
* **Publish is a real gate.** Draft/published state is enforced on the read
  path used by the public site, not merely hidden in the UI.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core import website_media_storage
from backend.core.errors import NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import ContentStatus
from backend.db.models.identity import User
from backend.db.models.website_cms import (
    WebsiteCompany,
    WebsiteContentRevision,
    WebsiteContentSection,
    WebsiteMedia,
    WebsiteMenu,
    WebsitePage,
    WebsiteSeoMeta,
    WebsiteService,
    WebsiteSettings,
    WebsiteSlide,
)
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------
PUBLIC_MEDIA_PATH = "/api/v1/public/website/media"
ADMIN_MEDIA_PATH = "/api/v1/website/media"


def public_media_url(media_id: int | None) -> str | None:
    return f"{PUBLIC_MEDIA_PATH}/{media_id}" if media_id else None


def admin_media_url(media_id: int | None) -> str | None:
    return f"{ADMIN_MEDIA_PATH}/{media_id}/file" if media_id else None


def _media_display_url(db: Session, media_id: int | None) -> str | None:
    """A URL the admin UI can actually load.

    Public assets use the cacheable public path; private assets use the
    authenticated raw endpoint so a preview still works without making the
    asset public.
    """
    if not media_id:
        return None
    media = db.get(WebsiteMedia, media_id)
    if media is None:
        return None
    if media.visibility == "public":
        return public_media_url(media.id)
    return admin_media_url(media.id)


def media_display_url(db: Session, media_id: int | None) -> str | None:
    """Public alias for :func:`_media_display_url` (used by the API/router)."""
    return _media_display_url(db, media_id)


def company_out(db: Session, company: WebsiteCompany) -> dict:
    return {
        "id": company.id,
        "slug": company.slug,
        "name_ar": company.name_ar,
        "name_en": company.name_en,
        "description_ar": company.description_ar,
        "description_en": company.description_en,
        "activity_ar": company.activity_ar,
        "activity_en": company.activity_en,
        "country": company.country,
        "location_ar": company.location_ar,
        "location_en": company.location_en,
        "phone": company.phone,
        "email": company.email,
        "whatsapp": company.whatsapp,
        "website": company.website,
        "logo_media_id": company.logo_media_id,
        "logo_url": _media_display_url(db, company.logo_media_id),
        "display_order": company.display_order,
        "is_visible": company.is_visible,
        "is_featured": company.is_featured,
    }


def service_out(db: Session, service: WebsiteService) -> dict:
    return {
        "id": service.id,
        "slug": service.slug,
        "title_ar": service.title_ar,
        "title_en": service.title_en,
        "description_ar": service.description_ar,
        "description_en": service.description_en,
        "icon": service.icon,
        "image_media_id": service.image_media_id,
        "image_url": _media_display_url(db, service.image_media_id),
        "market": service.market,
        "linked_form_key": service.linked_form_key,
        "display_order": service.display_order,
        "is_visible": service.is_visible,
    }


def slide_out(db: Session, slide: WebsiteSlide) -> dict:
    """Public alias for the slide serializer."""
    return _slide_out(db, slide)


# --------------------------------------------------------------------------
# revisions
# --------------------------------------------------------------------------
def _revision(
    db: Session,
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    actor: User | None,
    snapshot: dict | None,
    summary: str | None = None,
) -> WebsiteContentRevision:
    row = WebsiteContentRevision(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor.id if actor else None,
        snapshot=snapshot,
        summary=summary,
    )
    db.add(row)
    db.flush()
    return row


def list_revisions(
    db: Session, *, actor: User, entity_type: str | None = None, limit: int = 50
) -> list[WebsiteContentRevision]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    stmt = select(WebsiteContentRevision).order_by(WebsiteContentRevision.id.desc())
    if entity_type:
        stmt = stmt.where(WebsiteContentRevision.entity_type == entity_type)
    return list(db.execute(stmt.limit(max(1, min(limit, 200)))).scalars())


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------
def get_settings(db: Session) -> WebsiteSettings:
    """Return the singleton settings row, creating a default on first use."""
    row = db.get(WebsiteSettings, 1)
    if row is None:
        row = WebsiteSettings(id=1, default_language="ar", maintenance_mode=False)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def settings_out(db: Session, row: WebsiteSettings) -> dict:
    data = {
        column: getattr(row, column)
        for column in (
            "id",
            "site_name_ar",
            "site_name_en",
            "description_ar",
            "description_en",
            "logo_media_id",
            "favicon_media_id",
            "primary_color",
            "secondary_color",
            "contact_email",
            "contact_phone",
            "whatsapp_number",
            "social_links",
            "header_config",
            "footer_config",
            "default_language",
            "maintenance_mode",
            "maintenance_message_ar",
            "maintenance_message_en",
            "seo_default_title_ar",
            "seo_default_title_en",
            "seo_default_description_ar",
            "seo_default_description_en",
            "updated_at",
        )
    }
    data["logo_url"] = _media_display_url(db, row.logo_media_id)
    data["favicon_url"] = _media_display_url(db, row.favicon_media_id)
    return data


def update_settings(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteSettings:
    require_permission(actor, Perm.WEBSITE_SETTINGS_MANAGE)
    row = get_settings(db)
    allowed = {
        "site_name_ar",
        "site_name_en",
        "description_ar",
        "description_en",
        "logo_media_id",
        "favicon_media_id",
        "primary_color",
        "secondary_color",
        "contact_email",
        "contact_phone",
        "whatsapp_number",
        "social_links",
        "header_config",
        "footer_config",
        "default_language",
        "maintenance_mode",
        "maintenance_message_ar",
        "maintenance_message_en",
        "seo_default_title_ar",
        "seo_default_title_en",
        "seo_default_description_ar",
        "seo_default_description_en",
    }
    for key, value in payload.items():
        if key in allowed and value is not None:
            if key == "default_language" and value not in ("ar", "en"):
                raise ValidationError("default_language must be 'ar' or 'en'.")
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db,
        entity_type="settings",
        entity_id=row.id,
        action="update",
        actor=actor,
        snapshot={"keys": sorted(k for k in payload if k in allowed)},
        summary="Website settings updated",
    )
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.WEBSITE_SETTINGS_UPDATED,
        actor_user_id=actor.id,
        entity_type="website_settings",
        entity_id=row.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"keys": sorted(k for k in payload if k in allowed)},
    )
    return row


# --------------------------------------------------------------------------
# media
# --------------------------------------------------------------------------
def record_media(
    db: Session,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    visibility: str = "public",
    usage: str | None = None,
    alt_text_ar: str | None = None,
    alt_text_en: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteMedia:
    require_permission(actor, Perm.WEBSITE_MEDIA_MANAGE)
    if visibility not in ("public", "private"):
        raise ValidationError("visibility must be 'public' or 'private'.")

    extension = website_media_storage.validate_media(
        filename=filename, content_type=content_type, size=len(data)
    )
    key = website_media_storage.store_media_bytes(data=data, extension=extension)
    media = WebsiteMedia(
        storage_key=key,
        original_name=(filename or "")[:255] or None,
        content_type=content_type,
        byte_size=len(data),
        visibility=visibility,
        usage=usage,
        alt_text_ar=alt_text_ar,
        alt_text_en=alt_text_en,
        uploaded_by_id=actor.id,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    audit_service.record(
        db,
        action=AuditAction.WEBSITE_MEDIA_UPLOADED,
        actor_user_id=actor.id,
        entity_type="website_media",
        entity_id=media.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"content_type": content_type, "bytes": len(data), "visibility": visibility},
    )
    return media


def list_media(
    db: Session, *, actor: User, visibility: str | None = None, usage: str | None = None
) -> list[WebsiteMedia]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    stmt = select(WebsiteMedia).order_by(WebsiteMedia.id.desc())
    if visibility:
        stmt = stmt.where(WebsiteMedia.visibility == visibility)
    if usage:
        stmt = stmt.where(WebsiteMedia.usage == usage)
    return list(db.execute(stmt).scalars())


def media_out(db: Session, media: WebsiteMedia) -> dict:
    return {
        "id": media.id,
        "storage_key": media.storage_key,
        "original_name": media.original_name,
        "content_type": media.content_type,
        "byte_size": media.byte_size,
        "alt_text_ar": media.alt_text_ar,
        "alt_text_en": media.alt_text_en,
        "visibility": media.visibility,
        "usage": media.usage,
        "uploaded_by_id": media.uploaded_by_id,
        "url": _media_display_url(db, media.id),
        "created_at": media.created_at,
    }


def update_media(
    db: Session,
    *,
    actor: User,
    media_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteMedia:
    require_permission(actor, Perm.WEBSITE_MEDIA_MANAGE)
    media = db.get(WebsiteMedia, media_id)
    if media is None:
        raise NotFoundError("Media asset not found.")
    previous_visibility = media.visibility
    for key in ("alt_text_ar", "alt_text_en", "visibility", "usage"):
        if key in payload and payload[key] is not None:
            if key == "visibility" and payload[key] not in ("public", "private"):
                raise ValidationError("visibility must be 'public' or 'private'.")
            setattr(media, key, payload[key])
    media.updated_at = utcnow()
    db.add(media)
    db.commit()
    db.refresh(media)
    if previous_visibility != media.visibility:
        audit_service.record(
            db,
            action=AuditAction.WEBSITE_MEDIA_VISIBILITY_CHANGED,
            actor_user_id=actor.id,
            entity_type="website_media",
            entity_id=media.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"from": previous_visibility, "to": media.visibility},
        )
    return media


def delete_media(
    db: Session,
    *,
    actor: User,
    media_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    require_permission(actor, Perm.WEBSITE_MEDIA_MANAGE)
    media = db.get(WebsiteMedia, media_id)
    if media is None:
        raise NotFoundError("Media asset not found.")
    key = media.storage_key
    db.delete(media)
    db.commit()
    website_media_storage.delete_media_bytes(key)
    audit_service.record(
        db,
        action=AuditAction.WEBSITE_MEDIA_DELETED,
        actor_user_id=actor.id,
        entity_type="website_media",
        entity_id=media_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"storage_key": key},
    )


def resolve_media_for_public(db: Session, media_id: int):
    media = db.get(WebsiteMedia, media_id)
    if media is None or media.visibility != "public":
        raise NotFoundError("Media asset not found.")
    return website_media_storage.resolve_media_path(media.storage_key), media.content_type


def resolve_media_for_admin(db: Session, *, actor: User, media_id: int):
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    media = db.get(WebsiteMedia, media_id)
    if media is None:
        raise NotFoundError("Media asset not found.")
    return website_media_storage.resolve_media_path(media.storage_key), media.content_type


# --------------------------------------------------------------------------
# slides
# --------------------------------------------------------------------------
def _slide_out(db: Session, slide: WebsiteSlide) -> dict:
    return {
        "id": slide.id,
        "title_ar": slide.title_ar,
        "title_en": slide.title_en,
        "description_ar": slide.description_ar,
        "description_en": slide.description_en,
        "image_media_id": slide.image_media_id,
        "image_url": _media_display_url(db, slide.image_media_id),
        "mobile_image_media_id": slide.mobile_image_media_id,
        "mobile_image_url": _media_display_url(db, slide.mobile_image_media_id),
        "cta_label_ar": slide.cta_label_ar,
        "cta_label_en": slide.cta_label_en,
        "cta_url": slide.cta_url,
        "display_order": slide.display_order,
        "is_active": slide.is_active,
        "starts_at": slide.starts_at,
        "ends_at": slide.ends_at,
        "updated_at": slide.updated_at,
    }


def list_slides(db: Session, *, actor: User) -> list[WebsiteSlide]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    return list(
        db.execute(select(WebsiteSlide).order_by(WebsiteSlide.display_order, WebsiteSlide.id)).scalars()
    )


def create_slide(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsiteSlide:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    slide = WebsiteSlide(**{k: v for k, v in payload.items() if v is not None})
    db.add(slide)
    db.commit()
    db.refresh(slide)
    _revision(
        db, entity_type="slide", entity_id=slide.id, action="create",
        actor=actor, snapshot={"id": slide.id}, summary="Slide created",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
        entity_type="website_slide", entity_id=slide.id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )
    return slide


def update_slide(
    db: Session, *, actor: User, slide_id: int, payload: dict, ip_address=None, user_agent=None
) -> WebsiteSlide:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    slide = db.get(WebsiteSlide, slide_id)
    if slide is None:
        raise NotFoundError("Slide not found.")
    for key, value in payload.items():
        if hasattr(slide, key) and value is not None:
            setattr(slide, key, value)
    slide.updated_at = utcnow()
    db.add(slide)
    db.commit()
    db.refresh(slide)
    _revision(
        db, entity_type="slide", entity_id=slide.id, action="update",
        actor=actor, snapshot={"id": slide.id}, summary="Slide updated",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_UPDATED, actor_user_id=actor.id,
        entity_type="website_slide", entity_id=slide.id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )
    return slide


def delete_slide(
    db: Session, *, actor: User, slide_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    slide = db.get(WebsiteSlide, slide_id)
    if slide is None:
        raise NotFoundError("Slide not found.")
    db.delete(slide)
    db.commit()
    _revision(
        db, entity_type="slide", entity_id=slide_id, action="delete",
        actor=actor, snapshot=None, summary="Slide deleted",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_DELETED, actor_user_id=actor.id,
        entity_type="website_slide", entity_id=slide_id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------
def _section_out(section: WebsiteContentSection) -> dict:
    return {
        "id": section.id,
        "key": section.key,
        "kind": section.kind,
        "heading_ar": section.heading_ar,
        "heading_en": section.heading_en,
        "body_ar": section.body_ar,
        "body_en": section.body_en,
        "display_order": section.display_order,
        "is_visible": section.is_visible,
    }


def page_out(db: Session, page: WebsitePage) -> dict:
    return {
        "id": page.id,
        "route_key": page.route_key,
        "title_ar": page.title_ar,
        "title_en": page.title_en,
        "content_ar": page.content_ar,
        "content_en": page.content_en,
        "slug_ar": page.slug_ar,
        "slug_en": page.slug_en,
        "seo_title_ar": page.seo_title_ar,
        "seo_title_en": page.seo_title_en,
        "seo_description_ar": page.seo_description_ar,
        "seo_description_en": page.seo_description_en,
        "og_media_id": page.og_media_id,
        "og_url": _media_display_url(db, page.og_media_id),
        "status": page.status,
        "published_at": page.published_at,
        "noindex": page.noindex,
        "in_sitemap": page.in_sitemap,
        "sections": [_section_out(s) for s in page.sections],
        "updated_at": page.updated_at,
    }


def list_pages(db: Session, *, actor: User) -> list[WebsitePage]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    return list(db.execute(select(WebsitePage).order_by(WebsitePage.route_key)).scalars())


def get_page(db: Session, *, actor: User, page_id: int) -> WebsitePage:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    page = db.get(WebsitePage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    return page


def _apply_sections(db: Session, page: WebsitePage, sections: list[dict]) -> None:
    page.sections.clear()
    db.flush()
    for index, item in enumerate(sections):
        page.sections.append(
            WebsiteContentSection(
                key=item["key"],
                kind=item.get("kind", "text"),
                heading_ar=item.get("heading_ar"),
                heading_en=item.get("heading_en"),
                body_ar=item.get("body_ar"),
                body_en=item.get("body_en"),
                display_order=item.get("display_order", index),
                is_visible=item.get("is_visible", True),
            )
        )


def create_page(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsitePage:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    route_key = payload.get("route_key")
    if not route_key:
        raise ValidationError("A route key is required.")
    existing = db.execute(
        select(WebsitePage).where(WebsitePage.route_key == route_key)
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError("A page with this route key already exists.")
    sections = payload.pop("sections", None) or []
    page = WebsitePage(**{k: v for k, v in payload.items() if v is not None})
    page.status = ContentStatus.DRAFT.value
    db.add(page)
    db.flush()
    _apply_sections(db, page, sections)
    db.commit()
    db.refresh(page)
    _revision(
        db, entity_type="page", entity_id=page.id, action="create",
        actor=actor, snapshot={"route_key": page.route_key}, summary="Page created",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
        entity_type="website_page", entity_id=page.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"route_key": page.route_key},
    )
    return page


def update_page(
    db: Session, *, actor: User, page_id: int, payload: dict, ip_address=None, user_agent=None
) -> WebsitePage:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    page = db.get(WebsitePage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    sections = payload.pop("sections", None)
    for key, value in payload.items():
        if (
            hasattr(page, key)
            and value is not None
            and key not in ("status", "route_key")
        ):
            setattr(page, key, value)
    if sections is not None:
        _apply_sections(db, page, sections)
    page.updated_at = utcnow()
    db.add(page)
    db.commit()
    db.refresh(page)
    _revision(
        db, entity_type="page", entity_id=page.id, action="update",
        actor=actor, snapshot={"route_key": page.route_key}, summary="Page updated",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_UPDATED, actor_user_id=actor.id,
        entity_type="website_page", entity_id=page.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"route_key": page.route_key},
    )
    return page


def set_page_status(
    db: Session, *, actor: User, page_id: int, status: str, ip_address=None, user_agent=None
) -> WebsitePage:
    require_permission(actor, Perm.WEBSITE_CONTENT_PUBLISH)
    if status not in {s.value for s in ContentStatus}:
        raise ValidationError("status must be 'draft' or 'published'.")
    page = db.get(WebsitePage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    page.status = status
    page.published_at = utcnow() if status == ContentStatus.PUBLISHED.value else None
    page.updated_at = utcnow()
    db.add(page)
    db.commit()
    db.refresh(page)
    action = (
        AuditAction.WEBSITE_CONTENT_PUBLISHED
        if status == ContentStatus.PUBLISHED.value
        else AuditAction.WEBSITE_CONTENT_UNPUBLISHED
    )
    _revision(
        db, entity_type="page", entity_id=page.id, action=status,
        actor=actor, snapshot={"route_key": page.route_key}, summary=f"Page {status}",
    )
    db.commit()
    audit_service.record(
        db, action=action, actor_user_id=actor.id, entity_type="website_page",
        entity_id=page.id, ip_address=ip_address, user_agent=user_agent,
        metadata={"route_key": page.route_key},
    )
    return page


def delete_page(
    db: Session, *, actor: User, page_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    page = db.get(WebsitePage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    db.delete(page)
    db.commit()
    _revision(
        db, entity_type="page", entity_id=page_id, action="delete",
        actor=actor, snapshot=None, summary="Page deleted",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_DELETED, actor_user_id=actor.id,
        entity_type="website_page", entity_id=page_id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )


# --------------------------------------------------------------------------
# menus
# --------------------------------------------------------------------------
def _validate_menu_url(url: str) -> str:
    """Allow internal paths and http(s) links only.

    Rejects control characters and dangerous schemes (``javascript:``,
    ``data:``, ``vbscript:``), which is what stops a menu entry from becoming
    a stored XSS or an open redirect.
    """
    url = (url or "").strip()
    if not url or any(ord(ch) < 32 for ch in url):
        raise ValidationError("A valid menu URL is required.")
    lower = url.lower()
    if lower.startswith("javascript:") or lower.startswith("data:") or lower.startswith("vbscript:"):
        raise ValidationError("This URL scheme is not allowed.")
    if url.startswith("//"):
        raise ValidationError("Protocol-relative URLs are not allowed.")
    if not (url.startswith("/") or lower.startswith("http://") or lower.startswith("https://")):
        raise ValidationError("Menu URLs must be an internal path or an http(s) link.")
    return url


def list_menus(db: Session, *, actor: User, location: str | None = None) -> list[WebsiteMenu]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    stmt = select(WebsiteMenu).order_by(WebsiteMenu.display_order, WebsiteMenu.id)
    if location:
        stmt = stmt.where(WebsiteMenu.location == location)
    return list(db.execute(stmt).scalars())


def create_menu(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsiteMenu:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    payload["url"] = _validate_menu_url(payload.get("url", ""))
    row = WebsiteMenu(**{k: v for k, v in payload.items() if v is not None})
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="menu", entity_id=row.id, action="create",
        actor=actor, snapshot={"url": row.url}, summary="Menu item created",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
        entity_type="website_menu", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )
    return row


def update_menu(
    db: Session, *, actor: User, menu_id: int, payload: dict, ip_address=None, user_agent=None
) -> WebsiteMenu:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteMenu, menu_id)
    if row is None:
        raise NotFoundError("Menu item not found.")
    if "url" in payload and payload["url"] is not None:
        payload["url"] = _validate_menu_url(payload["url"])
    for key, value in payload.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="menu", entity_id=row.id, action="update",
        actor=actor, snapshot={"url": row.url}, summary="Menu item updated",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_UPDATED, actor_user_id=actor.id,
        entity_type="website_menu", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )
    return row


def delete_menu(
    db: Session, *, actor: User, menu_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteMenu, menu_id)
    if row is None:
        raise NotFoundError("Menu item not found.")
    db.delete(row)
    db.commit()
    _revision(
        db, entity_type="menu", entity_id=menu_id, action="delete",
        actor=actor, snapshot=None, summary="Menu item deleted",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_DELETED, actor_user_id=actor.id,
        entity_type="website_menu", entity_id=menu_id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
def list_companies(db: Session, *, actor: User) -> list[WebsiteCompany]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    return list(
        db.execute(select(WebsiteCompany).order_by(WebsiteCompany.display_order, WebsiteCompany.id)).scalars()
    )


def create_company(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsiteCompany:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    slug = payload.get("slug")
    if slug:
        existing = db.execute(
            select(WebsiteCompany).where(WebsiteCompany.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError("A company with this slug already exists.")
    row = WebsiteCompany(**{k: v for k, v in payload.items() if v is not None})
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="company", entity_id=row.id, action="create",
        actor=actor, snapshot={"slug": row.slug}, summary="Company created",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
        entity_type="website_company", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"slug": row.slug},
    )
    return row


def update_company(
    db: Session, *, actor: User, company_id: int, payload: dict, ip_address=None, user_agent=None
) -> WebsiteCompany:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteCompany, company_id)
    if row is None:
        raise NotFoundError("Company not found.")
    for key, value in payload.items():
        if hasattr(row, key) and value is not None and key != "slug":
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="company", entity_id=row.id, action="update",
        actor=actor, snapshot={"slug": row.slug}, summary="Company updated",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_UPDATED, actor_user_id=actor.id,
        entity_type="website_company", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"slug": row.slug},
    )
    return row


def delete_company(
    db: Session, *, actor: User, company_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteCompany, company_id)
    if row is None:
        raise NotFoundError("Company not found.")
    db.delete(row)
    db.commit()
    _revision(
        db, entity_type="company", entity_id=company_id, action="delete",
        actor=actor, snapshot=None, summary="Company deleted",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_DELETED, actor_user_id=actor.id,
        entity_type="website_company", entity_id=company_id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )


def seed_companies_from_handoff(
    db: Session, *, actor: User, ip_address=None, user_agent=None
) -> int:
    """Idempotently import the canonical handoff companies.

    Only missing slugs are inserted, so a re-run never overwrites an editor's
    changes. Returns the number of rows created.
    """
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    from backend.website import group_companies

    existing = {slug for (slug,) in db.execute(select(WebsiteCompany.slug)).all()}
    created = 0
    for company in group_companies.ordered():
        if company["id"] in existing:
            continue
        db.add(
            WebsiteCompany(
                slug=company["id"],
                name_ar=company["name_ar"],
                name_en=company.get("name_en"),
                description_ar=company.get("about_ar"),
                description_en=company.get("about_en"),
                activity_ar=company.get("card_ar"),
                activity_en=company.get("card_en"),
                country=company.get("country"),
                location_ar=company.get("area_ar"),
                location_en=company.get("area_en"),
                phone=company.get("phone"),
                email=company.get("email"),
                whatsapp=company.get("whatsapp"),
                website=company.get("website"),
                display_order=company.get("order", 0),
                is_visible=True,
            )
        )
        created += 1
    db.commit()
    if created:
        _revision(
            db, entity_type="company", entity_id=None, action="create",
            actor=actor, snapshot={"seeded": created}, summary="Seeded handoff companies",
        )
        db.commit()
        audit_service.record(
            db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
            entity_type="website_company", entity_id=None, ip_address=ip_address,
            user_agent=user_agent, metadata={"seeded": created},
        )
    return created


# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------
def list_services(db: Session, *, actor: User) -> list[WebsiteService]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    return list(
        db.execute(select(WebsiteService).order_by(WebsiteService.display_order, WebsiteService.id)).scalars()
    )


def create_service(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsiteService:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    slug = payload.get("slug")
    if slug:
        existing = db.execute(
            select(WebsiteService).where(WebsiteService.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValidationError("A service with this slug already exists.")
    row = WebsiteService(**{k: v for k, v in payload.items() if v is not None})
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="service", entity_id=row.id, action="create",
        actor=actor, snapshot={"slug": row.slug}, summary="Service created",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_CREATED, actor_user_id=actor.id,
        entity_type="website_service", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"slug": row.slug},
    )
    return row


def update_service(
    db: Session, *, actor: User, service_id: int, payload: dict, ip_address=None, user_agent=None
) -> WebsiteService:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteService, service_id)
    if row is None:
        raise NotFoundError("Service not found.")
    for key, value in payload.items():
        if hasattr(row, key) and value is not None and key != "slug":
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="service", entity_id=row.id, action="update",
        actor=actor, snapshot={"slug": row.slug}, summary="Service updated",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_UPDATED, actor_user_id=actor.id,
        entity_type="website_service", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"slug": row.slug},
    )
    return row


def delete_service(
    db: Session, *, actor: User, service_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_CONTENT_WRITE)
    row = db.get(WebsiteService, service_id)
    if row is None:
        raise NotFoundError("Service not found.")
    db.delete(row)
    db.commit()
    _revision(
        db, entity_type="service", entity_id=service_id, action="delete",
        actor=actor, snapshot=None, summary="Service deleted",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_CONTENT_DELETED, actor_user_id=actor.id,
        entity_type="website_service", entity_id=service_id, ip_address=ip_address,
        user_agent=user_agent, metadata={},
    )


# --------------------------------------------------------------------------
# seo
# --------------------------------------------------------------------------
def list_seo(db: Session, *, actor: User) -> list[WebsiteSeoMeta]:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)
    return list(db.execute(select(WebsiteSeoMeta).order_by(WebsiteSeoMeta.route_key)).scalars())


def upsert_seo(
    db: Session, *, actor: User, payload: dict, ip_address=None, user_agent=None
) -> WebsiteSeoMeta:
    require_permission(actor, Perm.WEBSITE_SETTINGS_MANAGE)
    route_key = payload.get("route_key")
    if not route_key:
        raise ValidationError("A route key is required.")
    row = db.execute(
        select(WebsiteSeoMeta).where(WebsiteSeoMeta.route_key == route_key)
    ).scalar_one_or_none()
    if row is None:
        row = WebsiteSeoMeta(route_key=route_key)
        db.add(row)
    for key, value in payload.items():
        if key != "route_key" and hasattr(row, key) and value is not None:
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    _revision(
        db, entity_type="seo", entity_id=row.id, action="update",
        actor=actor, snapshot={"route_key": route_key}, summary="SEO metadata saved",
    )
    db.commit()
    audit_service.record(
        db, action=AuditAction.WEBSITE_SETTINGS_UPDATED, actor_user_id=actor.id,
        entity_type="website_seo", entity_id=row.id, ip_address=ip_address,
        user_agent=user_agent, metadata={"route_key": route_key},
    )
    return row


def delete_seo(
    db: Session, *, actor: User, seo_id: int, ip_address=None, user_agent=None
) -> None:
    require_permission(actor, Perm.WEBSITE_SETTINGS_MANAGE)
    row = db.get(WebsiteSeoMeta, seo_id)
    if row is None:
        raise NotFoundError("SEO entry not found.")
    db.delete(row)
    db.commit()
    _revision(
        db, entity_type="seo", entity_id=seo_id, action="delete",
        actor=actor, snapshot=None, summary="SEO metadata deleted",
    )
    db.commit()


# --------------------------------------------------------------------------
# overview
# --------------------------------------------------------------------------
def overview(db: Session, *, actor: User) -> dict:
    require_permission(actor, Perm.WEBSITE_CONTENT_READ)

    def count(model, *conditions) -> int:
        stmt = select(func.count()).select_from(model)
        for condition in conditions:
            stmt = stmt.where(condition)
        return int(db.execute(stmt).scalar_one())

    row = get_settings(db)
    return {
        "pages": count(WebsitePage),
        "published_pages": count(WebsitePage, WebsitePage.status == ContentStatus.PUBLISHED.value),
        "slides": count(WebsiteSlide),
        "active_slides": count(WebsiteSlide, WebsiteSlide.is_active.is_(True)),
        "companies": count(WebsiteCompany),
        "visible_companies": count(WebsiteCompany, WebsiteCompany.is_visible.is_(True)),
        "services": count(WebsiteService),
        "menus": count(WebsiteMenu),
        "media": count(WebsiteMedia),
        "public_media": count(WebsiteMedia, WebsiteMedia.visibility == "public"),
        "private_media": count(WebsiteMedia, WebsiteMedia.visibility == "private"),
        "maintenance_mode": row.maintenance_mode,
        "updated_at": row.updated_at,
    }


# --------------------------------------------------------------------------
# public read helpers (used by the renderer; no actor -> published only)
# --------------------------------------------------------------------------
def published_page(db: Session, route_key: str) -> WebsitePage | None:
    return db.execute(
        select(WebsitePage).where(
            WebsitePage.route_key == route_key,
            WebsitePage.status == ContentStatus.PUBLISHED.value,
        )
    ).scalar_one_or_none()


def list_published_pages(db: Session) -> list[WebsitePage]:
    """Every published page, for the public renderer's context."""
    return list(
        db.execute(
            select(WebsitePage).where(WebsitePage.status == ContentStatus.PUBLISHED.value)
        ).scalars()
    )


def active_slides(db: Session) -> list[WebsiteSlide]:
    now = utcnow()
    rows = db.execute(
        select(WebsiteSlide).where(WebsiteSlide.is_active.is_(True)).order_by(WebsiteSlide.display_order)
    ).scalars()
    result = []
    for slide in rows:
        if slide.starts_at is not None and slide.starts_at > now:
            continue
        if slide.ends_at is not None and slide.ends_at < now:
            continue
        result.append(slide)
    return result


def visible_companies(db: Session) -> list[WebsiteCompany]:
    return list(
        db.execute(
            select(WebsiteCompany)
            .where(WebsiteCompany.is_visible.is_(True))
            .order_by(WebsiteCompany.display_order, WebsiteCompany.id)
        ).scalars()
    )


def visible_services(db: Session) -> list[WebsiteService]:
    return list(
        db.execute(
            select(WebsiteService)
            .where(WebsiteService.is_visible.is_(True))
            .order_by(WebsiteService.display_order, WebsiteService.id)
        ).scalars()
    )


def menu_items(db: Session, location: str) -> list[WebsiteMenu]:
    return list(
        db.execute(
            select(WebsiteMenu)
            .where(WebsiteMenu.location == location, WebsiteMenu.is_visible.is_(True))
            .order_by(WebsiteMenu.display_order, WebsiteMenu.id)
        ).scalars()
    )


def seo_for_route(db: Session, route_key: str) -> WebsiteSeoMeta | None:
    return db.execute(
        select(WebsiteSeoMeta).where(WebsiteSeoMeta.route_key == route_key)
    ).scalar_one_or_none()


__all__ = [
    "PUBLIC_MEDIA_PATH",
    "ADMIN_MEDIA_PATH",
    "active_slides",
    "admin_media_url",
    "create_company",
    "create_menu",
    "create_page",
    "create_service",
    "create_slide",
    "delete_company",
    "delete_media",
    "delete_menu",
    "delete_page",
    "delete_seo",
    "delete_service",
    "delete_slide",
    "get_page",
    "get_settings",
    "list_companies",
    "list_media",
    "list_menus",
    "list_pages",
    "list_revisions",
    "list_seo",
    "list_services",
    "list_slides",
    "media_out",
    "menu_items",
    "overview",
    "page_out",
    "public_media_url",
    "published_page",
    "record_media",
    "resolve_media_for_admin",
    "resolve_media_for_public",
    "seo_for_route",
    "seed_companies_from_handoff",
    "set_page_status",
    "settings_out",
    "update_company",
    "update_media",
    "update_menu",
    "update_page",
    "update_service",
    "update_settings",
    "update_slide",
    "upsert_seo",
    "visible_companies",
    "visible_services",
]
