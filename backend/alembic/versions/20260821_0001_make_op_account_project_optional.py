"""Allow standalone operation accounts."""
from alembic import op

revision = '20260821_0001'
down_revision = '20260602_0001'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('op_accounts') as batch_op:
        batch_op.alter_column('project_id', nullable=True)

def downgrade():
    with op.batch_alter_table('op_accounts') as batch_op:
        batch_op.alter_column('project_id', nullable=False)
