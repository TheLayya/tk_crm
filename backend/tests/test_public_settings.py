import pytest

from app.models.monitor import MonitorSettings
from .conftest import auth_headers


@pytest.fixture(autouse=True)
def clean_settings(db):
    db.query(MonitorSettings).delete()
    db.commit()
    yield
    db.query(MonitorSettings).delete()
    db.commit()


def test_public_settings_exposes_only_branding(client, db):
    db.add(MonitorSettings(
        id=1,
        default_interval=14400,
        max_concurrent_checks=5,
        request_timeout=30,
        default_video_count=20,
        site_name="演示站点",
        logo_image="data:image/png;base64,logo",
        login_screen_text="Welcome to our team",
        telegram_bot_token="telegram-secret",
        smtp_username="smtp-user",
        smtp_password="smtp-secret",
    ))
    db.commit()

    response = client.get("/api/settings/public")

    assert response.status_code == 200
    assert response.json() == {
        "site_name": "演示站点",
        "logo_image": "data:image/png;base64,logo",
        "login_screen_text": "Welcome to our team",
    }


@pytest.mark.parametrize("submitted", [None, "", "********", "replacement-secret"])
def test_saving_settings_preserves_or_replaces_notification_secrets(client, db, super_admin, submitted):
    settings = MonitorSettings(id=1, telegram_bot_token="telegram-original", smtp_password="smtp-original")
    db.add(settings)
    db.commit()
    headers = auth_headers(super_admin)
    loaded = client.get("/api/settings", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["telegram_bot_token"] == "********"
    assert loaded.json()["smtp_password"] == "********"

    response = client.put("/api/settings", headers=headers, json={
        "site_name": "更新站名",
        "telegram_bot_token": submitted,
        "smtp_password": submitted,
    })

    assert response.status_code == 200, response.text
    assert response.json()["telegram_bot_token"] == "********"
    assert response.json()["smtp_password"] == "********"
    db.refresh(settings)
    assert settings.site_name == "更新站名"
    assert settings.telegram_bot_token == (submitted if submitted == "replacement-secret" else "telegram-original")
    assert settings.smtp_password == (submitted if submitted == "replacement-secret" else "smtp-original")


@pytest.mark.parametrize("screen_text", ["Teamwork creates value", "", "<script>alert(1)</script>"])
def test_login_screen_text_saved_and_public(client, super_admin, screen_text):
    response = client.put("/api/settings", headers=auth_headers(super_admin), json={
        "login_screen_text": screen_text,
    })
    assert response.status_code == 200, response.text
    assert response.json()["login_screen_text"] == screen_text
    assert client.get("/api/settings/public").json()["login_screen_text"] == screen_text


def test_login_screen_text_length_limit(client, super_admin):
    response = client.put("/api/settings", headers=auth_headers(super_admin), json={
        "login_screen_text": "a" * 501,
    })
    assert response.status_code == 422
