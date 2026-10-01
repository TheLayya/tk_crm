from alembic import op
import sqlalchemy as sa

revision = "20261001_0001"
down_revision = "20260929_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("recovery_email", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("op_accounts", "recovery_email")
