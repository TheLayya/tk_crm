import os
import re
import secrets
import sqlite3
import sys
import threading
from datetime import datetime
from contextlib import closing
from io import StringIO
from pathlib import Path


def configure_runtime() -> tuple[Path, Path]:
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    data = Path(os.environ.get("TKCRM_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TkCRM" / "server")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    import_legacy_data(bundle, data)
    configuration = data / ".env"
    if not configuration.exists():
        if (data / "monitor.db").exists():
            raise RuntimeError("Existing database has no encryption configuration; restore its original .env first")
        with configuration.open("x", encoding="utf-8") as output:
            output.write(f"JWT_SECRET={secrets.token_hex(32)}\nFIELD_ENCRYPTION_KEY={secrets.token_hex(32)}\nSUPER_ADMIN_PASSWORD=Admin123!\n")
    os.chdir(data)
    sys.path.insert(0, str(bundle / "backend"))
    os.environ["DATABASE_URL"] = "sqlite:///./monitor.db"
    os.environ["STATIC_DIR"] = str(bundle / "frontend" / "dist")
    os.environ["HOST"] = "127.0.0.1"
    os.environ["UPDATE_CLIENT_TYPE"] = "desktop"
    os.environ["UPDATE_AGENT_URL"] = os.environ.get("TKCRM_DESKTOP_AGENT_URL", "") if os.environ.get("TKCRM_MANAGED") == "1" else ""
    os.environ["UPDATE_AGENT_TOKEN"] = os.environ.get("TKCRM_DESKTOP_AGENT_TOKEN", "") if os.environ.get("TKCRM_MANAGED") == "1" else ""
    os.environ["UPDATE_HISTORY_PATH"] = str(data / "update-history.json")
    return bundle, data


def import_legacy_data(bundle: Path, data: Path) -> None:
    if (data / "monitor.db").exists() or (data / ".env").exists():
        return
    configured = os.environ.get("TKCRM_LEGACY_DATA_DIR", "").strip()
    if not configured:
        return
    from dotenv import dotenv_values

    root = Path(configured).resolve()
    candidates = [(root / "monitor.db", root / ".env"),
                  (root / "data" / "monitor.db", root / ".env"),
                  (root / "backend" / "data" / "monitor.db", root / "backend" / ".env")]
    for database, configuration in candidates:
        if not database.is_file() or not configuration.is_file():
            continue
        configuration_text = configuration.read_text(encoding="utf-8-sig")
        values = dotenv_values(stream=StringIO(configuration_text), interpolate=False)
        if not re.fullmatch(r"[0-9a-fA-F]{64}", values.get("FIELD_ENCRYPTION_KEY") or ""):
            raise RuntimeError("Legacy encryption key is missing or invalid")
        if not (values.get("JWT_SECRET") or "").strip() or not (values.get("SUPER_ADMIN_PASSWORD") or "").strip():
            raise RuntimeError("Legacy authentication configuration is missing")
        temporary = data / "monitor.importing.db"
        if temporary.exists():
            temporary.unlink()
        temporary_config = data / ".env.importing"
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source_connection, closing(sqlite3.connect(temporary)) as target_connection:
                source_connection.backup(target_connection)
                if target_connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise RuntimeError("Legacy database integrity check failed")
            temporary_config.write_text(configuration_text, encoding="utf-8")
            temporary_config.replace(data / ".env")
            try:
                temporary.replace(data / "monitor.db")
            except Exception:
                (data / ".env").unlink()
                raise
        finally:
            temporary.unlink(missing_ok=True)
            temporary_config.unlink(missing_ok=True)
        return
    raise RuntimeError("Legacy directory must contain monitor.db and its original .env")


def migrate_database(bundle: Path, data: Path) -> None:
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    database = data / "monitor.db"
    configuration = Config(str(bundle / "backend" / "alembic.ini"))
    configuration.set_main_option("script_location", str(bundle / "backend" / "alembic").replace("%", "%%"))
    configuration.set_main_option("sqlalchemy.url", "sqlite:///./monitor.db")
    if database.exists():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            version_table = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
            revisions = {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")} if version_table else set()
        if revisions == set(ScriptDirectory.from_config(configuration).get_heads()):
            return
    backup = None
    if database.exists():
        backups = data / "backups"
        backups.mkdir(exist_ok=True)
        backup = backups / f"before-migration-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
    try:
        command.upgrade(configuration, "head")
    except Exception:
        if backup is not None:
            from app.core.database import engine
            engine.dispose()
            with closing(sqlite3.connect(backup)) as source, closing(sqlite3.connect(database)) as target:
                source.backup(target)
        raise


def main() -> None:
    bundle, data = configure_runtime()
    migrate_database(bundle, data)
    import uvicorn
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), reload=False))
    if os.environ.get("TKCRM_MANAGED") == "1":
        def watch_owner():
            sys.stdin.readline()
            server.should_exit = True

        threading.Thread(target=watch_owner, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
