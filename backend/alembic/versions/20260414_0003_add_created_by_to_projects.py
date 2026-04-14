"""add created_by to projects

Revision ID: 20260414_0003
Revises: 20260414_0002
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260414_0003'
down_revision = '20260414_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('created_by', sa.String(64), nullable=True))


def downgrade():
    op.drop_column('projects', 'created_by')
