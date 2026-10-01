from alembic import op
import sqlalchemy as sa


revision = "20261001_0003"
down_revision = "20261001_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("account_created_year", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("op_accounts", "account_created_year")
