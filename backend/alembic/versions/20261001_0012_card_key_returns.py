from alembic import op
import sqlalchemy as sa

revision = "20261001_0012"
down_revision = "20261001_0011"
branch_labels = None
depends_on = None


def upgrade():
    if "history" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("card_keys")}:
        op.add_column("card_keys", sa.Column("history", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("card_keys") as batch:
        batch.drop_column("history")
