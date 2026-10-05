import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop_static import mount_frontend


@pytest.fixture
def frontend_client(tmp_path):
    (tmp_path / "index.html").write_text("<h1>CRM</h1>", encoding="utf-8")
    (tmp_path / "login").mkdir()
    (tmp_path / "login/room.jpg").write_bytes(b"image")
    app = FastAPI()

    @app.get("/api/example")
    def example():
        return {"ok": True}

    mount_frontend(app, str(tmp_path))
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/login", "/login/", "/card-keys", "/devices/123"])
def test_spa_routes(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 200
    assert response.text == "<h1>CRM</h1>"


def test_assets_and_api_are_not_spa_fallback(frontend_client):
    assert frontend_client.get("/login/room.jpg").content == b"image"
    assert frontend_client.get("/missing.js").status_code == 404
    assert frontend_client.get("/api/missing").status_code == 404
    assert frontend_client.get("/api/example").json() == {"ok": True}
    assert frontend_client.post("/card-keys").status_code == 405


def test_missing_frontend_fails_explicitly(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        mount_frontend(FastAPI(), str(tmp_path))
