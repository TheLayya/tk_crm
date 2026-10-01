"""Gmail status probe backed by the optional gmail0918.top API."""
from datetime import datetime
import re
from typing import Iterable

import httpx

CHECK_URL = "https://gmail0918.top/api.php"
MAX_BATCH_SIZE = 50
STATUS_MAP = {
    "live": "正常",
    "success": "正常",
    "ok": "正常",
    "disabled": "封禁",
    "disable": "封禁",
    "verify": "验证",
    "checkpoint": "验证",
    "not_exist": "未注册",
    "unregistered": "未注册",
}


def normalize_status(raw_status: str | None) -> str:
    raw = (raw_status or "").strip().lower()
    return STATUS_MAP.get(raw, "检测失败")


def check_gmail_accounts(emails: Iterable[str], timeout: float = 30.0) -> list[dict]:
    values = list(dict.fromkeys(str(email).strip().lower() for email in emails if str(email).strip()))
    if not values:
        return []
    if len(values) > MAX_BATCH_SIZE:
        raise ValueError(f"单次最多检测 {MAX_BATCH_SIZE} 个 Gmail 地址")
    if any(not re.fullmatch(r"[A-Za-z0-9._%+\-]+@gmail\.com", email, re.IGNORECASE) for email in values):
        raise ValueError("只接受完整 Gmail 地址，不接受密码或整行账号凭据")
    response = httpx.post(CHECK_URL, json={"emails": values}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") is not True or not isinstance(payload.get("data"), list):
        raise RuntimeError("检测服务返回无效结果")
    rows = payload["data"]
    expected = {email.lower() for email in values}
    received = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("email"), str) or not isinstance(row.get("status"), str):
            raise RuntimeError("检测服务返回格式异常")
        email = row["email"].strip().lower()
        if email not in expected or email in received:
            raise RuntimeError("检测服务返回邮箱不匹配或重复")
        received.add(email)
    if received != expected:
        raise RuntimeError("检测服务未返回全部邮箱结果")
    return rows


def apply_check_results(accounts, results: list[dict], now: datetime | None = None) -> int:
    by_email = {str(result.get("email") or "").strip().lower(): result for result in results}
    checked_at = now or datetime.utcnow()
    updated = 0
    for account in accounts:
        result = by_email.get(account.account.strip().lower())
        if result is None:
            continue
        raw_status = str(result.get("status") or result.get("message") or "")
        account.gmail_check_status = normalize_status(raw_status)
        account.gmail_check_raw_status = raw_status[:100] or None
        account.gmail_checked_at = checked_at
        updated += 1
    return updated
