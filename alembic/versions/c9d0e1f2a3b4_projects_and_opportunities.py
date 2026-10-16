"""projects & opportunities register (S20)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-04 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d0e1f2a3b4'
down_revision: str | None = 'b8c9d0e1f2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'project_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('record_type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=240), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('results', sa.Text(), nullable=True),
        sa.Column('resource_estimate', sa.Text(), nullable=True),
        sa.Column('estimated_value', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='SAR'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('owner_decision_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_project_records_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['owner_decision_id'], ['owner_decisions.id'],
            name=op.f('fk_project_records_owner_decision_id_owner_decisions'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_project_records_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_project_records')),
    )
    op.create_index(
        op.f('ix_project_records_record_type'), 'project_records', ['record_type'],
    )
    op.create_index(
        op.f('ix_project_records_company_id'), 'project_records', ['company_id'],
    )
    op.create_index(
        op.f('ix_project_records_status'), 'project_records', ['status'],
    )
    op.create_index(
        'ix_project_records_company_type', 'project_records', ['company_id', 'record_type'],
    )


def downgrade() -> None:
    op.drop_index('ix_project_records_company_type', table_name='project_records')
    op.drop_index(op.f('ix_project_records_status'), table_name='project_records')
    op.drop_index(op.f('ix_project_records_company_id'), table_name='project_records')
    op.drop_index(op.f('ix_project_records_record_type'), table_name='project_records')
    op.drop_table('project_records')
