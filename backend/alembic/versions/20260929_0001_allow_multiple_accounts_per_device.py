"""Allow multiple operation accounts on one device."""
from alembic import op

revision = "20260929_0001"
down_revision = "20260823_0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("op_accounts") as batch:
        batch.drop_constraint("uq_op_accounts_device_id", type_="unique")


def downgrade():
    with op.batch_alter_table("op_accounts") as batch:
        batch.create_unique_constraint("uq_op_accounts_device_id", ["device_id"])
