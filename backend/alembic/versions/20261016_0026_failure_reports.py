"""Keep encrypted failure screenshots together with card-key and email history."""
from alembic import op
import sqlalchemy as sa


revision = "20261016_0026"
down_revision = "20261015_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "failure_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("card_key_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("key_id", sa.Integer(), sa.ForeignKey("card_keys.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("batch_name", sa.String(200), nullable=True),
        sa.Column("batch_no", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("image_metadata", sa.JSON(), nullable=False),
        sa.Column("screenshots", sa.Text(), nullable=False),
        sa.CheckConstraint("(key_id IS NOT NULL AND email_id IS NULL AND kind = 'card_key') OR (key_id IS NULL AND email_id IS NOT NULL AND kind = 'email')", name="ck_failure_report_parent"),
        sa.CheckConstraint("image_count >= 0 AND image_count <= 5", name="ck_failure_report_image_count"),
    )
    for field in ("project_id", "key_id", "email_id", "username", "created_at"):
        op.create_index(f"ix_failure_reports_{field}", "failure_reports", [field])


def downgrade():
    op.drop_table("failure_reports")
