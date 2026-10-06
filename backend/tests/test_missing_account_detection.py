import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.monitor import latest_check_summary
from app.services.scraper_service import ACCOUNT_NOT_FOUND, ScraperService


def client_for(response):
    return SimpleNamespace(get=AsyncMock(return_value=response))


@pytest.mark.parametrize("status", [200, 404])
def test_explicit_missing_profile_detected(status):
    service = ScraperService()
    response = httpx.Response(status, text="<h1>Couldn't find this account</h1>")
    result = asyncio.run(service._try_oembed_api(client_for(response), "missing"))
    assert result["error_code"] == "account_not_found"


@pytest.mark.parametrize("status,text", [
    (404, "Not found"), (403, "Access denied"), (200, "Verify you are human"),
    (200, '<script>{"translation":"Couldn\'t find this account"}</script>'),
])
def test_network_or_generic_errors_do_not_mark_account_missing(status, text):
    result = asyncio.run(ScraperService()._try_oembed_api(client_for(httpx.Response(status, text=text)), "test"))
    assert result.get("error_code") != "account_not_found"


@pytest.mark.parametrize("method", ["_try_web_api", "_try_oembed_api"])
def test_waf_response_is_not_missing_account(method):
    response = httpx.Response(200, text='<script id="slardar-config">{"slardarClient":"SlardarWAF"}</script><body>Please wait...</body>')
    result = asyncio.run(getattr(ScraperService(), method)(client_for(response), "test"))
    assert result["error_code"] == "verification_required"
    assert "无法判断" in result["error"]


def test_browser_missing_account_dom_detected():
    response = httpx.Response(200, text='<div class="css-va67fb-7937d88b--DivErrorContainer ewerbqq0"><p>找不到此账号</p><p>寻找视频？试试浏览我们的热门创作者、话题标签和音乐。</p></div>')
    result = asyncio.run(ScraperService()._try_oembed_api(client_for(response), ".oceanszlyhh"))
    assert result["error_code"] == "account_not_found"


def test_empty_profile_is_not_missing_account():
    result = asyncio.run(ScraperService()._try_oembed_api(client_for(httpx.Response(200, text="")), "test"))
    assert result.get("error_code") != "account_not_found"


def test_latest_summary_identifies_verification_block():
    history = SimpleNamespace(check_status="failed", error_message="VERIFICATION_REQUIRED: blocked")
    assert latest_check_summary(history)["latest_check_status"] == "verification_required"


def test_non_json_api_has_readable_error():
    result = asyncio.run(ScraperService()._try_web_api(client_for(httpx.Response(200, text="")), "test"))
    assert "非 JSON" in result["error"]
    assert "Expecting value" not in result["error"]


def test_empty_profile_has_readable_error():
    result = asyncio.run(ScraperService()._try_oembed_api(client_for(httpx.Response(200, text="")), "test"))
    assert "无法判断" in result["error"]
    assert "oEmbed" not in result["error"]


def test_existing_profile_wins_over_missing_text():
    payload = {"__DEFAULT_SCOPE__": {"webapp.user-detail": {"userInfo": {"user": {"id": "123"}, "stats": {}}}}}
    text = '<h1>Couldn\'t find this account</h1><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">' + json.dumps(payload) + '</script>'
    result = asyncio.run(ScraperService()._try_oembed_api(client_for(httpx.Response(200, text=text)), "test"))
    assert result["success"] is True


@pytest.mark.parametrize("method", ["_try_web_api", "_try_oembed_api"])
def test_profile_without_follower_stats_does_not_fabricate_zero(method):
    if method == "_try_web_api":
        response = httpx.Response(200, json={"userInfo": {"user": {"id": "123"}, "stats": {}}})
    else:
        payload = {"__DEFAULT_SCOPE__": {"webapp.user-detail": {
            "userInfo": {"user": {"id": "123"}, "stats": {}}
        }}}
        text = '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">' + json.dumps(payload) + '</script>'
        response = httpx.Response(200, text=text)
    result = asyncio.run(getattr(ScraperService(), method)(client_for(response), "test"))
    assert result["success"] is True
    assert "follower_count" not in result["data"]


def test_api_explicit_missing_message():
    response = httpx.Response(200, json={"statusMsg": "user not found"})
    result = asyncio.run(ScraperService()._try_web_api(client_for(response), "test"))
    assert result["error_code"] == "account_not_found"


def test_fallback_preserves_missing_code_and_success_can_recover():
    service = ScraperService()
    missing = {"success": False, "data": None, "error": ACCOUNT_NOT_FOUND, "error_code": "account_not_found"}
    success = {"success": True, "data": {"tiktok_id": "123"}, "error": None}
    with patch("app.services.scraper_service.httpx.AsyncClient") as client:
        client.return_value.__aenter__.return_value = SimpleNamespace()
        service._try_web_api = AsyncMock(return_value=missing)
        service._try_oembed_api = AsyncMock(return_value={"success": False, "error": "Timeout"})
        result = asyncio.run(service.fetch_user_info("test"))
        assert result["error_code"] == "account_not_found"
        service._try_oembed_api = AsyncMock(return_value=success)
        assert asyncio.run(service.fetch_user_info("test"))["success"] is True


def test_latest_summary_separates_failure_missing_and_success():
    assert latest_check_summary(None)["latest_check_status"] == "pending"
    for error, expected in [(ACCOUNT_NOT_FOUND, "not_found"), ("Timeout", "failed")]:
        assert latest_check_summary(SimpleNamespace(check_status="failed", error_message=error))["latest_check_status"] == expected
    assert latest_check_summary(SimpleNamespace(check_status="success", error_message=None))["latest_check_status"] == "success"
