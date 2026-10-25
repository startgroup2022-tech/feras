"""D01: accountant-approved accounting policy registry

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-15 00:30:00.000000

Additive only. D01 requires that tax, fiscal-year, invoice and asset policy come
from accountant-approved *settings*, not code assumptions. This table stores a
policy as versioned data: a row is a ``draft`` until an accountant approves it,
and approving a new version supersedes (never deletes or edits) the prior one.
Nothing here activates a rule; resolution reads only ``approved`` rows.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'accounting_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('value', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('value_text', sa.String(length=300), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('approved_by_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('supersedes_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_accounting_policies_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['approved_by_id'], ['users.id'],
            name=op.f('fk_accounting_policies_approved_by_id_users'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['supersedes_id'], ['accounting_policies.id'],
            name=op.f('fk_accounting_policies_supersedes_id_accounting_policies'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_accounting_policies_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id', 'kind', 'version', name='uq_accounting_policy_version'
        ),
    )
    op.create_index(
        'ix_accounting_policies_company_kind', 'accounting_policies',
        ['company_id', 'kind'],
    )
    op.create_index(
        'ix_accounting_policies_company_id', 'accounting_policies', ['company_id']
    )
    op.create_index('ix_accounting_policies_kind', 'accounting_policies', ['kind'])
    op.create_index('ix_accounting_policies_status', 'accounting_policies', ['status'])


def downgrade() -> None:
    op.drop_index('ix_accounting_policies_status', 'accounting_policies')
    op.drop_index('ix_accounting_policies_kind', 'accounting_policies')
    op.drop_index('ix_accounting_policies_company_id', 'accounting_policies')
    op.drop_index('ix_accounting_policies_company_kind', 'accounting_policies')
    op.drop_table('accounting_policies')
