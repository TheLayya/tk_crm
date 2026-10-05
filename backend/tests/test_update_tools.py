import json
import tarfile
import threading
from pathlib import Path

import pytest

from tools.updater import prepare_release, safe_extract, validate_manifest, version_tuple
from tools import updater
import sqlite3
import subprocess
from tools.update_agent import Agent


def test_release_version_and_manifest_validation():
    assert version_tuple("v1.2.3") == (1, 2, 3)
    with pytest.raises(ValueError):
        version_tuple("main")
    manifest = {
        "version": "1.2.3",
        "package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1.2.3/app.tar.gz",
        "sha256": "a" * 64,
        "changes": ["change"],
    }
    assert validate_manifest(manifest) == manifest
    with pytest.raises(ValueError):
        validate_manifest({**manifest, "sha256": "0"})
    with pytest.raises(ValueError):
        validate_manifest({**manifest, "package_url": "https://example.com/app.tar.gz"})


def test_service_lifecycle_uses_phase_working_directories(tmp_path, monkeypatch):
    from tools.updater import ServiceLifecycle

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, cwd, **kwargs: calls.append((command, cwd)))
    lifecycle = ServiceLifecycle({
        "stop": [["stop"]],
        "migrate": [["migrate"], ["build"]],
        "migrate_cwds": ["backend", "."],
        "start": [["start"]],
        "health_url": "http://127.0.0.1:1/health",
    })

    lifecycle("migrate", tmp_path)

    assert calls == [
        (["migrate"], tmp_path / "backend"),
        (["build"], tmp_path),
    ]


def test_update_agent_records_install_history(tmp_path):
    agent = Agent(tmp_path, "x" * 32, None)
    agent._record_history({"version": "1.2.3", "date": "2026-10-02", "changes": ["fixed"]})

    history = json.loads((tmp_path / "backend/data/update-history.json").read_text(encoding="utf-8"))
    assert history[0]["version"] == "1.2.3"
    assert history[0]["changes"] == ["fixed"]
    assert history[0]["installed_at"]


def test_update_agent_persists_state_across_restart(tmp_path, monkeypatch):
    lifecycle = lambda phase, root: None
    manifest = {"version": "1.2.3", "date": "2026-10-02", "changes": []}
    monkeypatch.setattr("tools.update_agent.apply_release", lambda *args: None)
    first = Agent(tmp_path, "x" * 32, lifecycle)
    assert first.start(manifest)
    first.lock.acquire()
    first.lock.release()
    assert first.snapshot()["status"] == "completed"

    restored = Agent(tmp_path, "x" * 32, lifecycle)
    assert restored.snapshot()["status"] == "completed"
    assert restored.snapshot()["latest_version"] == "1.2.3"


@pytest.mark.parametrize("update_fails", [False, True])
def test_update_agent_completion_callback_runs_after_success(tmp_path, monkeypatch, update_fails):
    completed = []
    finished = threading.Event()

    def apply(*_):
        if update_fails:
            raise RuntimeError("migration failed")

    def on_completed():
        restored = Agent(tmp_path, "x" * 32, None)
        assert restored.snapshot()["status"] == "completed"
        assert not agent.lock.locked()
        completed.append(True)
        finished.set()

    monkeypatch.setattr("tools.update_agent.apply_release", apply)
    agent = Agent(
        tmp_path,
        "x" * 32,
        lambda phase, root: None,
        on_completed=on_completed,
    )
    assert agent.start({"version": "1.2.3", "changes": []})
    agent.lock.acquire()
    agent.lock.release()
    if update_fails:
        assert agent.snapshot()["status"] == "failed"
        assert completed == []
    else:
        assert finished.wait(2)
        assert completed == [True]


def test_update_agent_marks_interrupted_update_failed(tmp_path):
    agent = Agent(tmp_path, "x" * 32, None)
    agent._set_state(status="running", latest_version="1.2.3")
    restarted = Agent(tmp_path, "x" * 32, None)
    assert restarted.snapshot()["status"] == "failed"
    assert restarted.snapshot()["latest_version"] == "1.2.3"


@pytest.mark.parametrize("frontend_status", [200, 503])
def test_service_lifecycle_requires_frontend_health(tmp_path, monkeypatch, frontend_status):
    from tools.updater import ServiceLifecycle

    responses = {
        "http://backend/health": (200, {"status": "ok"}),
        "http://frontend/": (frontend_status, None),
    }
    checked = []

    class Response:
        def __init__(self, status, payload):
            self.status, self.payload = status, payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _):
            return json.dumps(self.payload).encode()

    def open_url(request, timeout=3):
        checked.append(request)
        return Response(*responses[request])

    times = iter([0, 0, 2])
    monkeypatch.setattr("tools.updater.urlopen", open_url)
    monkeypatch.setattr("tools.updater.time.monotonic", lambda: next(times))
    monkeypatch.setattr("tools.updater.time.sleep", lambda _: None)
    lifecycle = ServiceLifecycle({
        "stop": [["stop"]],
        "migrate": [["migrate"]],
        "start": [["start"]],
        "health_url": "http://backend/health",
        "frontend_health_url": "http://frontend/",
        "health_timeout": 1,
    })
    if frontend_status == 200:
        lifecycle("health", tmp_path)
    else:
        with pytest.raises(RuntimeError, match="health check"):
            lifecycle("health", tmp_path)
    assert checked == ["http://backend/health", "http://frontend/"]


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        import io
        handle.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "out")


def test_prepare_release_accepts_only_code_package(tmp_path):
    source = tmp_path / "package"
    (source / "backend/app").mkdir(parents=True)
    (source / "frontend").mkdir()
    (source / "backend/app/main.py").write_text("app = True", encoding="utf-8")
    (source / "backend/alembic.ini").write_text("[alembic]", encoding="utf-8")
    (source / "frontend/package.json").write_text("{}", encoding="utf-8")
    (source / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    (source / "version.json").write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
    (source / "README.md").write_text("release", encoding="utf-8")
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for item in source.rglob("*"):
            handle.add(item, item.relative_to(source.parent), recursive=False)
    package = prepare_release(archive, tmp_path / "staging", "1.2.3")
    assert (package / "backend/app/main.py").is_file()


def test_prepare_release_accepts_nested_env_templates(tmp_path):
    source = tmp_path / "package"
    (source / "backend").mkdir(parents=True)
    (source / "frontend").mkdir()
    (source / "backend/app").mkdir()
    (source / "backend/app/main.py").write_text("app = True", encoding="utf-8")
    (source / "backend/alembic.ini").write_text("[alembic]", encoding="utf-8")
    (source / "frontend/package.json").write_text("{}", encoding="utf-8")
    (source / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    (source / "version.json").write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
    (source / "backend/.env.example").write_text("KEY=value", encoding="utf-8")
    (source / "frontend/.env.example").write_text("VITE_KEY=value", encoding="utf-8")
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for item in source.rglob("*"):
            handle.add(item, item.relative_to(source.parent), recursive=False)
    package = prepare_release(archive, tmp_path / "staging", "1.2.3")
    assert (package / "backend/.env.example").is_file()


def test_update_rollback_removes_new_database(tmp_path, monkeypatch):
    root = tmp_path / "fresh"
    (root / "backend/app").mkdir(parents=True)
    (root / "backend/data").mkdir(parents=True)
    (root / "backend/app/main.py").write_text("old", encoding="utf-8")
    source = tmp_path / "new-code"
    (source / "backend/app").mkdir(parents=True)
    (source / "backend/app/main.py").write_text("new", encoding="utf-8")
    database = root / "backend/data/monitor.db"
    manifest = {
        "version": "1.2.3", "sha256": "a" * 64,
        "package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1.2.3/app.tar.gz"
    }
    monkeypatch.setattr(updater, "download_package", lambda *args: None)
    monkeypatch.setattr(updater, "prepare_release", lambda *args: source)

    def lifecycle(phase, directory):
        if phase == "migrate":
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE created (value TEXT)")
            finally:
                connection.close()
            raise RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        updater.apply_release(root, manifest, lifecycle)
    assert not database.exists()
    assert (root / "backend/app/main.py").read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize("migration_fails", [False, True])
def test_update_transaction_preserves_runtime_and_rolls_back(tmp_path, monkeypatch, migration_fails):
    root = tmp_path / "中文 workspace"
    (root / "backend/data").mkdir(parents=True)
    (root / "backend/app").mkdir()
    (root / "backend/.venv312").mkdir()
    (root / "backend/.env").write_text("private-config", encoding="utf-8")
    (root / "backend/.venv312/marker").write_text("keep", encoding="utf-8")
    (root / "backend/app/main.py").write_text("old", encoding="utf-8")
    database = root / "backend/data/monitor.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('original')")
    source = tmp_path / "new-code"
    (source / "backend/app").mkdir(parents=True)
    (source / "backend/app/main.py").write_text("new", encoding="utf-8")
    (source / "backend/app/new.py").write_text("added", encoding="utf-8")
    manifest = {
        "version": "1.2.3", "sha256": "a" * 64,
        "package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1.2.3/app.tar.gz"
    }
    monkeypatch.setattr(updater, "download_package", lambda *args: None)
    monkeypatch.setattr(updater, "prepare_release", lambda *args: source)
    phases = []

    def lifecycle(phase, directory):
        assert directory == root.resolve()
        phases.append(phase)
        if phase == "migrate":
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE records SET value='migrated'")
            if migration_fails:
                raise RuntimeError("migration failed")

    if migration_fails:
        with pytest.raises(RuntimeError, match="migration failed"):
            updater.apply_release(root, manifest, lifecycle)
    else:
        recovery = updater.apply_release(root, manifest, lifecycle)
        assert (recovery / "monitor.db").is_file()
    assert (root / "backend/.env").read_text(encoding="utf-8") == "private-config"
    assert (root / "backend/.venv312/marker").read_text(encoding="utf-8") == "keep"
    assert (root / "backend/app/main.py").read_text(encoding="utf-8") == ("old" if migration_fails else "new")
    assert (root / "backend/app/new.py").exists() == (not migration_fails)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == ("original" if migration_fails else "migrated")
    assert phases[-2:] == ["start", "health"]
