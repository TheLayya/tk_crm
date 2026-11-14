"""Store email Cookie credentials separately from notes."""
from alembic import op
import sqlalchemy as sa


revision = "20261114_0027"
down_revision = "20261016_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_accounts", sa.Column("ck", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("email_accounts", "ck")
