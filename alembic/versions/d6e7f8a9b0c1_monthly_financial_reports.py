"""S28: monthly financial report (Table 57)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-15 23:00:00.000000

S28 ``التقرير المالي الشهري``: the accountant draws the accounts for a month
and adds the analysis. This is a new, additive table; no existing column is
touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_financial_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("figures", sa.Text(), nullable=True),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("source_version_id", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by_id", sa.Integer(), nullable=True),
        sa.Column("finalised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalised_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["financial_summary_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["generated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finalised_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "period_year", "period_month", name="uq_monthly_fin_report"
        ),
    )
    op.create_index(
        "ix_monthly_financial_reports_company_id", "monthly_financial_reports", ["company_id"]
    )
    op.create_index(
        "ix_monthly_financial_reports_status", "monthly_financial_reports", ["status"]
    )
    op.create_index(
        "ix_monthly_fin_reports_company_period",
        "monthly_financial_reports",
        ["company_id", "period_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_monthly_fin_reports_company_period", table_name="monthly_financial_reports")
    op.drop_index("ix_monthly_financial_reports_status", table_name="monthly_financial_reports")
    op.drop_index("ix_monthly_financial_reports_company_id", table_name="monthly_financial_reports")
    op.drop_table("monthly_financial_reports")
