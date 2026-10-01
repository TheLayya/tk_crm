from alembic import op
import sqlalchemy as sa


revision = "20261001_0002"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("gmail_check_status", sa.String(30), nullable=True))
    op.add_column("op_accounts", sa.Column("gmail_check_raw_status", sa.String(100), nullable=True))
    op.add_column("op_accounts", sa.Column("gmail_checked_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("op_accounts", "gmail_checked_at")
    op.drop_column("op_accounts", "gmail_check_raw_status")
    op.drop_column("op_accounts", "gmail_check_status")
