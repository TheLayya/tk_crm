from alembic import op
import sqlalchemy as sa


revision = "20261001_0005"
down_revision = "20261001_0004"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    roles = bind.execute(sa.text("""
        SELECT DISTINCT role_id FROM role_permissions WHERE permission = 'op_account:view'
    """)).fetchall()
    for (role_id,) in roles:
        existing = bind.execute(sa.text("""
            SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission = 'email:view'
        """), {"role_id": role_id}).first()
        if not existing:
            bind.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission) VALUES (:role_id, 'email:view')
            """), {"role_id": role_id})


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission = 'email:view'"))
