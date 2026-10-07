import asyncio
import logging
import random
from concurrent.futures import Future
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Awaitable, Callable, Optional, cast

from sqlalchemy.orm import Session

from app.models.monitor import MonitorProxy, MonitorSettings
from app.models.op_account import OpAccount
from app.models.video import OpAccountVideo
from app.services.scraper_service import is_retryable_result, scraper_service
from app.services.video_service import save_video_items

logger = logging.getLogger(__name__)
RETRY_DELAYS = (300, 900, 1800)
# ponytail: in-process guard covers the current single-worker deployment; use a DB lease before adding workers.
_collection_guard = Lock()
_collection_results: dict[int, Future[bool]] = {}


def select_proxy(db: Session, excluded_ids: set[int] | None = None) -> Optional[MonitorProxy]:
    """随机选取一个 is_active=True 且 proxy_type='socks5' 的代理，无则返回 None。"""
    proxies = (
        db.query(MonitorProxy)
        .filter(MonitorProxy.is_active == True, MonitorProxy.proxy_type == "socks5")
        .all()
    )
    proxies = [proxy for proxy in proxies if proxy.id not in (excluded_ids or set())]
    if not proxies:
        return None
    return random.choice(proxies)


async def _fetch_with_failover(
    db: Session, fetch: Callable[..., Awaitable[dict[str, Any]]], value: str,
    proxy: MonitorProxy | None, used_proxy_ids: set[int], **kwargs: Any,
) -> tuple[dict[str, Any], MonitorProxy | None]:
    """At most two distinct configured proxies per account, never a direct fallback."""
    while True:
        if proxy is not None:
            used_proxy_ids.add(proxy.id)
        result = await fetch(value, proxy=proxy, **kwargs)
        if not is_retryable_result(result) or proxy is None or len(used_proxy_ids) >= 2:
            return result, proxy
        alternate = select_proxy(db, used_proxy_ids)
        if alternate is None:
            return result, proxy
        logger.info("Op collection switching proxy %s -> %s", proxy.id, alternate.id)
        proxy = alternate


def schedule_collection_result(account: OpAccount, interval: int, now: datetime, success: bool) -> None:
    """Three short retries per cycle; exhausted/permanent failures use the normal interval."""
    if success:
        account.collect_retry_count = 0
    retryable = is_retryable_result({"success": False, "error": account.collect_error})
    retry_count = max(0, int(account.collect_retry_count or 0))
    delay = min(RETRY_DELAYS[retry_count], interval) if not success and retryable and retry_count < len(RETRY_DELAYS) else interval
    account.next_attempt_at = now + timedelta(seconds=delay)


async def collect_account(
    db: Session, account: OpAccount, proxy: MonitorProxy | None = None, *, scheduled: bool = False,
) -> bool:
    """Share an in-flight result across manual, import and scheduler tasks for this account."""
    account_id = account.id
    with _collection_guard:
        existing = _collection_results.get(account_id)
        if existing is None:
            existing = Future()
            _collection_results[account_id] = existing
            owner = True
        else:
            owner = False
    if not owner:
        result = await asyncio.shield(asyncio.wrap_future(existing))
        db.expire_all()
        return result

    result = False
    identity = None
    interval = 14400
    try:
        # A waiting caller must not reset retries or mutate the owner's status.
        db.refresh(account)
        identity = (account.platform, account.account)
        settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
        interval = settings.default_interval if settings else 14400
        now = datetime.utcnow()
        short_retry = (
            scheduled and account.collect_status == "failed"
            and account.last_attempt_at is not None
            and is_retryable_result({"success": False, "error": account.collect_error})
            and max(0, int(account.collect_retry_count or 0)) < len(RETRY_DELAYS)
        )
        account.collect_retry_count = max(0, int(account.collect_retry_count or 0)) + 1 if short_retry else 0
        account.last_attempt_at = now
        account.next_attempt_at = None
        db.commit()
        result = await _collect_account_once(db, account, proxy, settings)
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(OpAccount.id == account_id).one_or_none()
        if current_identity == identity:
            schedule_collection_result(account, interval, datetime.utcnow(), result)
            db.commit()
        return result
    except BaseException:
        result = False
        db.rollback()
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(OpAccount.id == account_id).one_or_none()
        if identity is not None and current_identity == identity:
            account.collect_status = "failed"
            account.collect_error = "COLLECTION_INTERRUPTED: 采集任务被中断，将自动重试"
            schedule_collection_result(account, interval, datetime.utcnow(), False)
            db.commit()
        raise
    finally:
        # Settle waiters even when the owner is cancelled or its database write raises.
        with _collection_guard:
            if not existing.done():
                existing.set_result(result)
            _collection_results.pop(account_id, None)


def _collect_unsupported(db: Session, account: OpAccount) -> None:
    account.collect_status = "unsupported"
    db.commit()


async def _collect_account_once(
    db: Session, account: OpAccount, proxy: MonitorProxy | None, settings: MonitorSettings | None,
) -> bool:
    """
    按 platform 路由采集。
    - tiktok: 采集基础数据与视频；视频失败时保留成功的基础数据与历史视频。
    - 其他: 调用 _collect_unsupported。
    返回 True/False。
    """
    platform = (account.platform or "").lower()

    if platform != "tiktok":
        _collect_unsupported(db, account)
        return False

    # A collection is complete only after both profile and video requests finish.
    identity_snapshot = (account.platform, account.account)
    cached_sec_uid = account.platform_sec_uid
    account.collect_status = "pending"
    account.collect_error = None
    db.commit()

    profile_error = None
    data = None
    used_proxy_ids: set[int] = set()
    timeout = settings.request_timeout if settings else 30
    try:
        profile_result, proxy = await _fetch_with_failover(
            db, scraper_service.fetch_user_info, account.account.strip().lstrip("@"),
            proxy, used_proxy_ids, timeout=timeout,
        )
        if not profile_result.get("success") or not profile_result.get("data"):
            raise RuntimeError(profile_result.get("error") or "fetch_user_info returned no data")
        data = cast(dict[str, Any], profile_result["data"])
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(
            OpAccount.id == account.id
        ).one_or_none()
        if current_identity != identity_snapshot:
            db.rollback()
            logger.info("Collection abandoned after identity change for account %s", account.id)
            return False
        now = datetime.utcnow()
        account.platform_user_id = data.get("tiktok_id") or account.platform_user_id
        account.platform_sec_uid = data.get("sec_uid") or account.platform_sec_uid
        account.nickname = data.get("nickname") or account.nickname
        account.avatar_url = data.get("avatar_url") or account.avatar_url
        if data.get("follower_count") is not None:
            account.previous_follower_count = (
                account.follower_count if account.last_collected_at is not None else None
            )
            account.follower_count = data["follower_count"]
        account.following_count = data.get("following_count", account.following_count)
        account.like_count = data.get("like_count", account.like_count)
        account.video_count = data.get("video_count", account.video_count)
        account.account_created_at = data.get("account_created_at") or account.account_created_at
        account.last_collected_at = now
        # Profile data remain valid even when the subsequent video request fails.
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"collect_account failed for account {account.id}: {e}")
        profile_error = (str(e).strip() or type(e).__name__)[:500]

    try:
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(
            OpAccount.id == account.id
        ).one_or_none()
        if current_identity != identity_snapshot:
            db.rollback()
            logger.info("Collection abandoned after identity change for account %s", account.id)
            return False
        sec_uid = (data or {}).get("sec_uid") or cached_sec_uid
        if not sec_uid:
            raise RuntimeError("账号缺少 SEC_UID，无法采集视频")
        result, proxy = await _fetch_with_failover(
            db, scraper_service.fetch_user_videos, sec_uid, proxy, used_proxy_ids,
            max_count=settings.default_video_count if settings else 20, timeout=timeout,
        )
        if not result.get("success") or result.get("partial") or not isinstance(result.get("data"), list):
            raise RuntimeError(result.get("error") or "未获取到视频列表")
        video_items = result["data"]
        expected_video_count = (data or {}).get("video_count")
        if expected_video_count is None:
            expected_video_count = account.video_count
        if expected_video_count and not video_items:
            raise RuntimeError("账号资料显示有视频，但视频接口返回空列表，请重试或核实账号可见性")
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(
            OpAccount.id == account.id
        ).one_or_none()
        if current_identity != identity_snapshot:
            db.rollback()
            logger.info("Collection abandoned after identity change for account %s", account.id)
            return False
        save_video_items(db, account.id, video_items, model=OpAccountVideo)
        account.video_collected_at = datetime.utcnow()
        account.collect_status = "failed" if profile_error else "success"
        account.collect_error = profile_error
        db.commit()
        return not profile_error
    except Exception as e:
        db.rollback()
        current_identity = db.query(OpAccount.platform, OpAccount.account).filter(
            OpAccount.id == account.id
        ).one_or_none()
        if current_identity != identity_snapshot:
            logger.info("Collection error ignored after identity change for account %s", account.id)
            return False
        logger.error("Video collection failed for op account %s: %s", account.id, e)
        account.collect_status = "failed"
        reason = f"VIDEO_COLLECTION_FAILED: {(str(e).strip() or type(e).__name__)}"
        account.collect_error = f"{profile_error}; {reason}"[:500] if profile_error else reason[:500]
        account.updated_at = datetime.utcnow()
        db.commit()
        return False
