"""investment valuation summaries

Revision ID: f49eb1554901
Revises: 9950bdb57824
Create Date: 2026-11-06 22:21:59.310700
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f49eb1554901'
down_revision: str | None = '9950bdb57824'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deck slides 107-109: the documented valuation summary for one owned
    # company. Nullable figures and a yes/no valuation flag so an unset or
    # "no valuation" record never stores an invented zero.
    op.create_table('investment_valuations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owned_company_id', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('investment_date', sa.Date(), nullable=True),
    sa.Column('original_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('subsequent_contributions', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('financing', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('distributions', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('book_value', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('book_value_date', sa.Date(), nullable=True),
    sa.Column('book_value_source', sa.String(length=200), nullable=True),
    sa.Column('has_valuation', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('valuation_amount', sa.Numeric(precision=18, scale=2), nullable=True),
    sa.Column('valuation_date', sa.Date(), nullable=True),
    sa.Column('valuation_source', sa.String(length=200), nullable=True),
    sa.Column('valuation_reference', sa.String(length=200), nullable=True),
    sa.Column('decision_reference', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owned_company_id'], ['companies.id'], name=op.f('fk_investment_valuations_owned_company_id_companies'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_investment_valuations')),
    sa.UniqueConstraint('owned_company_id', name='uq_investment_valuation_company')
    )


def downgrade() -> None:
    op.drop_table('investment_valuations')
    # ### end Alembic commands ###
