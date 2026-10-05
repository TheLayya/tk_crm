"""track the user who creates a proxy node"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_0020"
down_revision = "20261002_0019"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("proxy_nodes")}
    if "created_by" not in columns:
        op.add_column("proxy_nodes", sa.Column("created_by", sa.String(length=255), nullable=True))
        op.create_index("ix_proxy_nodes_created_by", "proxy_nodes", ["created_by"], unique=False)


def downgrade():
    op.drop_index("ix_proxy_nodes_created_by", table_name="proxy_nodes")
    op.drop_column("proxy_nodes", "created_by")
