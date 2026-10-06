import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

root = Path(__file__).resolve().parents[2]
data = Path(tempfile.mkdtemp(prefix="TkCRM-packaged-migration-"))
configuration_text = "JWT_SECRET=isolated-migration-fixture\nFIELD_ENCRYPTION_KEY=" + "a" * 64 + "\nSUPER_ADMIN_PASSWORD=FixtureOnly123!\n"
(data / ".env").write_text(configuration_text, encoding="utf-8")
os.environ.update(FIELD_ENCRYPTION_KEY="a" * 64, JWT_SECRET="isolated-migration-fixture", SUPER_ADMIN_PASSWORD="FixtureOnly123!")
sys.path.insert(0, str(root / "backend"))
from app.services.encryption_service import EncryptionService

encryption = EncryptionService("a" * 64)
password = encryption.encrypt("preserved-mail-password")
totp = encryption.encrypt("JBSWY3DPEHPK3PXP")
configuration = Config()
configuration.set_main_option("script_location", str(root / "backend/alembic").replace("%", "%%"))
configuration.set_main_option("sqlalchemy.url", "sqlite:///" + str(data / "monitor.db").replace("%", "%%"))
command.upgrade(configuration, "20261001_0004")
with sqlite3.connect(data / "monitor.db") as connection:
    connection.execute("INSERT INTO email_accounts (email,password,totp_secret,management_status,registrant,operator,remark,created_at,updated_at) VALUES (?,?,?,'闲置','admin','admin','preserved-note',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", ("fixture@example.invalid", password, totp))
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261001_0004"
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
environment = {**os.environ, "TKCRM_DATA_DIR": str(data), "TKCRM_LEGACY_DATA_DIR": "", "TKCRM_MANAGED": "1", "PORT": str(port), "PYTHONUTF8": "1"}
for name in ["DATABASE_URL", "UPDATE_AGENT_URL", "UPDATE_AGENT_TOKEN", "TKCRM_DESKTOP_AGENT_URL", "TKCRM_DESKTOP_AGENT_TOKEN"]:
    environment.pop(name, None)

def request(endpoint, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    with urlopen(Request(f"http://127.0.0.1:{port}" + endpoint, data=body, headers=headers), timeout=2) as response:
        return json.load(response)

with (data / "server.log").open("wb") as log:
    process = subprocess.Popen([str(root / "desktop/runtime/windows-x64/server/TkCrm.Server.exe")], cwd=data, env=environment, stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 60
        while True:
            assert process.poll() is None, "Frozen server exited; see " + str(data / "server.log")
            try:
                if request("/health")["status"] == "ok":
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline, "Frozen server health timeout"
            time.sleep(0.25)
        token = request("/api/auth/login", {"username": "admin", "password": "FixtureOnly123!"})["access_token"]
        result = request("/api/emails?skip=0&limit=50", token=token)
        item = next(item for item in result["items"] if item["email"] == "fixture@example.invalid")
        assert item["password"] == "preserved-mail-password"
        assert item["totp_secret"] == "JBSWY3DPEHPK3PXP"
        assert item["remark"] == "preserved-note"
        assert (data / ".env").read_text(encoding="utf-8") == configuration_text
        with sqlite3.connect(data / "monitor.db") as connection:
            revisions = {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")}
            assert revisions == set(ScriptDirectory.from_config(configuration).get_heads())
            assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert connection.execute("SELECT password,totp_secret FROM email_accounts WHERE email=?", ("fixture@example.invalid",)).fetchone() == (password, totp)
        backups = list((data / "backups").glob("*.db"))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261001_0004"
            assert connection.execute("SELECT password FROM email_accounts WHERE email=?", ("fixture@example.invalid",)).fetchone()[0] == password
        print("PASS frozen server: old schema migrated, encrypted fields readable, ciphertext/config preserved, pre-migration backup valid")
    finally:
        if process.poll() is None:
            process.stdin.write(b"shutdown\n")
            process.stdin.flush()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        print("Fixture logs: " + str(data))
    assert process.returncode == 0, "Frozen server shutdown failed"
