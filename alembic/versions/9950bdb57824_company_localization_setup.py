"""company localization setup

Revision ID: 9950bdb57824
Revises: b27b32d9905b
Create Date: 2026-11-06 22:16:45.081116
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9950bdb57824'
down_revision: str | None = 'b27b32d9905b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deck slides 105/106: per-entity localization target and calculation-rule
    # edition. Additive and nullable so unset means غير مُعدّ.
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('localization_target_pct', sa.Numeric(precision=6, scale=3), nullable=True))
        batch_op.add_column(sa.Column('localization_rule_version', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('localization_rule_effective_from', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_column('localization_rule_effective_from')
        batch_op.drop_column('localization_rule_version')
        batch_op.drop_column('localization_target_pct')
