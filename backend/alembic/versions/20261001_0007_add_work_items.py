from alembic import op
import sqlalchemy as sa


revision = "20261001_0007"
down_revision = "20261001_0006"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("work_items"):
        return
    op.create_table(
        "work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("reminder_users", sa.Text(), nullable=True),
        sa.Column("remind_at", sa.DateTime(), nullable=True),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    for name, column in (("title", "title"), ("remind_at", "remind_at"), ("is_done", "is_done"), ("created_by", "created_by")):
        op.create_index(f"ix_work_items_{name}", "work_items", [column])


def downgrade():
    op.drop_table("work_items")
