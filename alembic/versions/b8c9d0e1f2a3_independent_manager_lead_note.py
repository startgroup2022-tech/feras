"""independent manager note on website leads (S13)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-13 15:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'lead_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['lead_id'], ['website_leads.id'],
            name=op.f('fk_lead_notes_lead_id_website_leads'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['author_id'], ['users.id'],
            name=op.f('fk_lead_notes_author_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lead_notes')),
    )
    with op.batch_alter_table('lead_notes', schema=None) as batch_op:
        batch_op.create_index(
            'ix_lead_notes_lead', ['lead_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('lead_notes', schema=None) as batch_op:
        batch_op.drop_index('ix_lead_notes_lead')
    op.drop_table('lead_notes')
