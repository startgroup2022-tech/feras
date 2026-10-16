"""Pydantic schemas for the Website Management (CMS) API.

Request models validate and bound every field; response models expose only what
the admin UI needs. ``visibility`` and ``status`` are constrained to the enum
membership so an invalid value is rejected at the edge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db.models.enums import ContentStatus, MediaVisibility, SectionKind


def _bounded_str(max_length: int):
    return Field(default=None, max_length=max_length)


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------
class WebsiteSettingsOut(_ORMBase):
    id: int
    site_name_ar: str | None = None
    site_name_en: str | None = None
    description_ar: str | None = None
    description_en: str | None = None
    logo_media_id: int | None = None
    logo_url: str | None = None
    favicon_media_id: int | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    whatsapp_number: str | None = None
    social_links: list | None = None
    header_config: dict | None = None
    footer_config: dict | None = None
    default_language: str
    maintenance_mode: bool
    maintenance_message_ar: str | None = None
    maintenance_message_en: str | None = None
    seo_default_title_ar: str | None = None
    seo_default_title_en: str | None = None
    seo_default_description_ar: str | None = None
    seo_default_description_en: str | None = None
    updated_at: datetime | None = None


class WebsiteSettingsUpdate(BaseModel):
    site_name_ar: str | None = Field(default=None, max_length=200)
    site_name_en: str | None = Field(default=None, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    logo_media_id: int | None = None
    favicon_media_id: int | None = None
    primary_color: str | None = Field(default=None, max_length=16)
    secondary_color: str | None = Field(default=None, max_length=16)
    contact_email: str | None = Field(default=None, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=60)
    whatsapp_number: str | None = Field(default=None, max_length=60)
    social_links: list | None = None
    header_config: dict | None = None
    footer_config: dict | None = None
    default_language: Literal["ar", "en"] | None = None
    maintenance_mode: bool | None = None
    maintenance_message_ar: str | None = Field(default=None, max_length=2000)
    maintenance_message_en: str | None = Field(default=None, max_length=2000)
    seo_default_title_ar: str | None = Field(default=None, max_length=300)
    seo_default_title_en: str | None = Field(default=None, max_length=300)
    seo_default_description_ar: str | None = Field(default=None, max_length=2000)
    seo_default_description_en: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# media
# --------------------------------------------------------------------------
class WebsiteMediaOut(_ORMBase):
    id: int
    storage_key: str
    original_name: str | None = None
    content_type: str | None = None
    byte_size: int
    alt_text_ar: str | None = None
    alt_text_en: str | None = None
    visibility: str
    usage: str | None = None
    uploaded_by_id: int | None = None
    url: str | None = None
    created_at: datetime | None = None


class WebsiteMediaUpdate(BaseModel):
    alt_text_ar: str | None = Field(default=None, max_length=300)
    alt_text_en: str | None = Field(default=None, max_length=300)
    visibility: Literal["public", "private"] | None = None
    usage: str | None = Field(default=None, max_length=60)

    @field_validator("visibility")
    @classmethod
    def _check_visibility(cls, v):
        if v is not None and v not in {m.value for m in MediaVisibility}:
            raise ValueError("visibility must be 'public' or 'private'")
        return v


# --------------------------------------------------------------------------
# slides
# --------------------------------------------------------------------------
class WebsiteSlideOut(_ORMBase):
    id: int
    title_ar: str | None = None
    title_en: str | None = None
    description_ar: str | None = None
    description_en: str | None = None
    image_media_id: int | None = None
    image_url: str | None = None
    mobile_image_media_id: int | None = None
    mobile_image_url: str | None = None
    cta_label_ar: str | None = None
    cta_label_en: str | None = None
    cta_url: str | None = None
    display_order: int
    is_active: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    updated_at: datetime | None = None


class WebsiteSlideIn(BaseModel):
    title_ar: str | None = Field(default=None, max_length=300)
    title_en: str | None = Field(default=None, max_length=300)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    image_media_id: int | None = None
    mobile_image_media_id: int | None = None
    cta_label_ar: str | None = Field(default=None, max_length=120)
    cta_label_en: str | None = Field(default=None, max_length=120)
    cta_url: str | None = Field(default=None, max_length=500)
    display_order: int = 0
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


# --------------------------------------------------------------------------
# pages + sections
# --------------------------------------------------------------------------
class WebsiteSectionOut(_ORMBase):
    id: int
    key: str
    kind: str
    heading_ar: str | None = None
    heading_en: str | None = None
    body_ar: str | None = None
    body_en: str | None = None
    display_order: int
    is_visible: bool


class WebsiteSectionIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    kind: Literal["hero", "cards", "stats", "steps", "cta", "text"] = "text"
    heading_ar: str | None = Field(default=None, max_length=300)
    heading_en: str | None = Field(default=None, max_length=300)
    body_ar: str | None = Field(default=None, max_length=20000)
    body_en: str | None = Field(default=None, max_length=20000)
    display_order: int = 0
    is_visible: bool = True

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v):
        if v not in {k.value for k in SectionKind}:
            raise ValueError("unknown section kind")
        return v


class WebsitePageOut(_ORMBase):
    id: int
    route_key: str
    title_ar: str | None = None
    title_en: str | None = None
    content_ar: str | None = None
    content_en: str | None = None
    slug_ar: str | None = None
    slug_en: str | None = None
    seo_title_ar: str | None = None
    seo_title_en: str | None = None
    seo_description_ar: str | None = None
    seo_description_en: str | None = None
    og_media_id: int | None = None
    og_url: str | None = None
    status: str
    published_at: datetime | None = None
    noindex: bool
    in_sitemap: bool
    sections: list[WebsiteSectionOut] = []
    updated_at: datetime | None = None


class WebsitePageIn(BaseModel):
    route_key: str | None = Field(default=None, max_length=80)
    title_ar: str | None = Field(default=None, max_length=300)
    title_en: str | None = Field(default=None, max_length=300)
    content_ar: str | None = Field(default=None, max_length=20000)
    content_en: str | None = Field(default=None, max_length=20000)
    slug_ar: str | None = Field(default=None, max_length=120)
    slug_en: str | None = Field(default=None, max_length=120)
    seo_title_ar: str | None = Field(default=None, max_length=300)
    seo_title_en: str | None = Field(default=None, max_length=300)
    seo_description_ar: str | None = Field(default=None, max_length=2000)
    seo_description_en: str | None = Field(default=None, max_length=2000)
    og_media_id: int | None = None
    noindex: bool | None = None
    in_sitemap: bool | None = None
    sections: list[WebsiteSectionIn] | None = None


# --------------------------------------------------------------------------
# menus
# --------------------------------------------------------------------------
class WebsiteMenuOut(_ORMBase):
    id: int
    location: str
    label_ar: str | None = None
    label_en: str | None = None
    url: str
    display_order: int
    is_visible: bool
    parent_id: int | None = None


class WebsiteMenuIn(BaseModel):
    location: Literal["header", "footer"] = "header"
    label_ar: str | None = Field(default=None, max_length=120)
    label_en: str | None = Field(default=None, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    display_order: int = 0
    is_visible: bool = True
    parent_id: int | None = None


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
class WebsiteCompanyOut(_ORMBase):
    id: int
    slug: str
    name_ar: str
    name_en: str | None = None
    description_ar: str | None = None
    description_en: str | None = None
    activity_ar: str | None = None
    activity_en: str | None = None
    country: str | None = None
    location_ar: str | None = None
    location_en: str | None = None
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    logo_media_id: int | None = None
    logo_url: str | None = None
    display_order: int
    is_visible: bool
    is_featured: bool


class WebsiteCompanyIn(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    name_ar: str = Field(min_length=1, max_length=300)
    name_en: str | None = Field(default=None, max_length=300)
    description_ar: str | None = Field(default=None, max_length=20000)
    description_en: str | None = Field(default=None, max_length=20000)
    activity_ar: str | None = Field(default=None, max_length=300)
    activity_en: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, max_length=60)
    location_ar: str | None = Field(default=None, max_length=200)
    location_en: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=200)
    whatsapp: str | None = Field(default=None, max_length=60)
    website: str | None = Field(default=None, max_length=500)
    logo_media_id: int | None = None
    display_order: int = 0
    is_visible: bool = True
    is_featured: bool = False


# --------------------------------------------------------------------------
# services
# --------------------------------------------------------------------------
class WebsiteServiceOut(_ORMBase):
    id: int
    slug: str
    title_ar: str | None = None
    title_en: str | None = None
    description_ar: str | None = None
    description_en: str | None = None
    icon: str | None = None
    image_media_id: int | None = None
    image_url: str | None = None
    market: str | None = None
    linked_form_key: str | None = None
    display_order: int
    is_visible: bool


class WebsiteServiceIn(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    title_ar: str | None = Field(default=None, max_length=300)
    title_en: str | None = Field(default=None, max_length=300)
    description_ar: str | None = Field(default=None, max_length=20000)
    description_en: str | None = Field(default=None, max_length=20000)
    icon: str | None = Field(default=None, max_length=60)
    image_media_id: int | None = None
    market: str | None = Field(default=None, max_length=40)
    linked_form_key: str | None = Field(default=None, max_length=80)
    display_order: int = 0
    is_visible: bool = True


# --------------------------------------------------------------------------
# seo
# --------------------------------------------------------------------------
class WebsiteSeoOut(_ORMBase):
    id: int
    route_key: str
    meta_title_ar: str | None = None
    meta_title_en: str | None = None
    meta_description_ar: str | None = None
    meta_description_en: str | None = None
    canonical_url: str | None = None
    og_media_id: int | None = None
    noindex: bool
    in_sitemap: bool


class WebsiteSeoIn(BaseModel):
    route_key: str = Field(min_length=1, max_length=120)
    meta_title_ar: str | None = Field(default=None, max_length=300)
    meta_title_en: str | None = Field(default=None, max_length=300)
    meta_description_ar: str | None = Field(default=None, max_length=2000)
    meta_description_en: str | None = Field(default=None, max_length=2000)
    canonical_url: str | None = Field(default=None, max_length=500)
    og_media_id: int | None = None
    noindex: bool = True
    in_sitemap: bool = True


# --------------------------------------------------------------------------
# revisions
# --------------------------------------------------------------------------
class WebsiteRevisionOut(_ORMBase):
    id: int
    entity_type: str
    entity_id: int | None = None
    action: str
    actor_user_id: int | None = None
    summary: str | None = None
    snapshot: dict | None = None
    created_at: datetime | None = None


class WebsiteCmsOverviewOut(BaseModel):
    """Small dashboard for the CMS landing view."""

    pages: int
    published_pages: int
    slides: int
    active_slides: int
    companies: int
    visible_companies: int
    services: int
    menus: int
    media: int
    public_media: int
    private_media: int
    maintenance_mode: bool
    updated_at: datetime | None = None
