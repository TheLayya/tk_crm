"""record who initiated an operating-account collection task"""
from alembic import op
import sqlalchemy as sa


revision = "20261006_0023"
down_revision = "20261006_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("op_collect_tasks", sa.Column("created_by", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("op_collect_tasks", "created_by")
