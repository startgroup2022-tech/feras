"""organisational positions (S24)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-13 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('title_ar', sa.String(length=180), nullable=False),
        sa.Column('title_en', sa.String(length=180), nullable=False),
        sa.Column('holder_user_id', sa.Integer(), nullable=True),
        sa.Column('holder_employee_id', sa.Integer(), nullable=True),
        sa.Column('reports_to_position_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_positions_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['department_id'], ['departments.id'],
            name=op.f('fk_positions_department_id_departments'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['holder_user_id'], ['users.id'],
            name=op.f('fk_positions_holder_user_id_users'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['holder_employee_id'], ['employees.id'],
            name=op.f('fk_positions_holder_employee_id_employees'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['reports_to_position_id'], ['positions.id'],
            name=op.f('fk_positions_reports_to_position_id_positions'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_positions')),
        sa.UniqueConstraint('company_id', 'code', name='uq_positions_company_code'),
    )
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_positions_company_id'), ['company_id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_positions_department_id'), ['department_id'], unique=False
        )
        batch_op.create_index('ix_positions_company_status', ['company_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_positions_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('positions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_positions_status'))
        batch_op.drop_index('ix_positions_company_status')
        batch_op.drop_index(batch_op.f('ix_positions_department_id'))
        batch_op.drop_index(batch_op.f('ix_positions_company_id'))
    op.drop_table('positions')
