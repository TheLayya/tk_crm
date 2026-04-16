"""refactor proxy_node status: merge usage into status, simplify enums

Revision ID: 20260416_0001
Revises: 20260601_0001
Create Date: 2026-04-16 00:01:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '20260416_0001'
down_revision: Union[str, None] = '20260601_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 不支持 ALTER COLUMN，用重建表方式迁移
    # 1. 将旧 status/usage 组合映射到新 status：
    #    usage=self  → active
    #    usage=rented → active  (出租也算在用)
    #    usage=idle  → idle
    #    status=sold → sold (覆盖 usage)
    #    status=expired → disabled (到期归入停用，expire_date 字段保留)
    #    status=disabled → disabled

    # 先更新数据：根据旧字段组合设置新 status 值
    op.execute("""
        UPDATE proxy_nodes SET status =
            CASE
                WHEN status = 'sold'     THEN 'sold'
                WHEN status = 'disabled' THEN 'disabled'
                WHEN status = 'expired'  THEN 'disabled'
                WHEN usage  = 'idle'     THEN 'idle'
                WHEN usage  = 'self'     THEN 'active'
                WHEN usage  = 'rented'   THEN 'active'
                ELSE 'idle'
            END
    """)

    # 删除 usage 列（SQLite 3.35+ 支持 DROP COLUMN）
    with op.batch_alter_table('proxy_nodes') as batch_op:
        batch_op.drop_index('ix_proxy_nodes_usage')
        batch_op.drop_column('usage')


def downgrade() -> None:
    # 恢复 usage 列，status 映射回旧值
    with op.batch_alter_table('proxy_nodes') as batch_op:
        batch_op.add_column(sa.Column('usage', sa.String(16), nullable=False, server_default='idle'))
        batch_op.create_index('ix_proxy_nodes_usage', ['usage'])

    op.execute("""
        UPDATE proxy_nodes SET
            usage = CASE
                WHEN status = 'active' THEN 'self'
                WHEN status = 'idle'   THEN 'idle'
                ELSE 'idle'
            END,
            status = CASE
                WHEN status = 'sold'     THEN 'sold'
                WHEN status = 'disabled' THEN 'disabled'
                ELSE 'active'
            END
    """)
