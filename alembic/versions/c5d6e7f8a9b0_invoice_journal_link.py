"""S27/AC-27: one reference between an invoice and its ledger entry

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-15 22:00:00.000000

AC-27 requires that "the invoice and the entry keep one reference". A nullable,
*unique* foreign key from ``invoices`` to ``journals`` is what makes that true:
the entry is referenced, never re-created, and the uniqueness stops two invoices
from pointing at the same entry (or one invoice from carrying two).

Additive: the column is nullable, so existing invoices keep working, and the FK
is ``ON DELETE SET NULL`` so removing a journal never deletes an invoice.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("journal_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_invoices_journal_id",
            "journals",
            ["journal_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_invoices_journal_id", ["journal_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_constraint("uq_invoices_journal_id", type_="unique")
        batch_op.drop_constraint("fk_invoices_journal_id", type_="foreignkey")
        batch_op.drop_column("journal_id")
