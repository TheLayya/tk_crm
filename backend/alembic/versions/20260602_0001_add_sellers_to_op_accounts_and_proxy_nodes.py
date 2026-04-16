"""add sellers to op_accounts and proxy_nodes

Revision ID: 20260602_0001
Revises: 20260601_0001
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20260602_0001'
down_revision: Union[str, None] = '20260416_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('op_accounts', sa.Column('sellers', sa.Text(), nullable=True))
    op.add_column('proxy_nodes', sa.Column('sellers', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('op_accounts', 'sellers')
    op.drop_column('proxy_nodes', 'sellers')
