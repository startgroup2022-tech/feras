"""listing photo visibility on website lead attachments

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f6
Create Date: 2026-10-10 09:00:00.000000

Revision brief item 06: a business listing may carry project photos that are
shown once the listing is published, alongside a proof-of-relationship document
that stays internal. A single ``is_public`` flag on the attachment distinguishes
them; it defaults to false so every existing row (and every internal upload)
stays private.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("website_lead_attachments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_public",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("website_lead_attachments", schema=None) as batch_op:
        batch_op.drop_column("is_public")
