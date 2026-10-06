import logging
import random
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.monitor import MonitorProxy, MonitorSettings
from app.models.op_account import OpAccount
from app.models.video import OpAccountVideo
from app.services.scraper_service import scraper_service
from app.services.video_service import save_video_items

logger = logging.getLogger(__name__)


def select_proxy(db: Session) -> Optional[MonitorProxy]:
    """随机选取一个 is_active=True 且 proxy_type='socks5' 的代理，无则返回 None。"""
    proxies = (
        db.query(MonitorProxy)
        .filter(MonitorProxy.is_active == True, MonitorProxy.proxy_type == "socks5")
        .all()
    )
    if not proxies:
        return None
    return random.choice(proxies)


async def _collect_tiktok(db: Session, account: OpAccount, proxy) -> dict:
    """调用 scraper_service 采集 TikTok 用户信息，成功返回 dict，失败抛出异常。"""
    result = await scraper_service.fetch_user_info(account.account.strip().lstrip("@"), proxy=proxy)
    if not result.get("success") or not result.get("data"):
        raise RuntimeError(result.get("error") or "fetch_user_info returned no data")
    return result["data"]


def _collect_unsupported(db: Session, account: OpAccount) -> None:
    account.collect_status = "unsupported"
    db.commit()


async def collect_account(db: Session, account: OpAccount, proxy) -> bool:
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
    try:
        data = await _collect_tiktok(db, account, proxy)
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
        settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
        result = await scraper_service.fetch_user_videos(
            sec_uid, proxy=proxy,
            max_count=settings.default_video_count if settings else 20,
        )
        if not result.get("success") or not isinstance(result.get("data"), list):
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
