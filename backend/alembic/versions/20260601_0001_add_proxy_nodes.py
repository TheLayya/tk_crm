"""add proxy_nodes table

Revision ID: 20260601_0001
Revises: 20260415_0001
Create Date: 2026-06-01 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260601_0001'
down_revision: Union[str, None] = '20260415_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'proxy_nodes',
        sa.Column('id', sa.Integer(), nullable=False),

        # 原始节点信息
        sa.Column('ip', sa.String(length=255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('protocol', sa.String(length=16), nullable=False, server_default='socks5'),

        # 中转节点信息
        sa.Column('relay_ip', sa.String(length=255), nullable=True),
        sa.Column('relay_port', sa.Integer(), nullable=True),
        sa.Column('relay_protocol', sa.String(length=16), nullable=True),

        # 采购信息
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('purchase_channel', sa.String(length=255), nullable=True),
        sa.Column('expire_date', sa.Date(), nullable=True),

        # 出售信息
        sa.Column('sale_customer', sa.String(length=255), nullable=True),
        sa.Column('sale_price', sa.Numeric(precision=10, scale=2), nullable=True),

        # 状态字段
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('usage', sa.String(length=16), nullable=False, server_default='idle'),

        # 测试字段
        sa.Column('last_test_at', sa.DateTime(), nullable=True),
        sa.Column('last_test_result', sa.String(length=16), nullable=True),
        sa.Column('last_test_latency', sa.Integer(), nullable=True),

        # 备注
        sa.Column('remark', sa.Text(), nullable=True),

        # 系统字段
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),

        sa.PrimaryKeyConstraint('id'),
    )

    # 主键索引（自动）+ 单列索引
    op.create_index(op.f('ix_proxy_nodes_id'), 'proxy_nodes', ['id'], unique=False)
    op.create_index(op.f('ix_proxy_nodes_status'), 'proxy_nodes', ['status'], unique=False)
    op.create_index(op.f('ix_proxy_nodes_usage'), 'proxy_nodes', ['usage'], unique=False)
    op.create_index(op.f('ix_proxy_nodes_expire_date'), 'proxy_nodes', ['expire_date'], unique=False)
    op.create_index(op.f('ix_proxy_nodes_purchase_channel'), 'proxy_nodes', ['purchase_channel'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_proxy_nodes_purchase_channel'), table_name='proxy_nodes')
    op.drop_index(op.f('ix_proxy_nodes_expire_date'), table_name='proxy_nodes')
    op.drop_index(op.f('ix_proxy_nodes_usage'), table_name='proxy_nodes')
    op.drop_index(op.f('ix_proxy_nodes_status'), table_name='proxy_nodes')
    op.drop_index(op.f('ix_proxy_nodes_id'), table_name='proxy_nodes')
    op.drop_table('proxy_nodes')
