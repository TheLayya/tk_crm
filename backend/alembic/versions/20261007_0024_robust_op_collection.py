"""persist bounded retries for operating-account collection"""
from alembic import op
import sqlalchemy as sa


revision = "20261007_0024"
down_revision = "20261006_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("op_accounts", sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("op_accounts", sa.Column("collect_retry_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("op_accounts", "collect_retry_count")
    op.drop_column("op_accounts", "next_attempt_at")
    op.drop_column("op_accounts", "last_attempt_at")
