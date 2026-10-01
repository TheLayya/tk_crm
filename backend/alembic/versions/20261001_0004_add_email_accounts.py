from alembic import op
import sqlalchemy as sa


revision = "20261001_0004"
down_revision = "20261001_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("recovery_email", sa.String(length=255), nullable=True),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("account_created_at", sa.DateTime(), nullable=True),
        sa.Column("account_created_year", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("management_status", sa.String(length=20), nullable=False, server_default="闲置"),
        sa.Column("gmail_check_status", sa.String(length=30), nullable=True),
        sa.Column("gmail_check_raw_status", sa.String(length=100), nullable=True),
        sa.Column("gmail_checked_at", sa.DateTime(), nullable=True),
        sa.Column("registrant", sa.String(length=255), nullable=True),
        sa.Column("operator", sa.String(length=255), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_email_accounts_email", "email_accounts", ["email"], unique=True)
    op.create_index("ix_email_accounts_management_status", "email_accounts", ["management_status"])
    op.create_table(
        "email_account_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("op_account_id", sa.Integer(), sa.ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bound_at", sa.DateTime(), nullable=False),
        sa.Column("unbound_at", sa.DateTime(), nullable=True),
        sa.Column("operator", sa.String(length=255), nullable=True),
        sa.Column("unbound_by", sa.String(length=255), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
    )
    op.create_index("ix_email_account_relations_email_id", "email_account_relations", ["email_id"])
    op.create_index("ix_email_account_relations_op_account_id", "email_account_relations", ["op_account_id"])
    op.create_index("uq_email_current_relation", "email_account_relations", ["email_id", "op_account_id"],
                    unique=True, sqlite_where=sa.text("unbound_at IS NULL"))
    op.execute(sa.text("""
        INSERT INTO email_accounts (
            email, password, recovery_email, totp_secret, account_created_at, account_created_year,
            country, management_status, gmail_check_status, gmail_check_raw_status, gmail_checked_at,
            registrant, operator, remark, created_at, updated_at
        ) SELECT lower(trim(account)), password, recovery_email, totp_secret, account_created_at,
            account_created_year, country, '闲置', gmail_check_status, gmail_check_raw_status,
            gmail_checked_at, registrant, operator, remark, created_at, updated_at
        FROM op_accounts WHERE platform = 'gmail'
        AND id IN (SELECT min(id) FROM op_accounts WHERE platform = 'gmail' GROUP BY lower(trim(account)))
    """))


def downgrade():
    op.drop_table("email_account_relations")
    op.drop_index("ix_email_accounts_management_status", table_name="email_accounts")
    op.drop_index("ix_email_accounts_email", table_name="email_accounts")
    op.drop_table("email_accounts")
