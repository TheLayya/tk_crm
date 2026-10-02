from alembic import op
import sqlalchemy as sa


revision = "20261002_0019"
down_revision = "20261002_0018"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("card_keys")}
    if "remark" not in columns:
        op.add_column("card_keys", sa.Column("remark", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("card_keys", "remark")
