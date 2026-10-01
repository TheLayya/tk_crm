"""Reconcile relation indexes and nullable account ownership constraints."""
from alembic import op
import sqlalchemy as sa


revision = "20261001_0013"
down_revision = "20261001_0012"
branch_labels = None
depends_on = None


def _indexes(table_name):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _reconcile_op_account_constraints(bind):
    metadata = sa.MetaData()
    table = sa.Table("op_accounts", metadata, autoload_with=bind)
    unique_constraints = [
        constraint for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
        and [column.name for column in constraint.columns] in (
            ["platform", "account"], ["project_id", "platform", "account"]
        )
    ]
    project_foreign_keys = [
        constraint for constraint in table.constraints
        if isinstance(constraint, sa.ForeignKeyConstraint)
        and [column.name for column in constraint.columns] == ["project_id"]
    ]
    expected_unique = any(
        [column.name for column in constraint.columns] == ["platform", "account"]
        for constraint in unique_constraints
    )
    expected_project_fk = any(
        next(iter(constraint.elements)).ondelete == "SET NULL"
        for constraint in project_foreign_keys
    )
    if expected_unique and expected_project_fk:
        return

    for constraint in unique_constraints + project_foreign_keys:
        table.constraints.remove(constraint)
    table.append_constraint(sa.UniqueConstraint(
        "platform", "account", name="uq_op_account_platform_account"
    ))
    table.append_constraint(sa.ForeignKeyConstraint(
        ["project_id"], ["projects.id"], name="fk_op_accounts_project_id_projects", ondelete="SET NULL"
    ))
    with op.batch_alter_table("op_accounts", copy_from=table, recreate="always"):
        pass


def upgrade():
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        "SELECT 1 FROM op_accounts GROUP BY platform, account HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("运营账号存在重复的平台与账号组合，请先人工核对；迁移不会自动删除账号")

    for table_name, index_name, columns in (
        ("email_accounts", "ix_email_accounts_id", ["id"]),
        ("email_accounts", "ix_email_accounts_device_id", ["device_id"]),
        ("email_account_relations", "ix_email_account_relations_id", ["id"]),
        ("email_asset_relations", "ix_email_asset_relations_id", ["id"]),
    ):
        if index_name not in _indexes(table_name):
            op.create_index(index_name, table_name, columns)

    email_fks = sa.inspect(bind).get_foreign_keys("email_accounts")
    if not any(fk["constrained_columns"] == ["device_id"] for fk in email_fks):
        with op.batch_alter_table("email_accounts") as batch:
            batch.create_foreign_key(
                "fk_email_accounts_device_id_devices", "devices", ["device_id"], ["id"], ondelete="SET NULL"
            )

    _reconcile_op_account_constraints(bind)


def downgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    table = sa.Table("op_accounts", metadata, autoload_with=bind)
    for constraint in list(table.constraints):
        if (
            isinstance(constraint, sa.UniqueConstraint)
            and [column.name for column in constraint.columns] == ["platform", "account"]
        ) or (
            isinstance(constraint, sa.ForeignKeyConstraint)
            and [column.name for column in constraint.columns] == ["project_id"]
        ):
            table.constraints.remove(constraint)
    table.append_constraint(sa.UniqueConstraint(
        "project_id", "platform", "account", name="uq_op_account_project_platform_account"
    ))
    table.append_constraint(sa.ForeignKeyConstraint(
        ["project_id"], ["projects.id"], ondelete="CASCADE"
    ))
    with op.batch_alter_table("op_accounts", copy_from=table, recreate="always"):
        pass

    for table_name, index_name in (
        ("email_accounts", "ix_email_accounts_id"),
        ("email_account_relations", "ix_email_account_relations_id"),
        ("email_asset_relations", "ix_email_asset_relations_id"),
    ):
        if index_name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}:
            op.drop_index(index_name, table_name=table_name)
