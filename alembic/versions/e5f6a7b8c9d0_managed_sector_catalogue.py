"""managed sector catalogue

Revision ID: e5f6a7b8c9d0
Revises: 808896a24a5f
Create Date: 2026-10-04 15:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = '808896a24a5f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'sectors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name_ar', sa.String(length=180), nullable=False),
        sa.Column('name_en', sa.String(length=180), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sectors')),
    )
    with op.batch_alter_table('sectors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sectors_code'), ['code'], unique=True)
        batch_op.create_index('ix_sectors_status', ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sectors', schema=None) as batch_op:
        batch_op.drop_index('ix_sectors_status')
        batch_op.drop_index(batch_op.f('ix_sectors_code'))
    op.drop_table('sectors')
