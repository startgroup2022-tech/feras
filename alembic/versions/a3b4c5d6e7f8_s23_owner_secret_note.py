"""S23/AC-23: owner's confidential note on a leadership assessment

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6a7
Create Date: 2026-10-15 02:00:00.000000

S23 lists ``ملاحظات المالك`` (owner notes) with the type ``نص سري`` (secret
text) and the rule ``سياق لاحق`` (later context): the owner may save a private
note alongside a leadership assessment. AC-23 requires that no secret text
appears in a public activity log, so the note lives on the assessment row and is
never written into the audit payload.

Additive: the column is nullable, so existing rows keep their behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_note", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("owner_note_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_column("owner_note_at")
        batch_op.drop_column("owner_note")
