from alembic import op
import sqlalchemy as sa


revision = "20261001_0008"
down_revision = "20261001_0007"
branch_labels = None
depends_on = None


def upgrade():
    if "category" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("work_items")}:
        op.add_column("work_items", sa.Column("category", sa.String(32), nullable=False, server_default="其他"))
        op.create_index("ix_work_items_category", "work_items", ["category"])


def downgrade():
    if "category" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("work_items")}:
        op.drop_index("ix_work_items_category", table_name="work_items")
        op.drop_column("work_items", "category")
