"""execution 02 financial summary workflow

Adds the additive subsidiary financial-summary workflow tables (spec section
14.1, screens S05/S06/S08):

* ``financial_periods``            -- one per (company, year, month)
* ``financial_summary_versions``   -- versioned F-03 summaries
* ``financial_item_definitions``   -- stable F-04 special-item definitions
* ``financial_summary_items``      -- item values, each snapshotting its rules
* ``financial_bank_attachments``   -- the mandatory bank statement
* ``financial_review_actions``     -- append-only decision history

Every table is new and nothing existing is altered, so the migration is safe to
apply over live Phase 10/11 data. ``financial_periods.effective_version_id`` is
a plain indexed integer (not a hard FK) on purpose: it points at the single
effective version but a strict constraint would create an insert-order cycle
with ``financial_summary_versions``. Integrity is enforced in the service layer
and verified by tests.

Revision ID: 58ef167fa236
Revises: d1e2f3a4b5c6
Create Date: 2026-10-10 22:29:22.900602
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "58ef167fa236"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_item_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name_ar", sa.String(length=200), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("inclusion_rule", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("decision_reference", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_financial_item_definitions_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_item_definitions")),
        sa.UniqueConstraint("company_id", "code", name="uq_financial_item_definition_code"),
    )
    with op.batch_alter_table("financial_item_definitions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_financial_item_definitions_company_id"), ["company_id"], unique=False
        )

    op.create_table(
        "financial_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        # Plain indexed pointer to the effective version (see module docstring).
        sa.Column("effective_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_financial_periods_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_periods")),
        sa.UniqueConstraint("company_id", "period_year", "period_month", name="uq_financial_period"),
    )
    with op.batch_alter_table("financial_periods", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_financial_periods_company_id"), ["company_id"], unique=False
        )
        batch_op.create_index(
            "ix_financial_periods_company_period",
            ["company_id", "period_year", "period_month"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_financial_periods_effective_version_id"),
            ["effective_version_id"],
            unique=False,
        )

    op.create_table(
        "financial_summary_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("corrects_version_id", sa.Integer(), nullable=True),
        sa.Column("submitted_revenue", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("submitted_expenses", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("effective_revenue", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("effective_expenses", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("calculated_result", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("closing_bank_balance", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("closing_cash_balance", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("calculated_total_cash", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("outstanding_debts", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("customer_receivables", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("manager_notes", sa.Text(), nullable=True),
        sa.Column("bank_statement_reference", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("return_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_financial_summary_versions_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_financial_summary_versions_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["corrects_version_id"],
            ["financial_summary_versions.id"],
            name=op.f("fk_financial_summary_versions_corrects_version_id_financial_summary_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_financial_summary_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["financial_periods.id"],
            name=op.f("fk_financial_summary_versions_period_id_financial_periods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_financial_summary_versions_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
            name=op.f("fk_financial_summary_versions_submitted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_summary_versions")),
        sa.UniqueConstraint("period_id", "version_number", name="uq_financial_version_number"),
    )
    with op.batch_alter_table("financial_summary_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_financial_summary_versions_company_id"), ["company_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_financial_summary_versions_period_id"), ["period_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_financial_summary_versions_status"), ["status"], unique=False
        )
        batch_op.create_index(
            "ix_financial_versions_period_status", ["period_id", "status"], unique=False
        )

    op.create_table(
        "financial_bank_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_financial_bank_attachments_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_financial_bank_attachments_uploaded_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["financial_summary_versions.id"],
            name=op.f("fk_financial_bank_attachments_version_id_financial_summary_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_bank_attachments")),
        sa.UniqueConstraint(
            "storage_key", name=op.f("uq_financial_bank_attachments_storage_key")
        ),
    )
    with op.batch_alter_table("financial_bank_attachments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_financial_bank_attachments_company_id"), ["company_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_financial_bank_attachments_version_id"), ["version_id"], unique=False
        )

    op.create_table(
        "financial_review_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_financial_review_actions_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["financial_periods.id"],
            name=op.f("fk_financial_review_actions_period_id_financial_periods"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["financial_summary_versions.id"],
            name=op.f("fk_financial_review_actions_version_id_financial_summary_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_review_actions")),
    )
    with op.batch_alter_table("financial_review_actions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_financial_review_actions_period", ["period_id", "created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_financial_review_actions_period_id"), ["period_id"], unique=False
        )

    op.create_table(
        "financial_summary_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("definition_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name_ar", sa.String(length=200), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("inclusion_rule", sa.String(length=16), nullable=False),
        sa.Column("decision_reference", sa.String(length=120), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["financial_item_definitions.id"],
            name=op.f("fk_financial_summary_items_definition_id_financial_item_definitions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["financial_summary_versions.id"],
            name=op.f("fk_financial_summary_items_version_id_financial_summary_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_summary_items")),
    )
    with op.batch_alter_table("financial_summary_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_financial_summary_items_version_id"), ["version_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("financial_summary_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_summary_items_version_id"))
    op.drop_table("financial_summary_items")

    with op.batch_alter_table("financial_review_actions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_review_actions_period_id"))
        batch_op.drop_index("ix_financial_review_actions_period")
    op.drop_table("financial_review_actions")

    with op.batch_alter_table("financial_bank_attachments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_bank_attachments_version_id"))
        batch_op.drop_index(batch_op.f("ix_financial_bank_attachments_company_id"))
    op.drop_table("financial_bank_attachments")

    with op.batch_alter_table("financial_summary_versions", schema=None) as batch_op:
        batch_op.drop_index("ix_financial_versions_period_status")
        batch_op.drop_index(batch_op.f("ix_financial_summary_versions_status"))
        batch_op.drop_index(batch_op.f("ix_financial_summary_versions_period_id"))
        batch_op.drop_index(batch_op.f("ix_financial_summary_versions_company_id"))
    op.drop_table("financial_summary_versions")

    with op.batch_alter_table("financial_periods", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_periods_effective_version_id"))
        batch_op.drop_index("ix_financial_periods_company_period")
        batch_op.drop_index(batch_op.f("ix_financial_periods_company_id"))
    op.drop_table("financial_periods")

    with op.batch_alter_table("financial_item_definitions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_financial_item_definitions_company_id"))
    op.drop_table("financial_item_definitions")
