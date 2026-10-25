"""S13/S14: link a website lead to its marketing campaign

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-15 20:00:00.000000

Spec §18 lists ``Lead ... campaign_id`` and AC-13 requires "the customer is
linked to the campaign and the company without copying it", while AC-14
requires that the customer count "is not doubled between manual and linked
registration". A foreign key -- not a copied campaign name -- is what makes
"linked, not copied" true, and lets S14's ``عرض العملاء`` open the *same* lead
rows rather than a second count.

Additive: the column is nullable, so existing leads keep working and the FK is
``ON DELETE SET NULL`` so removing a campaign never deletes a lead.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("website_leads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("campaign_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_website_leads_campaign_id",
            "campaigns",
            ["campaign_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_website_leads_campaign_id", ["campaign_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("website_leads", schema=None) as batch_op:
        batch_op.drop_index("ix_website_leads_campaign_id")
        batch_op.drop_constraint("fk_website_leads_campaign_id", type_="foreignkey")
        batch_op.drop_column("campaign_id")
