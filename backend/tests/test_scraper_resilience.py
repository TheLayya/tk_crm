"""Offline checks for bounded retries, honest partial results and safe errors."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from socksio.exceptions import ProtocolError

from app.services import scraper_service as module
from app.services.scraper_service import ScraperService, is_retryable_result


@pytest.fixture
def fast_retry(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    monkeypatch.setattr(module.random, "uniform", lambda *args: 0)
    return sleep


def transport_client(monkeypatch, handler):
    real_client = httpx.AsyncClient
    options = []

    def create(**kwargs):
        options.append(kwargs.copy())
        kwargs.pop("proxies", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", create)
    return options


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout("secret-token"), httpx.ConnectError("secret-token"),
    httpx.ProxyError("socks5://user:secret@host"), ProtocolError("Malformed reply"),
    httpx.Response(429), httpx.Response(502), httpx.Response(503), httpx.Response(504),
])
def test_transient_failure_retries_and_can_recover(fast_retry, failure):
    success = httpx.Response(200, json={"userInfo": {"user": {"id": "123"}}})
    client = SimpleNamespace(get=AsyncMock(side_effect=[failure, failure, success]))
    result = asyncio.run(ScraperService()._try_web_api(client, "test"))
    assert result["success"] is True
    assert client.get.await_count == 3
    assert [call.args[0] for call in fast_retry.await_args_list] == [1, 2]


@pytest.mark.parametrize("response,code", [
    (httpx.Response(200, json={}), "missing_profile_data"),
    (httpx.Response(200, json=[]), "invalid_response"),
    (httpx.Response(200, json={"userInfo": "wrong"}), "invalid_response"),
    (httpx.Response(200, text="not JSON"), "invalid_response"),
    (httpx.Response(200, json={"statusMsg": "user not found"}), "account_not_found"),
    (httpx.Response(200, text="Verify you are human"), "verification_required"),
    (httpx.Response(503, text="SlardarWAF"), "verification_required"),
    (httpx.Response(403), "http_error"),
])
def test_terminal_responses_are_not_retried(fast_retry, response, code):
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    result = asyncio.run(ScraperService()._try_web_api(client, "test"))
    assert result["error_code"] == code
    assert not is_retryable_result(result)
    assert client.get.await_count == 1
    fast_retry.assert_not_awaited()


def test_retry_budget_and_proxy_errors_are_safe(fast_retry, caplog, monkeypatch):
    client = SimpleNamespace(get=AsyncMock(side_effect=ProtocolError(
        "Malformed reply from socks5://proxy-user:proxy-password@host?msToken=secret-token"
    )))
    monkeypatch.setattr(module.logger, "disabled", False)
    with caplog.at_level(logging.DEBUG, logger=module.logger.name):
        result = asyncio.run(ScraperService()._try_web_api(client, "test"))
    assert result["error_code"] == "proxy_error"
    assert is_retryable_result(result)
    assert client.get.await_count == 3
    assert "ProtocolError" in caplog.text
    for secret in ("proxy-user", "proxy-password", "secret-token", "socks5://"):
        assert secret not in caplog.text
        assert secret not in result["error"]


@pytest.mark.parametrize("retry_after,delay", [
    ("9999", 10), ("4", 4), ("invalid", 1),
    (format_datetime(datetime.now(timezone.utc) + timedelta(hours=1)), 10),
])
def test_retry_after_is_respected_and_bounded(fast_retry, retry_after, delay):
    client = SimpleNamespace(get=AsyncMock(side_effect=[
        httpx.Response(429, headers={"Retry-After": retry_after}), httpx.Response(200),
    ]))
    asyncio.run(ScraperService()._get_with_retry(client, "https://test", {}))
    fast_retry.assert_awaited_once_with(delay)


def test_api_verification_survives_failing_profile_fallback(monkeypatch):
    service = ScraperService()
    service._try_web_api = AsyncMock(return_value={"success": False, "error_code": "verification_required"})
    service._try_oembed_api = AsyncMock(return_value={"success": False, "error_code": "timeout"})
    transport_client(monkeypatch, lambda request: httpx.Response(200))
    result = asyncio.run(service.fetch_user_info("test", timeout=7))
    assert result["error_code"] == "verification_required"
    assert not is_retryable_result(result)


@pytest.mark.parametrize("api_response,page_response,code", [
    (httpx.Response(503), httpx.Response(200, text=""), "upstream_unavailable"),
    (httpx.Response(200, json={}), httpx.ReadTimeout("secret"), "timeout"),
])
def test_profile_fallback_preserves_transient_failure(monkeypatch, fast_retry, api_response, page_response, code):
    def respond(request):
        outcome = api_response if request.url.path == "/api/user/detail/" else page_response
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    options = transport_client(monkeypatch, respond)
    result = asyncio.run(ScraperService().fetch_user_info("test", timeout=7))
    assert result["success"] is False
    assert result["error_code"] == code
    assert is_retryable_result(result)
    assert is_retryable_result({"error": result["error"]})
    assert result["causes"]["user_api"] is not None
    assert result["causes"]["profile_page"] is not None
    assert options[0]["timeout"] == 7


@pytest.mark.parametrize("response,code", [
    (httpx.Response(503), "upstream_unavailable"),
    (httpx.Response(200, text="Verify you are human"), "verification_required"),
])
def test_video_warmup_failure_is_not_ignored(monkeypatch, fast_retry, response, code):
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return response

    transport_client(monkeypatch, respond)
    result = asyncio.run(ScraperService().fetch_user_videos("secret-sec"))
    assert result["success"] is False
    assert result["error_code"] == code
    assert set(requests) == {"/api/user/detail/"}


@pytest.mark.parametrize("response,code", [
    (httpx.Response(200, text=""), "invalid_response"),
    (httpx.Response(200, text="not JSON"), "invalid_response"),
    (httpx.Response(200, json=[]), "invalid_response"),
    (httpx.Response(200, json={"statusCode": 10204, "itemList": []}), "video_restricted"),
    (httpx.Response(200, text="Verify you are human"), "verification_required"),
])
def test_video_response_errors_are_readable_and_terminal(monkeypatch, fast_retry, response, code):
    calls = []

    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200) if request.url.path == "/api/user/detail/" else response

    transport_client(monkeypatch, respond)
    result = asyncio.run(ScraperService().fetch_user_videos("sec"))
    assert result["success"] is False
    assert result["error_code"] == code
    assert not is_retryable_result(result)
    assert len(calls) == 2
    fast_retry.assert_not_awaited()


def test_empty_token_is_diagnostic_only_and_timeout_is_forwarded(monkeypatch, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"statusCode": 0, "itemList": []})

    options = transport_client(monkeypatch, respond)
    monkeypatch.setattr(module.logger, "disabled", False)
    with caplog.at_level(logging.WARNING, logger=module.logger.name):
        result = asyncio.run(ScraperService().fetch_user_videos("secret-sec", timeout=9))
    assert result == {"success": True, "data": [], "error": None}
    assert options[0]["timeout"] == 9
    assert "did not supply msToken" in caplog.text
    assert "secret-sec" not in caplog.text
    assert len(requests) == 2


@pytest.mark.parametrize("failure,code,retryable", [
    (httpx.Response(503), "upstream_unavailable", True),
    (httpx.Response(200, text="not JSON"), "invalid_response", False),
    (httpx.Response(200, text="Verify you are human"), "verification_required", False),
])
def test_later_page_failure_is_partial_not_complete(monkeypatch, fast_retry, failure, code, retryable):
    page_calls = 0

    def respond(request):
        nonlocal page_calls
        if request.url.path == "/api/user/detail/":
            return httpx.Response(200)
        page_calls += 1
        if page_calls == 1:
            return httpx.Response(200, json={"statusCode": 0, "hasMore": True, "itemList": [
                {"id": "1", "createTime": 1700000000, "stats": {"playCount": 5}},
            ]})
        return failure

    transport_client(monkeypatch, respond)
    result = asyncio.run(ScraperService().fetch_user_videos("sec", max_count=20))
    assert result["partial"] is True
    assert result["data"][0]["video_id"] == "1"
    assert result["error_code"] == "partial_result"
    assert result["cause_error_code"] == code
    assert is_retryable_result(result) is retryable
    assert "PARTIAL_RESULT" in result["error"]


def test_proxy_url_escapes_credentials_and_brackets_ipv6():
    proxy = SimpleNamespace(username="user@name", password="p@ss:/?#", host="::1", port=1080, proxy_type="socks5")
    assert ScraperService()._build_proxy_url(proxy) == "socks5://user%40name:p%40ss%3A%2F%3F%23@[::1]:1080"


@pytest.mark.parametrize("response,success,code", [
    (httpx.Response(200, text="TikTok"), True, None),
    (httpx.Response(200, text="Verify you are human"), False, "verification_required"),
    (httpx.Response(403), False, "http_error"),
    (httpx.Response(429), False, "rate_limited"),
    (httpx.Response(503), False, "upstream_unavailable"),
])
def test_proxy_check_reports_blocked_tiktok_connection(monkeypatch, response, success, code):
    transport_client(monkeypatch, lambda request: response)
    result = asyncio.run(ScraperService().test_proxy(None))
    assert result["success"] is success
    assert result["error_code"] == code
    assert result["error"] is None if success else result["error"]


@pytest.mark.parametrize("message,retryable", [
    ("COLLECTION_INTERRUPTED: restart", True), ("VIDEO_COLLECTION_FAILED: TIMEOUT: 请求超时", True),
    ("User API: Timeout; profile page: HTTP 200 empty", False),
    ("VERIFICATION_REQUIRED: blocked; HTTP 503", False),
    ("ACCOUNT_NOT_FOUND: missing; Timeout", False),
])
def test_stored_legacy_errors_use_safe_retry_policy(message, retryable):
    assert is_retryable_result({"error": message}) is retryable
