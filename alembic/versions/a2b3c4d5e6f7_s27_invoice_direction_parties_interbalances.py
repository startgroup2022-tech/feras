"""S27: invoice direction, party directory and inter-company balances

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-10-14 00:00:00.000000

Additive only. S27 requires a receivable/payable distinction on an invoice, a
single customer/supplier directory and a place to record an inter-company
balance with its currency and reason. The balance is a balance, never revenue;
no transfer or service fee is created (spec §15, D01).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3c4d5e6f7'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # S27: the customer / supplier directory.
    op.create_table(
        'parties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('name_en', sa.String(length=200), nullable=True),
        sa.Column('party_type', sa.String(length=20), nullable=False, server_default='customer'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='SAR'),
        sa.Column('contact', sa.String(length=200), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_parties_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_parties_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_parties')),
        sa.UniqueConstraint('company_id', 'name', name='uq_party_company_name'),
    )
    op.create_index(op.f('ix_parties_company_id'), 'parties', ['company_id'])
    op.create_index('ix_parties_company_type', 'parties', ['company_id', 'party_type'])

    # S27: recorded inter-company balances (currency preserved, never revenue).
    op.create_table(
        'company_interbalances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('counterparty_company_id', sa.Integer(), nullable=True),
        sa.Column('counterparty_name', sa.String(length=200), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='SAR'),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False,
                  server_default='0'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('journal_reference', sa.String(length=120), nullable=True),
        sa.Column('recorded_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'],
            name=op.f('fk_company_interbalances_company_id_companies'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['counterparty_company_id'], ['companies.id'],
            name=op.f('fk_company_interbalances_counterparty_company_id_companies'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['recorded_by_id'], ['users.id'],
            name=op.f('fk_company_interbalances_recorded_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_company_interbalances')),
    )
    op.create_index(
        op.f('ix_company_interbalances_company_id'), 'company_interbalances', ['company_id'],
    )
    op.create_index(
        op.f('ix_company_interbalances_counterparty_company_id'),
        'company_interbalances', ['counterparty_company_id'],
    )
    op.create_index(
        'ix_interbalances_company', 'company_interbalances',
        ['company_id', 'counterparty_company_id'],
    )

    # S27: receivables ("مستحق لنا") vs payables ("مستحق علينا") on one invoice.
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('direction', sa.String(length=20), nullable=False,
                      server_default='issued'),
        )
        batch_op.add_column(sa.Column('party_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_invoices_direction'), ['direction'])
        batch_op.create_foreign_key(
            batch_op.f('fk_invoices_party_id_parties'), 'parties',
            ['party_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f('fk_invoices_party_id_parties'), type_='foreignkey',
        )
        batch_op.drop_index(batch_op.f('ix_invoices_direction'))
        batch_op.drop_column('party_id')
        batch_op.drop_column('direction')

    op.drop_index('ix_interbalances_company', table_name='company_interbalances')
    op.drop_index(
        op.f('ix_company_interbalances_counterparty_company_id'),
        table_name='company_interbalances',
    )
    op.drop_index(
        op.f('ix_company_interbalances_company_id'), table_name='company_interbalances',
    )
    op.drop_table('company_interbalances')

    op.drop_index('ix_parties_company_type', table_name='parties')
    op.drop_index(op.f('ix_parties_company_id'), table_name='parties')
    op.drop_table('parties')
