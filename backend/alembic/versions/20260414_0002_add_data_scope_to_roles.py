"""add data_scope to roles

Revision ID: 20260414_0002
Revises: 20260501_0001
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260414_0002'
down_revision = '20260501_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('roles', sa.Column('data_scope', sa.String(16), nullable=False, server_default='all'))


def downgrade():
    op.drop_column('roles', 'data_scope')
