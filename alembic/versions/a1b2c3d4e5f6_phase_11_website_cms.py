"""phase 11 website cms

Adds the additive Website Management tables: settings, slides, media library,
pages/content sections, menus, public company profiles, service content, SEO
metadata and content revisions.

Every table is new; nothing existing is altered, so the migration is safe to
apply over live Phase 10 data (the renderer falls back to the built-in V2
content until rows exist).

Revision ID: a1b2c3d4e5f6
Revises: c4a9e1f2b3d7
Create Date: 2026-10-09 07:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c4a9e1f2b3d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("alt_text_ar", sa.String(length=300), nullable=True),
        sa.Column("alt_text_en", sa.String(length=300), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("usage", sa.String(length=60), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_website_media_visibility", "website_media", ["visibility"])

    op.create_table(
        "website_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_name_ar", sa.String(length=200), nullable=True),
        sa.Column("site_name_en", sa.String(length=200), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("logo_media_id", sa.Integer(), nullable=True),
        sa.Column("favicon_media_id", sa.Integer(), nullable=True),
        sa.Column("primary_color", sa.String(length=16), nullable=True),
        sa.Column("secondary_color", sa.String(length=16), nullable=True),
        sa.Column("contact_email", sa.String(length=200), nullable=True),
        sa.Column("contact_phone", sa.String(length=60), nullable=True),
        sa.Column("whatsapp_number", sa.String(length=60), nullable=True),
        sa.Column("social_links", sa.JSON(), nullable=True),
        sa.Column("header_config", sa.JSON(), nullable=True),
        sa.Column("footer_config", sa.JSON(), nullable=True),
        sa.Column("default_language", sa.String(length=4), nullable=False),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False),
        sa.Column("maintenance_message_ar", sa.Text(), nullable=True),
        sa.Column("maintenance_message_en", sa.Text(), nullable=True),
        sa.Column("seo_default_title_ar", sa.String(length=300), nullable=True),
        sa.Column("seo_default_title_en", sa.String(length=300), nullable=True),
        sa.Column("seo_default_description_ar", sa.Text(), nullable=True),
        sa.Column("seo_default_description_en", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["favicon_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["logo_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "website_slides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title_ar", sa.String(length=300), nullable=True),
        sa.Column("title_en", sa.String(length=300), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("image_media_id", sa.Integer(), nullable=True),
        sa.Column("mobile_image_media_id", sa.Integer(), nullable=True),
        sa.Column("cta_label_ar", sa.String(length=120), nullable=True),
        sa.Column("cta_label_en", sa.String(length=120), nullable=True),
        sa.Column("cta_url", sa.String(length=500), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["image_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mobile_image_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_slides_active_order", "website_slides", ["is_active", "display_order"])

    op.create_table(
        "website_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_key", sa.String(length=80), nullable=False),
        sa.Column("title_ar", sa.String(length=300), nullable=True),
        sa.Column("title_en", sa.String(length=300), nullable=True),
        sa.Column("content_ar", sa.Text(), nullable=True),
        sa.Column("content_en", sa.Text(), nullable=True),
        sa.Column("slug_ar", sa.String(length=120), nullable=True),
        sa.Column("slug_en", sa.String(length=120), nullable=True),
        sa.Column("seo_title_ar", sa.String(length=300), nullable=True),
        sa.Column("seo_title_en", sa.String(length=300), nullable=True),
        sa.Column("seo_description_ar", sa.Text(), nullable=True),
        sa.Column("seo_description_en", sa.Text(), nullable=True),
        sa.Column("og_media_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("noindex", sa.Boolean(), nullable=False),
        sa.Column("in_sitemap", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["og_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_key"),
    )

    op.create_table(
        "website_content_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("heading_ar", sa.String(length=300), nullable=True),
        sa.Column("heading_en", sa.String(length=300), nullable=True),
        sa.Column("body_ar", sa.Text(), nullable=True),
        sa.Column("body_en", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["website_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id", "key", name="uq_page_section_key"),
    )

    op.create_table(
        "website_menus",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=16), nullable=False),
        sa.Column("label_ar", sa.String(length=120), nullable=True),
        sa.Column("label_en", sa.String(length=120), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["website_menus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_menus_location_order", "website_menus", ["location", "display_order"])

    op.create_table(
        "website_companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name_ar", sa.String(length=300), nullable=False),
        sa.Column("name_en", sa.String(length=300), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("activity_ar", sa.String(length=300), nullable=True),
        sa.Column("activity_en", sa.String(length=300), nullable=True),
        sa.Column("country", sa.String(length=60), nullable=True),
        sa.Column("location_ar", sa.String(length=200), nullable=True),
        sa.Column("location_en", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("whatsapp", sa.String(length=60), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("logo_media_id", sa.Integer(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["logo_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "website_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title_ar", sa.String(length=300), nullable=True),
        sa.Column("title_en", sa.String(length=300), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=60), nullable=True),
        sa.Column("image_media_id", sa.Integer(), nullable=True),
        sa.Column("market", sa.String(length=40), nullable=True),
        sa.Column("linked_form_key", sa.String(length=80), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["image_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "website_seo_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_key", sa.String(length=120), nullable=False),
        sa.Column("meta_title_ar", sa.String(length=300), nullable=True),
        sa.Column("meta_title_en", sa.String(length=300), nullable=True),
        sa.Column("meta_description_ar", sa.Text(), nullable=True),
        sa.Column("meta_description_en", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.String(length=500), nullable=True),
        sa.Column("og_media_id", sa.Integer(), nullable=True),
        sa.Column("noindex", sa.Boolean(), nullable=False),
        sa.Column("in_sitemap", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["og_media_id"], ["website_media.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_key"),
    )

    op.create_table(
        "website_content_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_revisions_entity", "website_content_revisions", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_website_revisions_entity", table_name="website_content_revisions")
    op.drop_table("website_content_revisions")
    op.drop_table("website_seo_meta")
    op.drop_table("website_services")
    op.drop_table("website_companies")
    op.drop_index("ix_website_menus_location_order", table_name="website_menus")
    op.drop_table("website_menus")
    op.drop_table("website_content_sections")
    op.drop_table("website_pages")
    op.drop_index("ix_website_slides_active_order", table_name="website_slides")
    op.drop_table("website_slides")
    op.drop_table("website_settings")
    op.drop_index("ix_website_media_visibility", table_name="website_media")
    op.drop_table("website_media")
