"""Allow administrators to control which email accounts card-key projects may claim."""
from alembic import op
import sqlalchemy as sa


revision = "20261114_0028"
down_revision = "20261114_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_accounts",
        sa.Column("allow_card_key_claim", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Existing emails must stay out of the claim pool until an administrator explicitly enables them.
    op.execute(sa.text("UPDATE email_accounts SET allow_card_key_claim = 0"))


def downgrade():
    op.drop_column("email_accounts", "allow_card_key_claim")
