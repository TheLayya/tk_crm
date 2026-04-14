"""add default_video_count to settings

Revision ID: 20260322_0401
Revises: 
Create Date: 2026-03-22 04:01:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260322_0401'
down_revision = 'c41ab6b0086e'
branch_labels = None
depends_on = None


def upgrade():
    # Add default_video_count column to monitor_settings table
    op.add_column('monitor_settings', 
        sa.Column('default_video_count', sa.Integer(), nullable=False, server_default='20')
    )


def downgrade():
    # Remove default_video_count column from monitor_settings table
    op.drop_column('monitor_settings', 'default_video_count')
