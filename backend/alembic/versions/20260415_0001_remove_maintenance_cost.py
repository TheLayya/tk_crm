"""remove maintenance_cost from op_accounts

Revision ID: 20260415_0001
Revises: 20260501_0001
Create Date: 2026-04-15

"""
from alembic import op
import sqlalchemy as sa

revision = '20260415_0001'
down_revision = '20260501_0001'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('op_accounts') as batch_op:
        batch_op.drop_column('maintenance_cost')


def downgrade():
    with op.batch_alter_table('op_accounts') as batch_op:
        batch_op.add_column(sa.Column('maintenance_cost', sa.Numeric(10, 2), nullable=True))
