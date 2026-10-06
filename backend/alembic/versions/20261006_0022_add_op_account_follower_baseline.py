"""store the previous profile follower count for operator accounts"""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0022"
down_revision = "20261006_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("previous_follower_count", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("op_accounts", "previous_follower_count")
