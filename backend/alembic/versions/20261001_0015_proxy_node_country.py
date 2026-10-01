from alembic import op
import sqlalchemy as sa


revision = "20261001_0015"
down_revision = "20261001_0014"
branch_labels = None
depends_on = None


def upgrade():
    if "country" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("proxy_nodes")}:
        op.add_column("proxy_nodes", sa.Column("country", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("proxy_nodes", "country")
