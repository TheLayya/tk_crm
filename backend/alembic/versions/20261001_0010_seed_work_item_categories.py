from alembic import op
import sqlalchemy as sa


revision = "20261001_0010"
down_revision = "20261001_0009"
branch_labels = None
depends_on = None


def upgrade():
    table = sa.table(
        "work_item_category_settings",
        sa.column("id", sa.Integer()),
        sa.column("categories", sa.JSON()),
    )
    if not op.get_bind().execute(sa.select(table.c.id).where(table.c.id == 1)).first():
        op.bulk_insert(table, [{
            "id": 1,
            "categories": ["采购渠道", "VPS续费", "未结款项", "团队任务", "账号/节点", "其他"],
        }])


def downgrade():
    pass
