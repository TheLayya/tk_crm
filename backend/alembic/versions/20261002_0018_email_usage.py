from alembic import op
import sqlalchemy as sa


revision = "20261002_0018"
down_revision = "20261002_0017"
branch_labels = None
depends_on = None


def upgrade():
    if "card_key_email_usages" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "card_key_email_usages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("card_key_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("email_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("username", sa.String(255), nullable=False),
            sa.Column("platform", sa.String(100), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=False),
        )
        for column in ("project_id", "email_id", "username", "completed_at"):
            op.create_index(f"ix_card_key_email_usages_{column}", "card_key_email_usages", [column])


def downgrade():
    op.drop_table("card_key_email_usages")
