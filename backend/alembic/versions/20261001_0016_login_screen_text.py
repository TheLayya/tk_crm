from alembic import op
import sqlalchemy as sa


revision = "20261001_0016"
down_revision = "20261001_0015"
branch_labels = None
depends_on = None


def upgrade():
    if "login_screen_text" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("monitor_settings")}:
        op.add_column("monitor_settings", sa.Column("login_screen_text", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("monitor_settings", "login_screen_text")
