"""opportunity study fields and smart-brief plan requests

Revision ID: e1b2c3d4f5a6
Revises: dda8c6a19971
Create Date: 2026-11-08 09:12:00.000000

Deck slides 25-26 add an opportunity study ("تفاصيل وتقييم الفرصة"): a stage
label plus the free-text facts/assumptions/risks/recommendation shown before a
topic is raised to the owner. Deck slide 46 adds the manager's short smart brief
with a [نعم، اطلب خطة] offer that opens a plan request for Business Development.

All project columns are nullable/additive. The plan-request table is new.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e1b2c3d4f5a6'
down_revision: str | None = 'dda8c6a19971'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deck slide 26: the opportunity study. Free text only -- the deck has no
    # automatic feasibility engine, so nothing here is computed or constrained.
    with op.batch_alter_table('project_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('market_customers', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('information_source', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('expected_revenue', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('key_risks', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('alternatives', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('recommendation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('study_sources', sa.Text(), nullable=True))
        batch_op.create_index('ix_project_records_stage', ['stage'])

    # Deck slide 46: the manager's plan request, handed to Business Development
    # to answer by hand. Not an approval step -- a request with a status.
    op.create_table(
        'plan_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('advice', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='requested', nullable=False),
        sa.Column('requested_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('plan_requests', schema=None) as batch_op:
        batch_op.create_index('ix_plan_requests_company', ['company_id'])
        batch_op.create_index('ix_plan_requests_status', ['status'])


def downgrade() -> None:
    with op.batch_alter_table('plan_requests', schema=None) as batch_op:
        batch_op.drop_index('ix_plan_requests_status')
        batch_op.drop_index('ix_plan_requests_company')
    op.drop_table('plan_requests')

    with op.batch_alter_table('project_records', schema=None) as batch_op:
        batch_op.drop_index('ix_project_records_stage')
        batch_op.drop_column('study_sources')
        batch_op.drop_column('recommendation')
        batch_op.drop_column('alternatives')
        batch_op.drop_column('key_risks')
        batch_op.drop_column('expected_revenue')
        batch_op.drop_column('information_source')
        batch_op.drop_column('market_customers')
        batch_op.drop_column('stage')
