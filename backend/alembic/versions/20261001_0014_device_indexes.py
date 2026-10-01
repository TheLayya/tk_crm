"""Add missing device and activity lookup indexes."""
from alembic import op
import sqlalchemy as sa


revision = "20261001_0014"
down_revision = "20261001_0013"
branch_labels = None
depends_on = None

INDEXES = (
    ("devices", "ix_devices_id", "id"),
    ("devices", "ix_devices_owner_id", "owner_id"),
    ("devices", "ix_devices_is_deleted", "is_deleted"),
    ("device_logs", "ix_device_logs_device_id", "device_id"),
    ("device_logs", "ix_device_logs_created_at", "created_at"),
)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table, name, column in INDEXES:
        if name not in {index["name"] for index in inspector.get_indexes(table)}:
            op.create_index(name, table, [column])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table, name, column in reversed(INDEXES):
        if name in {index["name"] for index in inspector.get_indexes(table)}:
            op.drop_index(name, table_name=table)
