from datetime import datetime

import pytest

from app.models.op_account import OpAccount
from app.services.gmail_checker_service import apply_check_results, check_gmail_accounts, normalize_status


def test_gmail_status_mapping_and_apply_results(db):
    account = OpAccount(platform="gmail", account="demo@gmail.com")
    checked_at = datetime(2026, 10, 1, 12, 0)
    assert normalize_status("Disabled") == "封禁"
    assert apply_check_results([account], [{"email": "DEMO@gmail.com", "status": "live"}], checked_at) == 1
    assert account.gmail_check_status == "正常"
    assert account.gmail_check_raw_status == "live"
    assert account.gmail_checked_at == checked_at


@pytest.mark.parametrize("raw,expected", [
    ("live", "正常"), ("Disabled", "封禁"), ("Verify", "验证"),
    ("Unregistered", "未注册"), ("error", "检测失败"),
    ("not_live", "检测失败"), ("phone_error", "检测失败"),
])
def test_exact_status_mapping(raw, expected):
    assert normalize_status(raw) == expected


def test_gmail_checker_sends_only_deduplicated_addresses(monkeypatch):
    import httpx

    def post(url, **kwargs):
        assert kwargs["json"] == {"emails": ["demo@gmail.com"]}
        return httpx.Response(200, json={"status": True, "data": [
            {"email": "DEMO@gmail.com", "status": "Verify"},
        ]}, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.gmail_checker_service.httpx.post", post)
    assert check_gmail_accounts(["DEMO@gmail.com", "demo@gmail.com"])[0]["status"] == "Verify"


def test_gmail_checker_rejects_credentials_and_large_batches(monkeypatch):
    with pytest.raises(ValueError):
        check_gmail_accounts(["demo@gmail.com:password"])
    with pytest.raises(ValueError):
        check_gmail_accounts([f"user{index}@gmail.com" for index in range(51)])


def test_gmail_checker_rejects_incomplete_response(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status": True, "data": []}
    monkeypatch.setattr("app.services.gmail_checker_service.httpx.post", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError):
        check_gmail_accounts(["demo@gmail.com"])
