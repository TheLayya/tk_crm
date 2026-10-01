from alembic import op
import sqlalchemy as sa


revision = "20261001_0006"
down_revision = "20261001_0005"
branch_labels = None
depends_on = None


def upgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("email_accounts")}
    for name, column in (
        ("device_id", sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", name="fk_email_accounts_device_id_devices", ondelete="SET NULL"), nullable=True)),
        ("node_id", sa.Column("node_id", sa.Integer(), sa.ForeignKey("proxy_nodes.id", name="fk_email_accounts_node_id_proxy_nodes", ondelete="SET NULL"), nullable=True)),
        ("purchase_channel", sa.Column("purchase_channel", sa.String(255), nullable=True)),
        ("purchase_price", sa.Column("purchase_price", sa.Numeric(10, 2), nullable=True)),
        ("purchase_date", sa.Column("purchase_date", sa.Date(), nullable=True)),
        ("sale_customer", sa.Column("sale_customer", sa.String(255), nullable=True)),
        ("sale_price", sa.Column("sale_price", sa.Numeric(10, 2), nullable=True)),
        ("sale_date", sa.Column("sale_date", sa.Date(), nullable=True)),
        ("sellers", sa.Column("sellers", sa.Text(), nullable=True)),
    ):
        if name in existing:
            continue
        with op.batch_alter_table("email_accounts") as batch:
            batch.add_column(column)
        if name in {"device_id", "node_id"}:
            if not any(index["name"] == f"ix_email_accounts_{name}" for index in sa.inspect(op.get_bind()).get_indexes("email_accounts")):
                op.create_index(f"ix_email_accounts_{name}", "email_accounts", [name])
    if not sa.inspect(op.get_bind()).has_table("email_asset_relations"):
        op.create_table(
            "email_asset_relations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
            sa.Column("node_id", sa.Integer(), sa.ForeignKey("proxy_nodes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("bound_at", sa.DateTime(), nullable=False),
            sa.Column("unbound_at", sa.DateTime(), nullable=True),
            sa.Column("operator", sa.String(255), nullable=True),
            sa.Column("unbound_by", sa.String(255), nullable=True),
            sa.Column("remark", sa.Text(), nullable=True),
        )
        for name in ("email_id", "device_id", "node_id"):
            op.create_index(f"ix_email_asset_relations_{name}", "email_asset_relations", [name])


def downgrade():
    if sa.inspect(op.get_bind()).has_table("email_asset_relations"):
        op.drop_table("email_asset_relations")
    for name in ("device_id", "node_id"):
        if name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("email_accounts")}:
            if any(index["name"] == f"ix_email_accounts_{name}" for index in sa.inspect(op.get_bind()).get_indexes("email_accounts")):
                op.drop_index(f"ix_email_accounts_{name}", table_name="email_accounts")
    for name in ("sellers", "sale_date", "sale_price", "sale_customer", "purchase_date", "purchase_price", "purchase_channel", "node_id", "device_id"):
        op.drop_column("email_accounts", name)
