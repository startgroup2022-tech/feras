"""motivational sentence library (S01)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-13 15:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'motivation_texts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text_ar', sa.Text(), nullable=False),
        sa.Column('text_en', sa.Text(), nullable=False),
        sa.Column('audience_role', sa.String(length=60), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_motivation_texts_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_motivation_texts')),
    )
    with op.batch_alter_table('motivation_texts', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_motivation_texts_audience_role'), ['audience_role'], unique=False
        )
        batch_op.create_index(
            'ix_motivation_texts_active', ['is_active', 'sort_order'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('motivation_texts', schema=None) as batch_op:
        batch_op.drop_index('ix_motivation_texts_active')
        batch_op.drop_index(batch_op.f('ix_motivation_texts_audience_role'))
    op.drop_table('motivation_texts')
