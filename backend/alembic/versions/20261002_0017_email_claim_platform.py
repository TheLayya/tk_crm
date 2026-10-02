from alembic import op
import sqlalchemy as sa


revision = "20261002_0017"
down_revision = "20261001_0016"
branch_labels = None
depends_on = None


def upgrade():
    if "card_key_platforms" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "card_key_platforms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("name", name="uq_card_key_platform_name"),
        )
        op.create_index("ix_card_key_platforms_is_active", "card_key_platforms", ["is_active"], unique=False)
    inspector = sa.inspect(op.get_bind())
    project_columns = {column["name"] for column in inspector.get_columns("card_key_projects")}
    email_columns = {column["name"] for column in inspector.get_columns("email_accounts")}
    if "target_platform" not in project_columns:
        op.add_column("card_key_projects", sa.Column("target_platform", sa.String(100), nullable=True))
    existing_project_indexes = {index["name"] for index in inspector.get_indexes("card_key_projects")}
    if "ix_card_key_projects_target_platform" not in existing_project_indexes:
        op.create_index("ix_card_key_projects_target_platform", "card_key_projects", ["target_platform"])
    for name, column in (
        ("platform_tags", sa.Column("platform_tags", sa.Text(), nullable=True)),
        ("claimed_by", sa.Column("claimed_by", sa.String(255), nullable=True)),
        ("claimed_at", sa.Column("claimed_at", sa.DateTime(), nullable=True)),
        ("claimed_platform", sa.Column("claimed_platform", sa.String(100), nullable=True)),
    ):
        if name not in email_columns:
            op.add_column("email_accounts", column)
    existing_email_indexes = {index["name"] for index in inspector.get_indexes("email_accounts")}
    for name, column in (("ix_email_accounts_claimed_by", "claimed_by"),):
        if name not in existing_email_indexes:
            op.create_index(name, "email_accounts", [column])
    if "uq_email_pending_platform" not in existing_email_indexes:
        op.create_index("uq_email_pending_platform", "email_accounts", ["claimed_by", "claimed_platform"], unique=True)


def downgrade():
    op.drop_index("ix_card_key_platforms_is_active", table_name="card_key_platforms")
    op.drop_table("card_key_platforms")
    op.drop_index("uq_email_pending_platform", table_name="email_accounts")
    op.drop_index("ix_email_accounts_claimed_by", table_name="email_accounts")
    for name in ("claimed_platform", "claimed_at", "claimed_by", "platform_tags"):
        op.drop_column("email_accounts", name)
    op.drop_index("ix_card_key_projects_target_platform", table_name="card_key_projects")
    op.drop_column("card_key_projects", "target_platform")
