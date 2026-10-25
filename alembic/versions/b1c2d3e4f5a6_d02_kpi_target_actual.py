"""D02: KPI target-versus-actual configuration and approval record

Revision ID: b1c2d3e4f5a6
Revises: a2b3c4d5e6f7
Create Date: 2026-10-15 00:00:00.000000

Additive only. D02 requires a manageable KPI whose actual can be compared with
an approved target. The actual is never stored here — it is resolved live from
the source records — so this migration only adds *configuration* and the
*approval record*: the metric binding, the favourable direction, and the
who/when of activation. ``is_active`` defaults to false so a definition is inert
until an authorised approval flips it (D02: no invented business approval).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: str | None = 'a2b3c4d5e6f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('kpi_definitions', sa.Column('metric_key', sa.String(length=60), nullable=True))
    op.add_column(
        'kpi_definitions',
        sa.Column('direction', sa.String(length=10), nullable=False, server_default='up'),
    )
    op.add_column('kpi_definitions', sa.Column('approved_by_id', sa.Integer(), nullable=True))
    op.add_column(
        'kpi_definitions', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True)
    )
    # batch mode so the FK and the default change work on SQLite as well as
    # PostgreSQL (a plain ALTER of a constraint is not supported by SQLite).
    with op.batch_alter_table('kpi_definitions') as batch_op:
        batch_op.create_foreign_key(
            op.f('fk_kpi_definitions_approved_by_id_users'),
            'users', ['approved_by_id'], ['id'], ondelete='SET NULL',
        )
        # New definitions must be inert until approved (D02).
        batch_op.alter_column('is_active', server_default='0', existing_type=sa.Boolean())


def downgrade() -> None:
    with op.batch_alter_table('kpi_definitions') as batch_op:
        batch_op.alter_column('is_active', server_default='1', existing_type=sa.Boolean())
        batch_op.drop_constraint(
            op.f('fk_kpi_definitions_approved_by_id_users'), type_='foreignkey'
        )
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by_id')
        batch_op.drop_column('direction')
        batch_op.drop_column('metric_key')
