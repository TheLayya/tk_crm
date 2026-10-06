"""Seed/check only the temporary database used by the real online updater smoke."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

mode, directory = sys.argv[1:3]
data = Path(directory).resolve(strict=True)
root = Path(__file__).resolve().parents[2]
configuration = Config()
configuration.set_main_option("script_location", str(root / "backend/alembic").replace("%", "%%"))
configuration.set_main_option("sqlalchemy.url", ("sqlite:///" + str(data / "monitor.db")).replace("%", "%%"))
key = "a" * 64
os.environ.update(
    FIELD_ENCRYPTION_KEY=key,
    JWT_SECRET="online-update-fixture",
    SUPER_ADMIN_PASSWORD="FixtureOnly123!",
)
sys.path.insert(0, str(root / "backend"))
from app.services.encryption_service import EncryptionService  # noqa: E402

encryption = EncryptionService(key)
snapshot_path = data.parent / "original-data.json"
if mode == "seed":
    assert not (data / "monitor.db").exists(), "Only an empty fixture can be seeded"
    configuration_text = (
        "JWT_SECRET=online-update-fixture\n"
        f"FIELD_ENCRYPTION_KEY={key}\n"
        "SUPER_ADMIN_PASSWORD=FixtureOnly123!\n"
    )
    (data / ".env").write_bytes(configuration_text.encode("utf-8"))
    (data / "fixture-only.txt").write_text("online update marker", encoding="utf-8")
    command.upgrade(configuration, "20261001_0004")
    password = encryption.encrypt("preserved-mail-password")
    totp = encryption.encrypt("JBSWY3DPEHPK3PXP")
    with sqlite3.connect(data / "monitor.db") as connection:
        connection.execute(
            "INSERT INTO email_accounts "
            "(email,password,totp_secret,management_status,registrant,operator,remark,created_at,updated_at) "
            "VALUES (?,?,?,'闲置','admin','admin','preserved-note',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            ("fixture@example.invalid", password, totp),
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261001_0004"
    snapshot_path.write_text(json.dumps({"password": password, "totp": totp, "env": configuration_text}), encoding="utf-8")
    print("PASS synthetic 0004 schema and encrypted fixture seeded")
elif mode == "verify":
    original = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert (data / ".env").read_bytes() == original["env"].encode("utf-8"), "Original configuration changed"
    assert (data / "fixture-only.txt").read_text(encoding="utf-8") == "online update marker", "Marker changed"
    with sqlite3.connect((data / "monitor.db").as_uri() + "?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")} == set(ScriptDirectory.from_config(configuration).get_heads())
        row = connection.execute(
            "SELECT password,totp_secret,remark FROM email_accounts WHERE email=?", ("fixture@example.invalid",)
        ).fetchone()
        assert row == (original["password"], original["totp"], "preserved-note"), "Encrypted record changed"
        assert encryption.decrypt(row[0]) == "preserved-mail-password"
        assert encryption.decrypt(row[1]) == "JBSWY3DPEHPK3PXP"
    print("PASS current schema, SQLite integrity, original ciphertext/config/marker preserved")
else:
    raise ValueError("Expected seed or verify")
