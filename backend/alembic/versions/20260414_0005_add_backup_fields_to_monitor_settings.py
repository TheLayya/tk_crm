"""add backup fields to monitor_settings

Revision ID: 20260414_0005
Revises: 20260414_0004
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa


revision = '20260414_0005'
down_revision = '20260414_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('monitor_settings',
        sa.Column('backup_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0'))
    )
    op.add_column('monitor_settings',
        sa.Column('backup_interval_hours', sa.Integer(), nullable=False, server_default=sa.text('24'))
    )
    op.add_column('monitor_settings',
        sa.Column('telegram_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0'))
    )
    op.add_column('monitor_settings',
        sa.Column('telegram_bot_token', sa.String(length=512), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('telegram_chat_id', sa.String(length=128), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0'))
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_host', sa.String(length=255), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_port', sa.Integer(), nullable=False, server_default=sa.text('587'))
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_username', sa.String(length=255), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_password', sa.String(length=512), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_sender', sa.String(length=255), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('email_recipient', sa.String(length=255), nullable=False, server_default='')
    )
    op.add_column('monitor_settings',
        sa.Column('smtp_use_tls', sa.Boolean(), nullable=False, server_default=sa.text('1'))
    )


def downgrade():
    op.drop_column('monitor_settings', 'smtp_use_tls')
    op.drop_column('monitor_settings', 'email_recipient')
    op.drop_column('monitor_settings', 'smtp_sender')
    op.drop_column('monitor_settings', 'smtp_password')
    op.drop_column('monitor_settings', 'smtp_username')
    op.drop_column('monitor_settings', 'smtp_port')
    op.drop_column('monitor_settings', 'smtp_host')
    op.drop_column('monitor_settings', 'email_enabled')
    op.drop_column('monitor_settings', 'telegram_chat_id')
    op.drop_column('monitor_settings', 'telegram_bot_token')
    op.drop_column('monitor_settings', 'telegram_enabled')
    op.drop_column('monitor_settings', 'backup_interval_hours')
    op.drop_column('monitor_settings', 'backup_enabled')
