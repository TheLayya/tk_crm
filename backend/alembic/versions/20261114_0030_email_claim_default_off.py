"""Reset existing email claim switches to the safe default for databases that already ran 0028."""
from alembic import op
import sqlalchemy as sa


revision = "20261114_0030"
down_revision = "20261114_0029"
branch_labels = None
depends_on = None


def upgrade():
    # 0028 first shipped with a true default; databases that already applied it must not keep
    # historical emails in the claim pool until an administrator explicitly enables them.
    op.execute(sa.text("UPDATE email_accounts SET allow_card_key_claim = 0"))


def downgrade():
    pass
