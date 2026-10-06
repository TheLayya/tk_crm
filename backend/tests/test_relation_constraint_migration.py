from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def legacy_database(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    configuration = Config(str(backend / "alembic.ini"))
    configuration.set_main_option("script_location", str(backend / "alembic"))
    url = "sqlite:///" + (tmp_path / "legacy.db").as_posix()
    configuration.set_main_option("sqlalchemy.url", url)
    command.upgrade(configuration, "20261001_0012")
    engine = create_engine(url)
    try:
        yield configuration, engine
    finally:
        engine.dispose()


def test_relation_constraint_upgrade_and_downgrade_preserve_account(legacy_database):
    configuration, engine = legacy_database
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO op_accounts (platform, account, password, status, collect_status, created_at, updated_at) "
                                "VALUES ('tiktok', 'migration-account', 'legacy-secret', '正常', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    with engine.connect() as connection:
        original = connection.execute(text("SELECT id, password FROM op_accounts")).one()
    command.upgrade(configuration, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id, password FROM op_accounts")).one() == original
    uniques = {tuple(item["column_names"]) for item in inspect(engine).get_unique_constraints("op_accounts")}
    assert ("platform", "account") in uniques
    for revision in ("20261001_0012", "head"):
        if revision == "head":
            command.upgrade(configuration, revision)
        else:
            command.downgrade(configuration, revision)
        foreign_keys = {tuple(item["constrained_columns"]) for item in inspect(engine).get_foreign_keys("op_accounts")}
        assert {("device_id",), ("node_id",), ("project_id",)} <= foreign_keys
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id, password FROM op_accounts")).one() == original


def test_duplicate_accounts_stop_upgrade_without_deleting_records(legacy_database):
    configuration, engine = legacy_database
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO op_accounts (platform, account, status, collect_status, created_at, updated_at) "
                                "VALUES ('tiktok', 'duplicate', '正常', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), [{}, {}])
    with pytest.raises(RuntimeError, match="不会自动删除账号"):
        command.upgrade(configuration, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM op_accounts")).scalar_one() == 2
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261001_0012"


def test_device_index_upgrade_preserves_existing_indexes_and_rows(legacy_database):
    configuration, engine = legacy_database
    command.upgrade(configuration, '20261001_0013')
    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX ix_devices_owner_id ON devices (owner_id)"))
        connection.execute(text("INSERT INTO users (id, username, password_hash, is_active, is_super_admin, created_at) "
                                "VALUES (1, 'index-test', 'hash', 1, 0, CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO devices (id, name, device_type, owner_id, is_deleted, created_at, updated_at) "
                                "VALUES (1, 'test-phone', 'phone', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO device_logs (id, device_id, user_id, username, action, created_at) "
                                "VALUES (1, 1, 1, 'index-test', 'CREATE', CURRENT_TIMESTAMP)"))
    command.upgrade(configuration, 'head')
    expected = {
        'devices': {'ix_devices_id', 'ix_devices_owner_id', 'ix_devices_is_deleted'},
        'device_logs': {'ix_device_logs_device_id', 'ix_device_logs_created_at'},
    }
    for table, indexes in expected.items():
        assert indexes <= {index['name'] for index in inspect(engine).get_indexes(table)}
    command.check(configuration)
    command.downgrade(configuration, '20261001_0013')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT name FROM devices')).scalar_one() == 'test-phone'
        assert connection.execute(text('SELECT action FROM device_logs')).scalar_one() == 'CREATE'
    command.upgrade(configuration, 'head')
    command.check(configuration)
