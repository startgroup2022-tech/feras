"""management reports & report clarifications (S21/S02/S09)

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-10-04 18:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'e3f4a5b6c7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # S21: the BD manager's monthly five-axis brief.
    op.create_table(
        'management_briefs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period_year', sa.Integer(), nullable=False),
        sa.Column('period_month', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('urgency', sa.String(length=20), nullable=False, server_default='monthly'),
        sa.Column('executive_summary', sa.String(length=2000), nullable=True),
        sa.Column('axis_companies', sa.Text(), nullable=True),
        sa.Column('axis_projects', sa.Text(), nullable=True),
        sa.Column('axis_employees', sa.Text(), nullable=True),
        sa.Column('axis_risks', sa.Text(), nullable=True),
        sa.Column('axis_decisions', sa.Text(), nullable=True),
        sa.Column('source_report_ids', sa.String(length=2000), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['created_by_id'], ['users.id'],
            name=op.f('fk_management_briefs_created_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_management_briefs')),
        sa.UniqueConstraint(
            'period_year', 'period_month', 'created_by_id',
            name='uq_management_brief_period_author',
        ),
    )
    op.create_index(
        op.f('ix_management_briefs_status'), 'management_briefs', ['status'],
    )
    op.create_index(
        'ix_management_briefs_period', 'management_briefs', ['period_year', 'period_month'],
    )

    # S02/S09: a clarification linked to a report's original (never edits it).
    op.create_table(
        'report_clarifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='request'),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['report_id'], ['monthly_reports.id'],
            name=op.f('fk_report_clarifications_report_id_monthly_reports'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['author_id'], ['users.id'],
            name=op.f('fk_report_clarifications_author_id_users'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['report_clarifications.id'],
            name=op.f('fk_report_clarifications_parent_id_report_clarifications'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_report_clarifications')),
    )
    op.create_index(
        op.f('ix_report_clarifications_report_id'), 'report_clarifications', ['report_id'],
    )
    op.create_index(
        'ix_report_clarifications_report', 'report_clarifications', ['report_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_report_clarifications_report', table_name='report_clarifications')
    op.drop_index(op.f('ix_report_clarifications_report_id'), table_name='report_clarifications')
    op.drop_table('report_clarifications')
    op.drop_index('ix_management_briefs_period', table_name='management_briefs')
    op.drop_index(op.f('ix_management_briefs_status'), table_name='management_briefs')
    op.drop_table('management_briefs')
