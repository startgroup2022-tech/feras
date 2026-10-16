"""advisor monthly reports (S19)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-14 04:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: str | None = 'd2e3f4a5b6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'advisor_monthly_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('advisor_user_id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('development', sa.Text(), nullable=True),
        sa.Column('challenges', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_advisor_monthly_reports_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['advisor_user_id'], ['users.id'],
            name=op.f('fk_advisor_monthly_reports_advisor_user_id_users'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_advisor_monthly_reports_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_advisor_monthly_reports')),
    )
    with op.batch_alter_table('advisor_monthly_reports', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_advisor_monthly_reports_company_id'), ['company_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_advisor_monthly_reports_advisor_user_id'), ['advisor_user_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_advisor_monthly_reports_status'), ['status'], unique=False)
        batch_op.create_index(
            'ix_advisor_reports_company_period',
            ['company_id', 'period_year', 'period_month'], unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('advisor_monthly_reports', schema=None) as batch_op:
        batch_op.drop_index('ix_advisor_reports_company_period')
        batch_op.drop_index(batch_op.f('ix_advisor_monthly_reports_status'))
        batch_op.drop_index(batch_op.f('ix_advisor_monthly_reports_advisor_user_id'))
        batch_op.drop_index(batch_op.f('ix_advisor_monthly_reports_company_id'))
    op.drop_table('advisor_monthly_reports')
