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

    try:
        data = await _collect_tiktok(db, account, proxy)
        now = datetime.utcnow()
        account.platform_user_id = data.get("tiktok_id") or account.platform_user_id
        account.platform_sec_uid = data.get("sec_uid") or account.platform_sec_uid
        account.nickname = data.get("nickname") or account.nickname
        account.avatar_url = data.get("avatar_url") or account.avatar_url
        account.follower_count = data.get("follower_count", account.follower_count)
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
        account.collect_status = "failed"
        account.collect_error = str(e)[:500]
        account.updated_at = datetime.utcnow()
        db.commit()
        return False

    try:
        if data.get("video_count") == 0:
            video_items = []
        else:
            if not account.platform_sec_uid:
                raise RuntimeError("账号缺少 SEC_UID，无法采集视频")
            settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
            result = await scraper_service.fetch_user_videos(
                account.platform_sec_uid, proxy=proxy,
                max_count=settings.default_video_count if settings else 20,
            )
            if not result.get("success") or not isinstance(result.get("data"), list):
                raise RuntimeError(result.get("error") or "未获取到视频列表")
            video_items = result["data"]
        save_video_items(db, account.id, video_items, model=OpAccountVideo)
        account.video_collected_at = datetime.utcnow()
        account.collect_status = "success"
        account.collect_error = None
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error("Video collection failed for op account %s: %s", account.id, e)
        account.collect_status = "failed"
        account.collect_error = f"VIDEO_COLLECTION_FAILED: {e}"[:500]
        account.updated_at = datetime.utcnow()
        db.commit()
        return False
