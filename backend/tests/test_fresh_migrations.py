from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def test_fresh_database_upgrade_has_card_key_safety_constraints(tmp_path):
    backend_directory = Path(__file__).resolve().parents[1]
    configuration = Config(str(backend_directory / "alembic.ini"))
    configuration.set_main_option("script_location", str(backend_directory / "alembic"))
    database_url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "head")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {"email_accounts", "work_items", "work_item_category_settings",
                "card_key_projects", "card_keys"} <= set(inspector.get_table_names())
        email_foreign_keys = {
            (tuple(foreign_key["constrained_columns"]), foreign_key["referred_table"],
             foreign_key.get("options", {}).get("ondelete"))
            for foreign_key in inspector.get_foreign_keys("email_accounts")
        }
        assert {(("device_id",), "devices", "SET NULL"),
                (("node_id",), "proxy_nodes", "SET NULL")} <= email_foreign_keys
        email_indexes = {index["name"] for index in inspector.get_indexes("email_accounts")}
        assert {"ix_email_accounts_device_id", "ix_email_accounts_node_id"} <= email_indexes
        relation_index = next(index for index in inspector.get_indexes("email_account_relations")
                              if index["name"] == "uq_email_current_relation")
        assert relation_index["unique"]
        assert relation_index["column_names"] == ["email_id", "op_account_id"]
        assert str(relation_index["dialect_options"]["sqlite_where"]) == "unbound_at IS NULL"
        constraints = {tuple(constraint["column_names"])
                       for constraint in inspector.get_unique_constraints("card_keys")}
        assert {("fingerprint",), ("project_id", "pending_owner")} <= constraints
        history = next(column for column in inspector.get_columns("card_keys") if column["name"] == "history")
        assert history["nullable"] is False
        assert history["default"] is not None
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == ScriptDirectory.from_config(configuration).get_current_head()
        command.upgrade(configuration, "head")
        command.check(configuration)
    finally:
        engine.dispose()
