"""add users.token_version for server-side session revocation

Revision ID: a9c1e2f3b4d6
Revises: f7a1c2e3d4b5
Create Date: 2026-11-09 06:00:00.000000

Logout and password changes must invalidate tokens that were already issued.
A per-token denylist would need a store that every request reads and that grows
without bound; instead each account carries a monotonic ``token_version`` that is
embedded in every token as the ``tv`` claim. Bumping it (logout, password change,
administrator reset) refuses every token minted before the bump.

The column is NOT NULL with a server default of 0, so existing rows are backfilled
to the initial generation on both SQLite and PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c1e2f3b4d6"
down_revision: str | None = "f7a1c2e3d4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
