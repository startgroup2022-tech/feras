"""Public-site CMS context.

Loads the *published/visible* CMS rows once per page render and exposes them as
a small immutable context the renderer reads. Everything is best-effort: any
failure returns an empty context so a marketing page can never 500 because the
CMS tables are missing, empty or temporarily unreadable. An empty context makes
the renderer fall back to the built-in V2 content, which is the whole point of
the additive design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.services import website_cms_service as cms


@dataclass
class CmsContext:
    settings: dict | None = None
    slides: list = field(default_factory=list)
    companies: list = field(default_factory=list)
    services: list = field(default_factory=list)
    header_menu: list = field(default_factory=list)
    footer_menu: list = field(default_factory=list)
    pages: dict = field(default_factory=dict)

    @property
    def has_slides(self) -> bool:
        return bool(self.slides)

    @property
    def has_menu(self) -> bool:
        return bool(self.header_menu) or bool(self.footer_menu)


def _slide_view(db: Session, slide) -> dict:
    return {
        "id": slide.id,
        "title": {"ar": slide.title_ar, "en": slide.title_en},
        "description": {"ar": slide.description_ar, "en": slide.description_en},
        "image_url": cms.media_display_url(db, slide.image_media_id),
        "mobile_image_url": cms.media_display_url(db, slide.mobile_image_media_id),
        "cta_label": {"ar": slide.cta_label_ar, "en": slide.cta_label_en},
        "cta_url": slide.cta_url,
    }


def _company_view(db: Session, company) -> dict:
    return {
        "slug": company.slug,
        "name": {"ar": company.name_ar, "en": company.name_en or company.name_ar},
        "description": {
            "ar": company.description_ar,
            "en": company.description_en or company.description_ar,
        },
        "activity": {"ar": company.activity_ar, "en": company.activity_en},
        "location": {"ar": company.location_ar, "en": company.location_en},
        "country": company.country,
        "phone": company.phone,
        "email": company.email,
        "whatsapp": company.whatsapp,
        "website": company.website,
        "logo_url": cms.media_display_url(db, company.logo_media_id),
    }


def _menu_view(item) -> dict:
    return {
        "label": {"ar": item.label_ar, "en": item.label_en},
        "url": item.url,
    }


def load(db: Session) -> CmsContext:
    """Build the public CMS context, degrading to empty on any failure."""
    try:
        settings_row = cms.get_settings(db)
        settings = {
            "site_name": {"ar": settings_row.site_name_ar, "en": settings_row.site_name_en},
            "description": {
                "ar": settings_row.description_ar,
                "en": settings_row.description_en,
            },
            "logo_url": cms.media_display_url(db, settings_row.logo_media_id)
            or cms.media_display_url(db, settings_row.favicon_media_id),
            "favicon_url": cms.media_display_url(db, settings_row.favicon_media_id),
            "contact_email": settings_row.contact_email,
            "contact_phone": settings_row.contact_phone,
            "whatsapp_number": settings_row.whatsapp_number,
            "maintenance_mode": settings_row.maintenance_mode,
        }
        slides = [_slide_view(db, s) for s in cms.active_slides(db)]
        companies = [_company_view(db, c) for c in cms.visible_companies(db)]
        services = cms.visible_services(db)
        header_menu = [_menu_view(m) for m in cms.menu_items(db, "header")]
        footer_menu = [_menu_view(m) for m in cms.menu_items(db, "footer")]
        pages = {}
        for page in cms.list_published_pages(db):
            pages[page.route_key] = {
                "title": {"ar": page.title_ar, "en": page.title_en},
                "content": {"ar": page.content_ar, "en": page.content_en},
                "sections": [
                    {
                        "kind": s.kind,
                        "heading": {"ar": s.heading_ar, "en": s.heading_en},
                        "body": {"ar": s.body_ar, "en": s.body_en},
                    }
                    for s in page.sections
                    if s.is_visible
                ],
            }
        return CmsContext(
            settings=settings,
            slides=slides,
            companies=companies,
            services=[
                {
                    "slug": s.slug,
                    "title": {"ar": s.title_ar, "en": s.title_en},
                    "description": {"ar": s.description_ar, "en": s.description_en},
                    "icon": s.icon,
                    "market": s.market,
                }
                for s in services
            ],
            header_menu=header_menu,
            footer_menu=footer_menu,
            pages=pages,
        )
    except Exception:  # noqa: BLE001 - a public page must never break on CMS
        return CmsContext()


def maintenance(db: Session) -> tuple[bool, str | None, str | None]:
    """Return ``(on, message_ar, message_en)`` for the maintenance notice.

    Read separately from the full context so ``main.py`` can decide to short
    -circuit the public site without loading slides or menus.
    """
    try:
        row = cms.get_settings(db)
        return row.maintenance_mode, row.maintenance_message_ar, row.maintenance_message_en
    except Exception:  # noqa: BLE001
        return False, None, None


__all__ = ["CmsContext", "load", "maintenance"]
