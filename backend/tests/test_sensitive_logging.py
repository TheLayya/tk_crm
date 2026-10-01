import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import backup_service, proxy_node_test_service


def test_proxy_check_does_not_log_proxy_credentials(monkeypatch, caplog):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            raise RuntimeError("socks5://proxy-user:proxy-password@127.0.0.1:1080")

    monkeypatch.setattr(proxy_node_test_service.httpx, "AsyncClient", lambda **kwargs: Client())
    node = SimpleNamespace(
        id=7,
        protocol="socks5",
        ip="127.0.0.1",
        port=1080,
        username="proxy-user",
        password="proxy-password",
        relay_ip=None,
        relay_port=None,
        relay_protocol=None,
    )

    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(proxy_node_test_service._do_test(node))

    assert result["success"] is False
    assert "RuntimeError" in result["error"]
    assert "proxy-password" not in result["error"]
    assert "proxy-user" not in caplog.text
    assert "proxy-password" not in caplog.text
    assert "socks5://" not in caplog.text


@pytest.mark.parametrize("fails", [False, True])
def test_notification_logs_do_not_include_response_or_exception(monkeypatch, tmp_path, fails):
    class Response:
        status_code = 500
        text = "bot-token-leak"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            if fails:
                raise RuntimeError("bot-token-leak")
            return Response()

    monkeypatch.setattr(backup_service.httpx, "AsyncClient", lambda **kwargs: Client())
    error_logger = Mock()
    monkeypatch.setattr(backup_service.logger, "error", error_logger)
    file_path = Path(tmp_path) / "backup.zip"
    file_path.write_bytes(b"backup")

    asyncio.run(backup_service.send_telegram("bot-token", "chat", file_path, "backup"))

    logged = repr(error_logger.call_args_list)
    assert "Telegram notification failed" in logged
    assert "bot-token-leak" not in logged
    assert "bot-token" not in logged


def test_email_notification_does_not_log_exception_credentials(monkeypatch, tmp_path):
    def send_email(*args):
        raise RuntimeError("smtp-password-leak")

    monkeypatch.setattr(backup_service, "_send_email_sync", send_email)
    error_logger = Mock()
    monkeypatch.setattr(backup_service.logger, "error", error_logger)
    asyncio.run(backup_service.send_email(
        "smtp.example.com", 587, "user", "smtp-password-leak",
        "sender@example.com", "recipient@example.com", True,
        tmp_path / "backup.zip", "backup",
    ))

    logged = repr(error_logger.call_args_list)
    assert "Email notification failed" in logged
    assert "smtp-password-leak" not in logged
