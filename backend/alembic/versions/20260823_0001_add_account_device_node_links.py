"""Add bidirectional account, device and proxy-node links."""
from alembic import op
import sqlalchemy as sa

revision = "20260823_0001"
down_revision = "20260821_0001"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # 设备模块此前由应用启动时 create_all 创建，导致全新部署按迁移顺序执行时失败。
    # 在关系迁移中补齐幂等建表，兼容已有数据库和全新数据库。
    if "devices" not in inspector.get_table_names():
        op.create_table(
            "devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("device_type", sa.String(10), nullable=False),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("node_id", sa.Integer(), sa.ForeignKey("proxy_nodes.id"), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("node_id", name="uq_devices_node_id"),
        )
        op.create_table(
            "device_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("action", sa.String(16), nullable=False),
            sa.Column("changes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    # Refresh the inspector after create_table; SQLAlchemy caches table metadata.
    device_columns = {c["name"] for c in sa.inspect(bind).get_columns("devices")}
    with op.batch_alter_table("devices") as batch:
        if "node_ids" not in device_columns:
            batch.add_column(sa.Column("node_ids", sa.JSON(), nullable=True))
    with op.batch_alter_table("op_accounts") as batch:
        batch.add_column(sa.Column("device_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("node_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_op_accounts_device_id", ["device_id"])
        batch.create_index("ix_op_accounts_device_id", ["device_id"])
        batch.create_index("ix_op_accounts_node_id", ["node_id"])
        batch.create_foreign_key("fk_op_accounts_device_id", "devices", ["device_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_op_accounts_node_id", "proxy_nodes", ["node_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("devices") as batch:
        batch.drop_constraint("uq_devices_node_id", type_="unique")

def downgrade():
    with op.batch_alter_table("devices") as batch:
        batch.drop_column("node_ids")
    with op.batch_alter_table("devices") as batch:
        batch.create_unique_constraint("uq_devices_node_id", ["node_id"])
    with op.batch_alter_table("op_accounts") as batch:
        batch.drop_constraint("fk_op_accounts_node_id", type_="foreignkey")
        batch.drop_constraint("fk_op_accounts_device_id", type_="foreignkey")
        batch.drop_index("ix_op_accounts_node_id")
        batch.drop_index("ix_op_accounts_device_id")
        batch.drop_constraint("uq_op_accounts_device_id", type_="unique")
        batch.drop_column("node_id")
        batch.drop_column("device_id")
