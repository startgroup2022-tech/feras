"""D11: notification preferences and delivery log

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-10-15 00:10:00.000000

Additive only. D11 makes in-app the base channel and email optional per event
type and user preference. Two new tables hold the *configuration* (per-user,
per-event channel choice) and the *delivery record* (status, attempts and a
minimised excerpt). Nothing here activates an external channel: a preference is
inert until a provider is configured outside the code.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=60), nullable=False),
        sa.Column('in_app', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('email', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('muted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_notification_preferences_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'event_type', name='uq_notification_preferences_user_event'
        ),
    )
    op.create_index(
        'ix_notification_preferences_user_id', 'notification_preferences', ['user_id']
    )

    op.create_table(
        'notification_delivery_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notification_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('provider', sa.String(length=40), nullable=True),
        sa.Column('payload_excerpt', sa.Text(), nullable=True),
        sa.Column('error', sa.String(length=300), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['notification_id'], ['notifications.id'],
            name=op.f('fk_notification_delivery_log_notification_id_notifications'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_notification_delivery_log_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notification_delivery_user_channel',
        'notification_delivery_log', ['user_id', 'channel'],
    )
    op.create_index(
        'ix_notification_delivery_status', 'notification_delivery_log', ['status']
    )
    op.create_index(
        'ix_notification_delivery_log_notification_id',
        'notification_delivery_log', ['notification_id'],
    )
    op.create_index(
        'ix_notification_delivery_log_user_id',
        'notification_delivery_log', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_notification_delivery_log_user_id', 'notification_delivery_log')
    op.drop_index('ix_notification_delivery_log_notification_id', 'notification_delivery_log')
    op.drop_index('ix_notification_delivery_status', 'notification_delivery_log')
    op.drop_index('ix_notification_delivery_user_channel', 'notification_delivery_log')
    op.drop_table('notification_delivery_log')
    op.drop_index('ix_notification_preferences_user_id', 'notification_preferences')
    op.drop_table('notification_preferences')
