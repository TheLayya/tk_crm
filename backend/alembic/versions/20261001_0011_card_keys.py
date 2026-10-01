from alembic import op
import sqlalchemy as sa

revision = "20261001_0011"
down_revision = "20261001_0010"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {name for name in ("card_key_projects", "card_keys") if inspector.has_table(name)}
    if existing:
        required = {
            "card_key_projects": {"id", "name", "description", "member_usernames", "is_active", "created_by", "created_at", "updated_at"},
            "card_keys": {"id", "project_id", "content", "fingerprint", "pending_owner", "status", "claimed_by", "claimed_at", "consumed_at", "created_by", "created_at"},
        }
        if existing != set(required) or any(
            not columns.issubset({column["name"] for column in inspector.get_columns(name)})
            for name, columns in required.items()
        ):
            raise RuntimeError("Existing card key tables do not match this migration")
        constraints = {tuple(value["column_names"]) for value in inspector.get_unique_constraints("card_keys")}
        if not {("fingerprint",), ("project_id", "pending_owner")}.issubset(constraints):
            raise RuntimeError("Existing card key tables lack required uniqueness constraints")
        return
    op.create_table("card_key_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("member_usernames", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table("card_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("card_key_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("pending_owner", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False, server_default="available"),
        sa.Column("claimed_by", sa.String(64)), sa.Column("claimed_at", sa.DateTime()),
        sa.Column("consumed_at", sa.DateTime()), sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_card_key_fingerprint"),
        sa.UniqueConstraint("project_id", "pending_owner", name="uq_card_key_pending_owner"),
    )
    op.create_index("ix_card_key_projects_created_by", "card_key_projects", ["created_by"])
    op.create_index("ix_card_keys_project_id", "card_keys", ["project_id"])
    op.create_index("ix_card_keys_status", "card_keys", ["status"])
    op.create_index("ix_card_keys_claimed_by", "card_keys", ["claimed_by"])


def downgrade():
    op.drop_table("card_keys")
    op.drop_table("card_key_projects")
