"""Archive card-key projects that still carry history instead of deleting it."""
from alembic import op
import sqlalchemy as sa


revision = "20261114_0029"
down_revision = "20261114_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("card_key_projects", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("card_key_projects", sa.Column("archived_by", sa.String(length=64), nullable=True))
    op.create_index("ix_card_key_projects_archived_at", "card_key_projects", ["archived_at"], unique=False)


def downgrade():
    op.drop_index("ix_card_key_projects_archived_at", table_name="card_key_projects")
    op.drop_column("card_key_projects", "archived_by")
    op.drop_column("card_key_projects", "archived_at")
