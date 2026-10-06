import pytest
import json
from fastapi import HTTPException

from app.api import updates


def test_health_reports_running_version(client):
    from app.version import APP_VERSION

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": APP_VERSION}


def test_desktop_history_is_read_without_losing_changelog(tmp_path, monkeypatch):
    history = [{
        "version": "v2.0.0", "date": "2026-10-05",
        "changes": ["保留中文更新说明"],
        "installed_at": "2026-10-05T12:00:00+08:00",
    }, {"version": "1.0.0"}]
    history_path = tmp_path / "update-history.json"
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(updates, "HISTORY_PATH", history_path)
    assert updates.update_history() == {"items": history}


@pytest.fixture
def release(monkeypatch):
    manifest = {
        "version": "99.0.0",
        "package_url": "https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/app.tar.gz",
        "sha256": "a" * 64,
        "changes": ["Test release"],
    }
    monkeypatch.setattr(updates, "_manifest", lambda: manifest)
    monkeypatch.setattr(updates.settings, "UPDATE_AGENT_URL", "http://127.0.0.1:8765")
    monkeypatch.setattr(updates.settings, "UPDATE_AGENT_TOKEN", "test-token")
    return manifest


def test_server_update_does_not_require_windows_package(release, monkeypatch):
    monkeypatch.setattr(updates.settings, "UPDATE_CLIENT_TYPE", "server")
    monkeypatch.setattr(updates, "_agent_request", lambda method, path, payload: {"status": "running"})
    result = updates.check_update()
    assert result["client_type"] == "server"
    assert result["desktop_supported"] is None
    assert result["configured"]
    assert updates.apply_update() == {"status": "running"}


def test_desktop_rejects_source_only_release(release, monkeypatch):
    monkeypatch.setattr(updates.settings, "UPDATE_CLIENT_TYPE", "desktop")
    result = updates.check_update()
    assert result["has_update"]
    assert result["desktop_supported"] is False
    with pytest.raises(HTTPException) as error:
        updates.apply_update()
    assert error.value.status_code == 409
    assert "Windows installer" in error.value.detail


def test_desktop_accepts_windows_only_release(release, monkeypatch):
    monkeypatch.setattr(updates.settings, "UPDATE_CLIENT_TYPE", "desktop")
    release.pop("package_url")
    release.pop("sha256")
    release.update(
        windows_package_url="https://github.com/TheLayya/tk_crm/releases/download/v99.0.0/TkCRM-99.0.0-win-x64-setup.exe",
        windows_sha256="b" * 64,
    )
    calls = []
    monkeypatch.setattr(updates, "_agent_request", lambda *args: calls.append(args) or {"status": "running"})
    assert updates.check_update()["desktop_supported"] is True
    assert updates.apply_update() == {"status": "running"}
    assert calls == [("POST", "/apply", release)]


@pytest.mark.parametrize("fields", [
    {"windows_package_url": "https://example.com/setup.exe", "windows_sha256": "b" * 64},
    {"windows_package_url": "https://github.com/another/repo/releases/download/v1/setup.exe", "windows_sha256": "b" * 64},
    {"windows_package_url": "https://user:password@github.com/TheLayya/tk_crm/releases/download/v1/setup.exe", "windows_sha256": "b" * 64},
    {"windows_package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1/setup.exe#fragment", "windows_sha256": "b" * 64},
    {"windows_package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1/setup.exe", "windows_sha256": "invalid"},
    {"windows_sha256": "b" * 64},
    {"windows_package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1/setup.exe?download=1", "windows_sha256": "b" * 64},
    {"windows_package_url": "https://github.com/TheLayya/tk_crm/releases/download/v1/source.tar.gz", "windows_sha256": "b" * 64},
])
def test_invalid_windows_manifest_is_rejected(fields):
    with pytest.raises(ValueError):
        updates._has_windows_package(fields)


def test_apply_timeout_allows_updater_startup_handshake(monkeypatch):
    from io import BytesIO

    calls = []

    def open_agent(request, timeout):
        calls.append((request.method, timeout))
        return BytesIO(b'{"status":"running"}')

    monkeypatch.setattr(updates.settings, "UPDATE_AGENT_URL", "http://127.0.0.1:8765")
    monkeypatch.setattr(updates.settings, "UPDATE_AGENT_TOKEN", "fixture-token")
    monkeypatch.setattr(updates, "urlopen", open_agent)
    assert updates._agent_request("POST", "/apply", {}) == {"status": "running"}
    assert updates._agent_request("GET", "/status") == {"status": "running"}
    assert calls == [("POST", 15), ("GET", 5)]
