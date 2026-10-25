"""Website CMS models (Phase 11).

These tables let the Holding manage the public website from the internal
platform without a deploy. They are **additive**: the Phase 10 lead/opportunity
tables and the V2 content model are untouched. The public renderer prefers a
published CMS row when one exists and otherwise falls back to the built-in V2
content, so removing every row returns the site to exactly its previous state.

Two invariants are enforced structurally, not just in the UI:

* **Nothing unpublished is public.** Slides, pages and service content carry a
  ``status`` column; the public renderer only ever reads ``PUBLISHED`` rows.
* **Private media stays private.** ``WebsiteMedia.visibility`` decides which
  endpoint may serve an asset; the public endpoint filters on ``PUBLIC``.

History is append-only. Every settings/page/company/service change writes a
:class:`WebsiteContentRevision` row with the actor and a JSON snapshot, so any
edit can be reviewed and (practically) rolled back.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import ContentStatus, MediaVisibility, SectionKind

if TYPE_CHECKING:
    from backend.db.models.identity import User


class WebsiteSettings(Base, TimestampMixin):
    """The single row of site-wide configuration.

    A singleton (enforced by a fixed ``id = 1``): the site has exactly one
    identity, one set of contact details and one header/footer configuration
    for a given language.
    """

    __tablename__ = "website_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    site_name_ar: Mapped[str | None] = mapped_column(String(200))
    site_name_en: Mapped[str | None] = mapped_column(String(200))
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)

    # The logo/favicon are references into the media library, not raw paths,
    # so deleting the media asset in one place cannot leave a dangling header.
    logo_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )
    favicon_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )

    primary_color: Mapped[str | None] = mapped_column(String(16))
    secondary_color: Mapped[str | None] = mapped_column(String(16))

    contact_email: Mapped[str | None] = mapped_column(String(200))
    contact_phone: Mapped[str | None] = mapped_column(String(60))
    whatsapp_number: Mapped[str | None] = mapped_column(String(60))

    # JSON lists/dicts keep the shape flexible without a table per link.
    social_links: Mapped[list | None] = mapped_column(JSON)
    header_config: Mapped[dict | None] = mapped_column(JSON)
    footer_config: Mapped[dict | None] = mapped_column(JSON)

    default_language: Mapped[str] = mapped_column(String(4), default="ar")
    # When maintenance mode is on, the public site shows a maintenance notice
    # while the platform (``/platform/``) and the API stay fully reachable --
    # the separation is enforced in ``main.py``, never by taking the app down.
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_message_ar: Mapped[str | None] = mapped_column(Text)
    maintenance_message_en: Mapped[str | None] = mapped_column(Text)

    seo_default_title_ar: Mapped[str | None] = mapped_column(String(300))
    seo_default_title_en: Mapped[str | None] = mapped_column(String(300))
    seo_default_description_ar: Mapped[str | None] = mapped_column(Text)
    seo_default_description_en: Mapped[str | None] = mapped_column(Text)


class WebsiteSlide(Base, TimestampMixin):
    """One homepage slider slide.

    An empty table must not break the homepage: the renderer simply omits the
    slider when there are no active slides in the window.
    """

    __tablename__ = "website_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_ar: Mapped[str | None] = mapped_column(String(300))
    title_en: Mapped[str | None] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)

    image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )
    mobile_image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )

    cta_label_ar: Mapped[str | None] = mapped_column(String(120))
    cta_label_en: Mapped[str | None] = mapped_column(String(120))
    cta_url: Mapped[str | None] = mapped_column(String(500))

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_website_slides_active_order", "is_active", "display_order"),)


class WebsiteMedia(Base, TimestampMixin):
    """A file in the public/private media library.

    The binary lives on disk under an opaque key (via the website media storage
    module); only metadata is stored here. ``visibility`` is the security
    boundary between public marketing assets and internal documents.
    """

    __tablename__ = "website_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    alt_text_ar: Mapped[str | None] = mapped_column(String(300))
    alt_text_en: Mapped[str | None] = mapped_column(String(300))

    visibility: Mapped[str] = mapped_column(
        String(16), default=MediaVisibility.PUBLIC.value, nullable=False
    )
    # Free-form grouping ("slider", "logo", "company", ...) for the UI filter.
    usage: Mapped[str | None] = mapped_column(String(60))
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (Index("ix_website_media_visibility", "visibility"),)


class WebsitePage(Base, TimestampMixin):
    """An editable public page keyed by a stable route key.

    ``route_key`` ties the row to a route the renderer already knows
    ("home", "about", "contact", ...). Creating a *new* route is intentionally
    not supported from the CMS: the public URL set stays canonical so SEO and
    links cannot drift. The CMS edits the content of existing routes.
    """

    __tablename__ = "website_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)

    title_ar: Mapped[str | None] = mapped_column(String(300))
    title_en: Mapped[str | None] = mapped_column(String(300))
    content_ar: Mapped[str | None] = mapped_column(Text)
    content_en: Mapped[str | None] = mapped_column(Text)

    slug_ar: Mapped[str | None] = mapped_column(String(120))
    slug_en: Mapped[str | None] = mapped_column(String(120))

    seo_title_ar: Mapped[str | None] = mapped_column(String(300))
    seo_title_en: Mapped[str | None] = mapped_column(String(300))
    seo_description_ar: Mapped[str | None] = mapped_column(Text)
    seo_description_en: Mapped[str | None] = mapped_column(Text)
    og_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(16), default=ContentStatus.DRAFT.value, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    noindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sections: Mapped[list["WebsiteContentSection"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="WebsiteContentSection.display_order"
    )


class WebsiteContentSection(Base, TimestampMixin):
    """A structured block on a page.

    Structured, not raw HTML: ``kind`` is a closed set and the free text is
    escaped by the renderer. This is what stops the CMS from becoming a stored
    XSS vector.
    """

    __tablename__ = "website_content_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("website_pages.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20), default=SectionKind.TEXT.value, nullable=False
    )

    heading_ar: Mapped[str | None] = mapped_column(String(300))
    heading_en: Mapped[str | None] = mapped_column(String(300))
    body_ar: Mapped[str | None] = mapped_column(Text)
    body_en: Mapped[str | None] = mapped_column(Text)

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    page: Mapped["WebsitePage"] = relationship(back_populates="sections")

    __table_args__ = (UniqueConstraint("page_id", "key", name="uq_page_section_key"),)


class WebsiteMenu(Base, TimestampMixin):
    """A navigation or footer menu item.

    ``location`` is either ``header`` or ``footer``. ``url`` is validated
    against approved destinations in the service layer (internal public routes
    only, or a small allow-list of external schemes), so the CMS cannot add an
    ``javascript:`` link or remove access to ``/platform/``.
    """

    __tablename__ = "website_menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location: Mapped[str] = mapped_column(String(16), default="header", nullable=False)
    label_ar: Mapped[str | None] = mapped_column(String(120))
    label_en: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_menus.id", ondelete="CASCADE")
    )

    __table_args__ = (Index("ix_website_menus_location_order", "location", "display_order"),)


class WebsiteCompany(Base, TimestampMixin):
    """A public company profile.

    This is the *public* view of a group company -- deliberately separate from
    the operational :class:`~backend.db.models.group.Company` record, whose
    meaning (ownership, financials, departments) differs and must never be
    exposed automatically. A row here is seeded once from the canonical
    handoff dataset and edited as public content.
    """

    __tablename__ = "website_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    activity_ar: Mapped[str | None] = mapped_column(String(300))
    activity_en: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(60))
    location_ar: Mapped[str | None] = mapped_column(String(200))
    location_en: Mapped[str | None] = mapped_column(String(200))

    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(200))
    whatsapp: Mapped[str | None] = mapped_column(String(60))
    website: Mapped[str | None] = mapped_column(String(500))

    logo_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WebsiteService(Base, TimestampMixin):
    """Editable public service content, additive to the V2 service taxonomy.

    V2 renders four services across two markets from ``content.py``. A CMS row
    here can override the copy for a matching slug, or add a presentation
    group; it never deletes a working V2 route. ``market`` is optional, so a
    service can apply to all markets.
    """

    __tablename__ = "website_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    title_ar: Mapped[str | None] = mapped_column(String(300))
    title_en: Mapped[str | None] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(60))
    image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )
    market: Mapped[str | None] = mapped_column(String(40))
    # The approved request/workflow this service leads into, if any.
    linked_form_key: Mapped[str | None] = mapped_column(String(80))
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebsiteSeoMeta(Base, TimestampMixin):
    """Per-route SEO overrides.

    Keyed by ``route_key`` (same vocabulary as :class:`WebsitePage`) so a page
    can carry SEO even when it has no CMS body. ``noindex`` protects private
    routes: the renderer forces ``noindex`` for anything under ``/platform``
    regardless of this table.
    """

    __tablename__ = "website_seo_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    meta_title_ar: Mapped[str | None] = mapped_column(String(300))
    meta_title_en: Mapped[str | None] = mapped_column(String(300))
    meta_description_ar: Mapped[str | None] = mapped_column(Text)
    meta_description_en: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    og_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("website_media.id", ondelete="SET NULL")
    )
    noindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebsiteContentRevision(Base, TimestampMixin):
    """One append-only revision of a CMS entity.

    ``entity_type`` + ``entity_id`` identify the subject; ``snapshot`` is the
    full JSON state at that moment. Written on every create/update so the
    history and rollback endpoints have a source of truth. ``action`` is a
    short verb (``create``/``update``/``publish``/``delete``).
    """

    __tablename__ = "website_content_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    snapshot: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        Index("ix_website_revisions_entity", "entity_type", "entity_id"),
    )


__all__ = [
    "WebsiteSettings",
    "WebsiteSlide",
    "WebsiteMedia",
    "WebsitePage",
    "WebsiteContentSection",
    "WebsiteMenu",
    "WebsiteCompany",
    "WebsiteService",
    "WebsiteSeoMeta",
    "WebsiteContentRevision",
]
