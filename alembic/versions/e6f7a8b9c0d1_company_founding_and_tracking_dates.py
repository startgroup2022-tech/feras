"""F-01/AC-03: company founding date, tracking start and optional English name

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-15 00:00:00.000000

Additive only. Appendix A / F-01 and AC-03 require the founding date to be kept
separate from the date monitoring starts (the opening-balance reference), and
make the sector mandatory while the English name is optional. The sector
mandatory rule is enforced in the request schema; only the two date columns and
the nullable ``name_en`` need a schema change here.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('founded_on', sa.Date(), nullable=True))
    op.add_column('companies', sa.Column('tracking_start_date', sa.Date(), nullable=True))
    # F-01: only the Arabic name is mandatory; the English name becomes optional.
    with op.batch_alter_table('companies') as batch_op:
        batch_op.alter_column('name_en', existing_type=sa.String(length=180), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('companies') as batch_op:
        batch_op.alter_column('name_en', existing_type=sa.String(length=180), nullable=False)
    op.drop_column('companies', 'tracking_start_date')
    op.drop_column('companies', 'founded_on')
