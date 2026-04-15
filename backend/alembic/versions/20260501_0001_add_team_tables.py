"""add team tables

Revision ID: 20260501_0001
Revises: 20260414_0001
Create Date: 2026-05-01 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260501_0001'
down_revision: Union[str, None] = '20260414_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. departments（无外键依赖，但自引用 parent_id）
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['parent_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parent_id', 'name'),
    )

    # 2. users（依赖 departments）
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('real_name', sa.String(length=64), nullable=True),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('is_super_admin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # 3. roles（无外键依赖）
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # 4. role_permissions（依赖 roles）
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('permission', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 5. user_roles（依赖 users + roles）
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
    )

    # 6. refresh_tokens（依赖 users）
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)

    # 7. operation_tokens（依赖 users）
    op.create_table(
        'operation_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('operation', sa.String(length=64), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )

    # 8. login_logs（无外键）
    op.create_table(
        'login_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('result', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_login_logs_username'), 'login_logs', ['username'], unique=False)
    op.create_index(op.f('ix_login_logs_created_at'), 'login_logs', ['created_at'], unique=False)

    # 9. operation_logs（无外键）
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('module', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('summary', sa.String(length=512), nullable=True),
        sa.Column('result', sa.String(length=16), nullable=False),
        sa.Column('error', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_operation_logs_username'), 'operation_logs', ['username'], unique=False)
    op.create_index(op.f('ix_operation_logs_created_at'), 'operation_logs', ['created_at'], unique=False)


def downgrade() -> None:
    # 按依赖顺序删除：先删有外键依赖的表
    op.drop_index(op.f('ix_operation_logs_created_at'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_username'), table_name='operation_logs')
    op.drop_table('operation_logs')

    op.drop_index(op.f('ix_login_logs_created_at'), table_name='login_logs')
    op.drop_index(op.f('ix_login_logs_username'), table_name='login_logs')
    op.drop_table('login_logs')

    op.drop_table('operation_tokens')

    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

    op.drop_table('user_roles')
    op.drop_table('role_permissions')
    op.drop_table('roles')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')

    op.drop_table('departments')
