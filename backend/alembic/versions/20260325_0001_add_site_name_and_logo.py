"""add site_name and logo_image to monitor_settings

Revision ID: 20260325_0001
Revises: 20260322_0436
Create Date: 2026-03-25 00:01:00

"""
from alembic import op
import sqlalchemy as sa


revision = '20260325_0001'
down_revision = '20260322_0436'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('monitor_settings',
        sa.Column('site_name', sa.String(length=100), nullable=False, server_default='TikTok Monitor')
    )
    op.add_column('monitor_settings',
        sa.Column('logo_image', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('monitor_settings', 'logo_image')
    op.drop_column('monitor_settings', 'site_name')
