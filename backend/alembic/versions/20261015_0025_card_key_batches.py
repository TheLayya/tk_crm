"""Track card-key import batches without rewriting existing cards or history."""
from alembic import op
import sqlalchemy as sa


revision = "20261015_0025"
down_revision = "20261007_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "card_key_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("card_key_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_no", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_card_key_batches_project_id", "card_key_batches", ["project_id"])
    op.create_index("ix_card_key_batches_status", "card_key_batches", ["status"])
    with op.batch_alter_table("card_keys") as batch:
        batch.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_card_keys_batch_id", "card_key_batches", ["batch_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_card_keys_batch_id", ["batch_id"])


def downgrade():
    with op.batch_alter_table("card_keys") as batch:
        batch.drop_index("ix_card_keys_batch_id")
        batch.drop_constraint("fk_card_keys_batch_id", type_="foreignkey")
        batch.drop_column("batch_id")
    op.drop_index("ix_card_key_batches_status", table_name="card_key_batches")
    op.drop_index("ix_card_key_batches_project_id", table_name="card_key_batches")
    op.drop_table("card_key_batches")
