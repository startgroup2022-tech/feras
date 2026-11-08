"""company setup wizard fields

Revision ID: dda8c6a19971
Revises: f49eb1554901
Create Date: 2026-11-07 14:51:50.050489
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'dda8c6a19971'
down_revision: str | None = 'f49eb1554901'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deck slides 50-52: fields the three-step company wizard collects that the
    # record previously had no home for. All nullable/additive; the language
    # column carries a server default so existing rows are valid.
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trade_name_ar', sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column('trade_name_en', sa.String(length=180), nullable=True))
        batch_op.add_column(sa.Column('activity', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('capital_amount', sa.Numeric(precision=18, scale=2), nullable=True))
        batch_op.add_column(sa.Column('fiscal_year_start_month', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('fiscal_year_end_month', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('default_language', sa.String(length=8), server_default='ar', nullable=False))
        batch_op.add_column(sa.Column('template_effective_from', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('access_scope', sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_column('access_scope')
        batch_op.drop_column('template_effective_from')
        batch_op.drop_column('default_language')
        batch_op.drop_column('fiscal_year_end_month')
        batch_op.drop_column('fiscal_year_start_month')
        batch_op.drop_column('capital_amount')
        batch_op.drop_column('activity')
        batch_op.drop_column('trade_name_en')
        batch_op.drop_column('trade_name_ar')

    # ### end Alembic commands ###
