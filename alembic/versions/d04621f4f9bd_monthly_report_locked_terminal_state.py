"""monthly report locked terminal state

Revision ID: d04621f4f9bd
Revises: a9c1e2f3b4d6
Create Date: 2026-11-10 21:22:05.632132
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd04621f4f9bd'
down_revision: str | None = 'a9c1e2f3b4d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('monthly_reports', sa.Column('locked_by_id', sa.Integer(), nullable=True))
    op.add_column('monthly_reports', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
    # batch mode so the FK works on SQLite as well as PostgreSQL (SQLite cannot
    # ALTER a constraint directly).
    with op.batch_alter_table('monthly_reports') as batch_op:
        batch_op.create_foreign_key(
            op.f('fk_monthly_reports_locked_by_id_users'),
            'users', ['locked_by_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('monthly_reports') as batch_op:
        batch_op.drop_constraint(
            op.f('fk_monthly_reports_locked_by_id_users'), type_='foreignkey'
        )
        batch_op.drop_column('locked_at')
        batch_op.drop_column('locked_by_id')
