import importlib.util
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


@pytest.fixture
def desktop_runtime():
    path = Path(__file__).resolve().parents[2] / "desktop/server_main.py"
    specification = importlib.util.spec_from_file_location("desktop_runtime", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_initial_configuration_is_preserved(desktop_runtime, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TKCRM_DATA_DIR", str(tmp_path))
    desktop_runtime.configure_runtime()
    saved = (tmp_path / ".env").read_bytes()
    assert b"SUPER_ADMIN_PASSWORD=Admin123!" in saved
    desktop_runtime.configure_runtime()
    assert (tmp_path / ".env").read_bytes() == saved


def test_runtime_uses_user_data_for_update_history(desktop_runtime, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TKCRM_DATA_DIR", str(tmp_path))
    desktop_runtime.configure_runtime()
    assert Path(os.environ["UPDATE_HISTORY_PATH"]) == tmp_path / "update-history.json"


def test_existing_database_without_key_is_rejected(desktop_runtime, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TKCRM_DATA_DIR", str(tmp_path))
    (tmp_path / "monitor.db").write_bytes(b"existing")
    with pytest.raises(RuntimeError, match="encryption configuration"):
        desktop_runtime.configure_runtime()
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / "monitor.db").read_bytes() == b"existing"


def test_legacy_data_is_imported_only_into_empty_target(desktop_runtime, tmp_path, monkeypatch):
    source = tmp_path / "legacy"
    target = tmp_path / "target"
    source.mkdir()
    with sqlite3.connect(source / "monitor.db") as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('legacy-db')")
    (source / ".env").write_text("JWT_SECRET=old\nFIELD_ENCRYPTION_KEY=" + "a" * 64 + "\nSUPER_ADMIN_PASSWORD=old\n", encoding="utf-8")
    monkeypatch.setenv("TKCRM_DATA_DIR", str(target))
    monkeypatch.setenv("TKCRM_LEGACY_DATA_DIR", str(source))
    desktop_runtime.configure_runtime()
    with sqlite3.connect(target / "monitor.db") as connection:
        assert connection.execute("SELECT value FROM records").fetchone() == ("legacy-db",)
    assert (target / ".env").read_bytes() == (source / ".env").read_bytes()
    with sqlite3.connect(source / "monitor.db") as connection:
        connection.execute("INSERT INTO records VALUES ('changed-source')")
    desktop_runtime.configure_runtime()
    with sqlite3.connect(target / "monitor.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone() == (1,)


def test_failed_migration_restores_database(desktop_runtime, tmp_path, monkeypatch):
    from alembic import command

    monkeypatch.chdir(tmp_path)
    database = tmp_path / "monitor.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE original (value TEXT)")
        connection.execute("INSERT INTO original VALUES ('preserved')")

    def failing_upgrade(configuration, revision):
        with sqlite3.connect(database) as connection:
            connection.execute("DROP TABLE original")
            connection.execute("CREATE TABLE partial (value TEXT)")
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(command, "upgrade", failing_upgrade)
    with pytest.raises(RuntimeError, match="injected"):
        desktop_runtime.migrate_database(Path(__file__).resolve().parents[2], tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM original").fetchone() == ("preserved",)
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchall()
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_current_database_does_not_migrate_or_create_backups(desktop_runtime, tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    bundle = Path(__file__).resolve().parents[2]
    configuration = Config()
    configuration.set_main_option("script_location", str(bundle / "backend/alembic").replace("%", "%%"))
    heads = ScriptDirectory.from_config(configuration).get_heads()
    database = tmp_path / "monitor.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO alembic_version VALUES (?)", [(revision,) for revision in heads])
        connection.execute("CREATE TABLE original (value TEXT)")
        connection.execute("INSERT INTO original VALUES ('preserved')")
    original = database.read_bytes()
    monkeypatch.chdir(tmp_path)

    def unexpected_upgrade(*args):
        pytest.fail("An up-to-date database must not be migrated")

    monkeypatch.setattr(command, "upgrade", unexpected_upgrade)
    desktop_runtime.migrate_database(bundle, tmp_path)
    desktop_runtime.migrate_database(bundle, tmp_path)
    assert database.read_bytes() == original
    assert not (tmp_path / "backups").exists()


def test_desktop_runtime_does_not_inherit_source_updater(desktop_runtime, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TKCRM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UPDATE_AGENT_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("UPDATE_AGENT_TOKEN", "source-updater-token")
    desktop_runtime.configure_runtime()
    assert os.environ["UPDATE_CLIENT_TYPE"] == "desktop"
    assert os.environ["UPDATE_AGENT_URL"] == ""
    assert os.environ["UPDATE_AGENT_TOKEN"] == ""


def test_managed_desktop_can_receive_local_update_agent(desktop_runtime, monkeypatch):
    monkeypatch.setenv("TKCRM_MANAGED", "1")
    monkeypatch.setenv("TKCRM_DESKTOP_AGENT_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("TKCRM_DESKTOP_AGENT_TOKEN", "desktop-agent-token")
    desktop_runtime.configure_runtime()
    assert os.environ["UPDATE_AGENT_URL"] == "http://127.0.0.1:8765"
    assert os.environ["UPDATE_AGENT_TOKEN"] == "desktop-agent-token"


def test_managed_desktop_without_agent_clears_source_updater(desktop_runtime, monkeypatch):
    monkeypatch.setenv("TKCRM_MANAGED", "1")
    monkeypatch.delenv("TKCRM_DESKTOP_AGENT_URL", raising=False)
    monkeypatch.delenv("TKCRM_DESKTOP_AGENT_TOKEN", raising=False)
    monkeypatch.setenv("UPDATE_AGENT_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("UPDATE_AGENT_TOKEN", "source-updater-token")
    desktop_runtime.configure_runtime()
    assert os.environ["UPDATE_AGENT_URL"] == ""
    assert os.environ["UPDATE_AGENT_TOKEN"] == ""


@pytest.mark.parametrize("layout", ["flat", "backend", "project"])
def test_legacy_wal_and_source_layouts(desktop_runtime, tmp_path, monkeypatch, layout):
    root = tmp_path / "legacy"
    backend = root / "backend" if layout == "project" else root
    directory = backend / "data" if layout != "flat" else backend
    directory.mkdir(parents=True)
    configuration = backend / ".env"
    configuration.write_text("JWT_SECRET=old\nFIELD_ENCRYPTION_KEY=" + "a" * 64 + "\nSUPER_ADMIN_PASSWORD=old\n", encoding="utf-8-sig")
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setenv("TKCRM_LEGACY_DATA_DIR", str(root))
    with closing(sqlite3.connect(directory / "monitor.db")) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('committed-in-wal')")
        connection.commit()
        assert Path(str(directory / "monitor.db") + "-wal").is_file()
        desktop_runtime.import_legacy_data(tmp_path, target)
        with closing(sqlite3.connect(target / "monitor.db")) as imported:
            assert imported.execute("SELECT value FROM records").fetchone() == ("committed-in-wal",)
    assert (target / ".env").read_text(encoding="utf-8") == configuration.read_text(encoding="utf-8-sig")
    assert not (target / ".env").read_bytes().startswith(b"\xef\xbb\xbf")
    assert not (target / "monitor.importing.db").exists()


@pytest.mark.parametrize("configuration", [None, "FIELD_ENCRYPTION_KEY=bad\n"])
def test_invalid_legacy_configuration_does_not_initialize(desktop_runtime, tmp_path, monkeypatch, configuration):
    source = tmp_path / "source"
    source.mkdir()
    with closing(sqlite3.connect(source / "monitor.db")) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
    if configuration is not None:
        (source / ".env").write_text(configuration, encoding="utf-8")
    target = tmp_path / "target"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TKCRM_DATA_DIR", str(target))
    monkeypatch.setenv("TKCRM_LEGACY_DATA_DIR", str(source))
    with pytest.raises(RuntimeError):
        desktop_runtime.configure_runtime()
    assert not (target / ".env").exists()
    assert not (target / "monitor.db").exists()
