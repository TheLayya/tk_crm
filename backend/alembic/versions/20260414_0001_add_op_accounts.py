"""add op_accounts tables

Revision ID: 20260414_0001
Revises: 20260325_0001_add_site_name_and_logo
Create Date: 2026-04-14 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260414_0001'
down_revision: Union[str, None] = '20260325_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'op_collect_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.Enum('running', 'completed', 'failed',
                                    name='op_task_status_enum', create_constraint=False),
                  nullable=False, server_default='running'),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'op_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.Enum('tiktok', 'youtube', 'instagram', 'facebook',
                                      name='op_platform_enum', create_constraint=False),
                  nullable=False),
        # 手动维护字段
        sa.Column('account', sa.String(length=255), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('totp_secret', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('email_password', sa.String(length=255), nullable=True),
        sa.Column('email_login_url', sa.String(length=512), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('phone_manage_url', sa.String(length=512), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('正常', '自用', '封禁', '已售',
                                    name='op_status_enum', create_constraint=False),
                  nullable=False, server_default='正常'),
        sa.Column('registrant', sa.String(length=255), nullable=True),
        sa.Column('operator', sa.String(length=255), nullable=True),
        # TikTok 专属字段
        sa.Column('tiktok_mid_video', sa.Boolean(), nullable=True),
        sa.Column('tiktok_showcase', sa.Boolean(), nullable=True),
        sa.Column('tiktok_phone_live', sa.Boolean(), nullable=True),
        sa.Column('tiktok_partner_live', sa.Boolean(), nullable=True),
        # 采购字段
        sa.Column('purchase_channel', sa.String(length=255), nullable=True),
        sa.Column('purchase_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('maintenance_cost', sa.Numeric(10, 2), nullable=True),
        # 出售字段
        sa.Column('sale_customer', sa.String(length=255), nullable=True),
        sa.Column('sale_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('sale_date', sa.Date(), nullable=True),
        # 采集字段
        sa.Column('platform_user_id', sa.String(length=255), nullable=True),
        sa.Column('platform_sec_uid', sa.String(length=512), nullable=True),
        sa.Column('nickname', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.String(length=1024), nullable=True),
        sa.Column('follower_count', sa.BigInteger(), nullable=True),
        sa.Column('following_count', sa.BigInteger(), nullable=True),
        sa.Column('like_count', sa.BigInteger(), nullable=True),
        sa.Column('video_count', sa.BigInteger(), nullable=True),
        sa.Column('account_created_at', sa.DateTime(), nullable=True),
        sa.Column('last_collected_at', sa.DateTime(), nullable=True),
        sa.Column('collect_status', sa.Enum('pending', 'success', 'failed', 'unsupported',
                                            name='op_collect_status_enum', create_constraint=False),
                  nullable=False, server_default='pending'),
        sa.Column('collect_error', sa.Text(), nullable=True),
        # 系统字段
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'platform', 'account',
                            name='uq_op_account_project_platform_account'),
    )
    op.create_index(op.f('ix_op_accounts_id'), 'op_accounts', ['id'], unique=False)
    op.create_index(op.f('ix_op_accounts_project_id'), 'op_accounts', ['project_id'], unique=False)
    op.create_index(op.f('ix_op_accounts_account'), 'op_accounts', ['account'], unique=False)
    op.create_index(op.f('ix_op_accounts_status'), 'op_accounts', ['status'], unique=False)

    op.create_table(
        'op_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('op_account_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('operator', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['op_account_id'], ['op_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_op_audit_logs_id'), 'op_audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_op_audit_logs_op_account_id'), 'op_audit_logs', ['op_account_id'], unique=False)
    op.create_index(op.f('ix_op_audit_logs_created_at'), 'op_audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_op_audit_logs_created_at'), table_name='op_audit_logs')
    op.drop_index(op.f('ix_op_audit_logs_op_account_id'), table_name='op_audit_logs')
    op.drop_index(op.f('ix_op_audit_logs_id'), table_name='op_audit_logs')
    op.drop_table('op_audit_logs')

    op.drop_index(op.f('ix_op_accounts_status'), table_name='op_accounts')
    op.drop_index(op.f('ix_op_accounts_account'), table_name='op_accounts')
    op.drop_index(op.f('ix_op_accounts_project_id'), table_name='op_accounts')
    op.drop_index(op.f('ix_op_accounts_id'), table_name='op_accounts')
    op.drop_table('op_accounts')

    op.drop_table('op_collect_tasks')
