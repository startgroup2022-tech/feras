"""S11/localization: employee country/nationality field

Revision ID: d806fc545297
Revises: 3473d285d919
Create Date: 2026-10-27 00:00:00.000000

Additive only. Deck slides 102-106 ("ملف الموظف", "لوحة التوطين") require the
employee record to carry the country/nationality the localization rule is
computed against, and slides 134-136 name "جنسية" among the employee-list
filters. The column is nullable so existing rows stay valid; the create form
marks it required on new records, matching the deck.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd806fc545297'
down_revision: str | None = '3473d285d919'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('nationality', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('employees', 'nationality')
