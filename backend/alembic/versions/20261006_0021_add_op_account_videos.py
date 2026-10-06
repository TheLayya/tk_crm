"""collect videos for operator accounts without a monitor account"""

from alembic import op
import sqlalchemy as sa


revision = "20261006_0021"
down_revision = "20261005_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_accounts", sa.Column("video_collected_at", sa.DateTime(), nullable=True))
    op.create_table(
        "op_account_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.String(255), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(1024), nullable=True),
        sa.Column("play_count", sa.BigInteger(), nullable=False),
        sa.Column("like_count", sa.BigInteger(), nullable=False),
        sa.Column("comment_count", sa.BigInteger(), nullable=False),
        sa.Column("share_count", sa.BigInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "video_id", name="uq_op_account_video"),
    )
    op.create_index("ix_op_account_videos_id", "op_account_videos", ["id"])
    op.create_index("ix_op_account_videos_account_id", "op_account_videos", ["account_id"])


def downgrade():
    op.drop_table("op_account_videos")
    op.drop_column("op_accounts", "video_collected_at")
