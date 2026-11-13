"""add the knowledge_documents.current_version_id foreign key

Revision ID: f7a1c2e3d4b5
Revises: e1b2c3d4f5a6
Create Date: 2026-11-02 02:20:00.000000

The AI knowledge base migration (``2b7c225bbb32``) declares
``knowledge_documents.current_version_id`` with ``use_alter=True`` because the
column points at ``knowledge_versions``, a table created *after*
``knowledge_documents`` -- a forward reference SQLite tolerates but PostgreSQL
does not allow inline. SQLite therefore created the constraint inside the
original ``CREATE TABLE``, while PostgreSQL dropped the ``use_alter`` constraint
entirely: the column exists on both backends, but only SQLite carries the
foreign key.

This migration adds the missing constraint on PostgreSQL only. It is a no-op on
SQLite, which already has it, so the two backends converge on the same schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f7a1c2e3d4b5"
down_revision: str | None = "e1b2c3d4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_knowledge_documents_current_version_id_knowledge_versions"


def _has_constraint(bind) -> bool:
    from sqlalchemy import text

    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :name AND conrelid = 'knowledge_documents'::regclass"
            ),
            {"name": _FK_NAME},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()
    # Only PostgreSQL is missing the constraint, and only PostgreSQL needs the
    # separate ALTER TABLE. On SQLite the constraint was created inline and a
    # batch rebuild here would risk the very table the KB depends on.
    if bind.dialect.name != "postgresql":
        return
    if _has_constraint(bind):
        return
    op.create_foreign_key(
        _FK_NAME,
        "knowledge_documents",
        "knowledge_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _has_constraint(bind):
        return
    op.drop_constraint(_FK_NAME, "knowledge_documents", type_="foreignkey")
