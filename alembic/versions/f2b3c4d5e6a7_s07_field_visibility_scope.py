"""S07/AC-07: per-field visibility scope (all / sector / company)

Revision ID: f2b3c4d5e6a7
Revises: e6f7a8b9c0d1
Create Date: 2026-10-15 01:00:00.000000

Table 18 lists ``نطاق الظهور`` (visibility scope) as a configurable-field
attribute with the values الكل (all) / قطاع (sector) / شركة (company). AC-07
requires that a sector-scoped field appears only for the companies of that
sector. Additive: existing fields default to ``all`` so their behaviour is
unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f2b3c4d5e6a7"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("form_fields", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scope", sa.String(length=20), nullable=False, server_default="all")
        )
        batch_op.add_column(sa.Column("scope_sector", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("scope_company_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_form_fields_scope_company_id",
            "companies",
            ["scope_company_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("form_fields", schema=None) as batch_op:
        batch_op.drop_constraint("fk_form_fields_scope_company_id", type_="foreignkey")
        batch_op.drop_column("scope_company_id")
        batch_op.drop_column("scope_sector")
        batch_op.drop_column("scope")
