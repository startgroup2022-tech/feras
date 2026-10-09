"""bilingual role description

Revision ID: c4a9e1f2b3d7
Revises: b7f1a7747880
Create Date: 2026-10-05 09:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a9e1f2b3d7'
down_revision: str | None = 'b7f1a7747880'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description_ar', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_column('description_ar')
