import json
import tarfile
from pathlib import Path

import pytest

from tools.updater import prepare_release, safe_extract, validate_manifest, version_tuple
from tools import updater
import sqlite3


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
