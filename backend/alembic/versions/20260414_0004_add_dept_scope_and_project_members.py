"""add dept scope and project_members table

Revision ID: 20260414_0004
Revises: 20260414_0003
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260414_0004'
down_revision = '20260414_0003'
branch_labels = None
depends_on = None


def upgrade():
    # project_members: 项目协作成员（创建人手动邀请）
    op.execute("""
        CREATE TABLE IF NOT EXISTS project_members (
            project_id INTEGER NOT NULL,
            username VARCHAR(64) NOT NULL,
            PRIMARY KEY (project_id, username),
            FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
        )
    """)


def downgrade():
    op.drop_table('project_members')
