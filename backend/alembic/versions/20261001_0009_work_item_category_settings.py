from alembic import op
import sqlalchemy as sa

revision = "20261001_0009"
down_revision = "20261001_0008"
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("work_item_category_settings"):
        op.create_table("work_item_category_settings",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        sa.Column("categories", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("work_item_category_settings")
