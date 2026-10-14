"""support request design metadata and external delivery (S16)

Revision ID: d2e3f4a5b6c7
Revises: c9d0e1f2a3b4
Create Date: 2026-10-14 04:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd2e3f4a5b6c7'
down_revision: str | None = 'c9d0e1f2a3b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('support_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('dimensions', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('reference_link', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('delivery_link', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('support_requests', schema=None) as batch_op:
        batch_op.drop_column('delivered_at')
        batch_op.drop_column('delivery_link')
        batch_op.drop_column('reference_link')
        batch_op.drop_column('dimensions')
        batch_op.drop_column('platform')
