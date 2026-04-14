"""add account_created_at and region fields

Revision ID: 20260322_0436
Revises: c41ab6b0086e
Create Date: 2026-03-22 04:36:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260322_0436'
down_revision = '20260322_0401'
branch_labels = None
depends_on = None


def upgrade():
    # Add account_created_at and region columns to monitor_accounts table
    op.add_column('monitor_accounts', sa.Column('account_created_at', sa.DateTime(), nullable=True))
    op.add_column('monitor_accounts', sa.Column('region', sa.String(length=10), nullable=True))


def downgrade():
    # Remove account_created_at and region columns
    op.drop_column('monitor_accounts', 'region')
    op.drop_column('monitor_accounts', 'account_created_at')
