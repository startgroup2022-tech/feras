"""employee restricted fields and localization

Revision ID: b27b32d9905b
Revises: 2b7c225bbb32
Create Date: 2026-11-06 22:03:21.671083
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b27b32d9905b'
down_revision: str | None = '2b7c225bbb32'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deck slide 103: the employee restricted-fields tab. Additive and nullable
    # so existing rows stay valid and nothing already stored is rewritten.
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('work_location', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('wage_effective_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('document_links', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('counts_toward_localization', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('localization_exclusion_reason', sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column('localization_job_title', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('localization_rule_version', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('localization_reference', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('employees', schema=None) as batch_op:
        batch_op.drop_column('localization_reference')
        batch_op.drop_column('localization_rule_version')
        batch_op.drop_column('localization_job_title')
        batch_op.drop_column('localization_exclusion_reason')
        batch_op.drop_column('counts_toward_localization')
        batch_op.drop_column('document_links')
        batch_op.drop_column('wage_effective_date')
        batch_op.drop_column('work_location')
