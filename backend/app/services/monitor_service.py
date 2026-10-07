import asyncio
import logging
import threading
from typing import Any, cast
from datetime import datetime, timedelta
from typing import Optional, List, Callable

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.services.table_query_service import apply_table_query, model_table_fields

from app.models.monitor import MonitorAccount, MonitorHistory, MonitorSettings
from app.schemas.account import AccountCreate, AccountUpdate
from app.schemas.settings import SettingsUpdate
from app.services.scraper_service import is_retryable_result, scraper_service

logger = logging.getLogger(__name__)

MONITOR_TABLE_FIELDS = model_table_fields(MonitorAccount, exclude=("avatar_url", "sec_uid", "tiktok_id"))
_checking_accounts: set[int] = set()
_check_guard = threading.Lock()


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

def get_accounts(
    db: Session,
    project_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: Optional[int] = 50,
    allowed_project_ids: Optional[List[int]] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    table_filters: object = None,
) -> List[MonitorAccount]:
    query = db.query(MonitorAccount)
    if allowed_project_ids is not None:
        query = query.filter(MonitorAccount.project_id.in_(allowed_project_ids))
    if project_id is not None:
        query = query.filter(MonitorAccount.project_id == project_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            MonitorAccount.username.ilike(like)
            | MonitorAccount.nickname.ilike(like)
        )
    if is_active is not None:
        query = query.filter(MonitorAccount.is_active == is_active)
    return cast(List[MonitorAccount], apply_table_query(query, MONITOR_TABLE_FIELDS, sort_by, sort_order, table_filters,
                             stable_column=MonitorAccount.id,
                             default_sort=(MonitorAccount.id, "asc")).offset(skip).limit(limit).all())


def count_accounts(
    db: Session,
    project_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    allowed_project_ids: Optional[List[int]] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    table_filters: object = None,
) -> int:
    query = db.query(MonitorAccount)
    if allowed_project_ids is not None:
        query = query.filter(MonitorAccount.project_id.in_(allowed_project_ids))
    if project_id is not None:
        query = query.filter(MonitorAccount.project_id == project_id)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            MonitorAccount.username.ilike(like)
            | MonitorAccount.nickname.ilike(like)
        )
    if is_active is not None:
        query = query.filter(MonitorAccount.is_active == is_active)
    return int(apply_table_query(query, MONITOR_TABLE_FIELDS, sort_by, sort_order, table_filters,
                             stable_column=MonitorAccount.id,
                             default_sort=(MonitorAccount.id, "asc")).count())


def get_account(db: Session, account_id: int) -> Optional[MonitorAccount]:
    return db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()


def create_account(db: Session, data: AccountCreate) -> MonitorAccount:
    """创建账号，同一 project 下 username 不可重复。创建后立即触发首次检查。"""
    existing = (
        db.query(MonitorAccount)
        .filter(
            MonitorAccount.project_id == data.project_id,
            MonitorAccount.username == data.username,
        )
        .first()
    )
    if existing:
        raise ValueError(f"Username '{data.username}' already exists in this project")

    # Get default interval from settings if not specified
    monitor_interval = data.monitor_interval
    if monitor_interval is None:
        settings = get_settings(db)
        monitor_interval = settings.default_interval

    account = MonitorAccount(
        project_id=data.project_id,
        username=data.username,
        nickname=data.nickname,
        tiktok_id=data.tiktok_id,
        sec_uid=data.sec_uid,
        monitor_interval=monitor_interval,
        use_proxy=data.use_proxy,
        proxy_id=data.proxy_id,
        enable_video_monitoring=data.enable_video_monitoring,
        is_active=data.is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    # 触发首次检查（在后台线程中执行，不阻塞响应）
    import threading
    account_id = account.id  # 只传 id，不传 ORM 对象

    def _trigger_first_check() -> None:
        from app.core.database import SessionLocal
        check_db = SessionLocal()
        try:
            import asyncio
            # 从新 Session 重新加载 account，避免 DetachedInstanceError
            fresh_account = check_db.query(MonitorAccount).filter(MonitorAccount.id == account_id).first()
            if not fresh_account:
                return
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(check_account(check_db, fresh_account))
                logger.info(f"First check completed for account id={account_id}")
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to trigger first check for account id={account_id}: {e}")
        finally:
            check_db.close()

    thread = threading.Thread(target=_trigger_first_check, daemon=True)
    thread.start()

    return account


async def check_account(db: Session, account: MonitorAccount) -> MonitorHistory:
    # ponytail: single-process ownership; use a database lease before multiple workers.
    account_id = account.id
    with _check_guard:
        if account_id in _checking_accounts:
            raise HTTPException(409, "该账号已有采集进行中，请等待完成")
        _checking_accounts.add(account_id)
    try:
        return await _check_account(db, account)
    finally:
        with _check_guard:
            _checking_accounts.discard(account_id)


async def _check_account(db: Session, account: MonitorAccount) -> MonitorHistory:
    """调用 scraper_service 抓取用户信息，更新账号字段，写入历史记录。"""
    proxy = None

    if account.use_proxy:
        if account.proxy_id:
            # 用户指定了代理，使用指定的代理
            proxy = account.proxy
        else:
            # 用户开启了代理但没有指定，从代理列表中随机选择一个启用的代理
            from app.models.monitor import MonitorProxy
            import random

            active_proxies = db.query(MonitorProxy).filter(
                MonitorProxy.is_active == True
            ).all()

            if active_proxies:
                # 随机选择一个代理
                proxy = random.choice(active_proxies)
                logger.info(f"Account {account.username}: randomly selected proxy {proxy.id} ({proxy.host}:{proxy.port})")
            else:
                # 代理列表为空，使用本地IP
                logger.info(f"Account {account.username}: no active proxies available, using local IP")
                proxy = None

    settings = get_settings(db)
    timeout = settings.request_timeout
    identity = (account.project_id, account.username)
    tried_proxy_ids = {proxy.id} if proxy else set()
    result = await scraper_service.fetch_user_info(account.username, proxy=proxy, timeout=timeout)
    if is_retryable_result(result) and proxy is not None and account.use_proxy and not account.proxy_id:
        from app.models.monitor import MonitorProxy
        alternatives = db.query(MonitorProxy).filter(MonitorProxy.is_active.is_(True), MonitorProxy.id != proxy.id).all()
        if alternatives:
            proxy = random.choice(alternatives)
            tried_proxy_ids.add(proxy.id)
            result = await scraper_service.fetch_user_info(account.username, proxy=proxy, timeout=timeout)

    now = datetime.utcnow()
    current_identity = db.query(MonitorAccount.project_id, MonitorAccount.username).filter(MonitorAccount.id == account.id).one_or_none()
    if current_identity != identity:
        db.rollback()
        raise HTTPException(409, "采集期间账号已修改，本次结果已丢弃，请重新采集")

    if result["success"] and result.get("data"):
        data = result["data"]
        account.nickname = data.get("nickname") or account.nickname
        account.tiktok_id = data.get("tiktok_id") or account.tiktok_id
        account.sec_uid = data.get("sec_uid") or account.sec_uid
        account.avatar_url = data.get("avatar_url") or account.avatar_url
        account.bio = data.get("bio") or account.bio
        account.follower_count = data.get("follower_count", account.follower_count)
        account.following_count = data.get("following_count", account.following_count)
        account.like_count = data.get("like_count", account.like_count)
        account.video_count = data.get("video_count", account.video_count)
        account.region = data.get("region") or account.region
        account.account_created_at = data.get("account_created_at") or account.account_created_at
        account.last_checked_at = now
        history = MonitorHistory(
            account_id=account.id,
            follower_count=account.follower_count,
            following_count=account.following_count,
            like_count=account.like_count,
            video_count=account.video_count,
            check_status="success",
            error_message=None,
            checked_at=now,
        )
        db.add(history)
        db.commit()  # Video failures must never undo an already collected profile.
        db.refresh(history)

        # 如果启用了视频监控且有 sec_uid，抓取视频列表
        if account.enable_video_monitoring and account.sec_uid:
            try:
                # 获取设置中的默认视频数量
                settings = get_settings(db)
                max_video_count = settings.default_video_count

                video_result = await scraper_service.fetch_user_videos(
                    account.sec_uid,
                    proxy=proxy,
                    max_count=max_video_count,
                    timeout=timeout,
                )
                current_identity = db.query(MonitorAccount.project_id, MonitorAccount.username).filter(MonitorAccount.id == account.id).one_or_none()
                if current_identity != identity:
                    db.rollback()
                    return history
                if is_retryable_result(video_result) and proxy is not None and account.use_proxy and not account.proxy_id and len(tried_proxy_ids) < 2:
                    from app.models.monitor import MonitorProxy
                    alternatives = db.query(MonitorProxy).filter(MonitorProxy.is_active.is_(True), MonitorProxy.id.notin_(tried_proxy_ids)).all()
                    if alternatives:
                        proxy = random.choice(alternatives)
                        tried_proxy_ids.add(proxy.id)
                        video_result = await scraper_service.fetch_user_videos(account.sec_uid, proxy=proxy, max_count=max_video_count, timeout=timeout)
                current_identity = db.query(MonitorAccount.project_id, MonitorAccount.username).filter(MonitorAccount.id == account.id).one_or_none()
                if current_identity != identity:
                    db.rollback()
                    return history
                if video_result["success"] and isinstance(video_result.get("data"), list):
                    videos_data = video_result["data"]
                    if account.video_count and not videos_data:
                        history.error_message = "VIDEO_COLLECTION_FAILED: 账号资料显示有视频，但接口返回空列表，原视频已保留"
                    logger.info(f"Account {account.username}: fetched {len(videos_data)} videos")

                    # Each savepoint owns only its video; history was already committed.
                    save_error = False
                    for video_info in videos_data:
                        try:
                            with db.begin_nested():
                                _save_monitor_video(db, account.id, video_info, now)
                        except Exception as ve:
                            logger.warning("Account id=%s: video write skipped (%s)", account.id, type(ve).__name__)
                            save_error = True
                    if save_error:
                        history.error_message = "VIDEO_COLLECTION_FAILED: 部分视频记录保存失败，资料已保留"
                    elif video_result.get("partial"):
                        history.error_message = "VIDEO_COLLECTION_FAILED: 视频分页未完整返回，资料和已取得的视频已保留"
                    db.commit()
                else:
                    history.error_message = ("VIDEO_COLLECTION_FAILED: " + str(video_result.get("error") or "未获取到视频列表"))[:500]
                    logger.warning("Account id=%s: video request failed (%s)", account.id, video_result.get("error_code", "unknown"))
            except Exception as e:
                db.rollback()
                history.error_message = "VIDEO_COLLECTION_FAILED: 视频处理异常，资料已保留"
                logger.error("Account id=%s: video processing failed (%s)", account.id, type(e).__name__)
        elif account.enable_video_monitoring and not account.sec_uid:
            history.error_message = "VIDEO_COLLECTION_FAILED: 资料未返回 SEC_UID，无法采集视频，资料已保留"
        db.commit()
        return history
    else:
        account.last_checked_at = now
        error_msg = str(result.get("error") or "Unknown error")[:500] if result else "No result"
        history = MonitorHistory(
            account_id=account.id,
            follower_count=account.follower_count,
            following_count=account.following_count,
            like_count=account.like_count,
            video_count=account.video_count,
            check_status="failed",
            error_message=error_msg,
            checked_at=now,
        )

    db.add(history)
    db.commit()
    db.refresh(history)
    return history


def _save_monitor_video(db: Session, account_id: int, video_info: dict[str, Any], now: datetime) -> None:
    from app.models.video import Video
    video_id = video_info.get("video_id")
    if not video_id:
        raise ValueError("Video ID is missing")
    existing_video = db.query(Video).filter(Video.account_id == account_id, Video.video_id == video_id).first()
    published_at = datetime.utcfromtimestamp(video_info["published_at"]) if video_info.get("published_at") else None
    if existing_video:
        for field in ("title", "cover_url", "play_count", "like_count", "comment_count", "share_count"):
            if field in video_info:
                setattr(existing_video, field, video_info[field])
        existing_video.updated_at = now
        if published_at:
            existing_video.published_at = published_at
    else:
        db.add(Video(account_id=account_id, video_id=video_id, title=video_info.get("title", ""),
                     cover_url=video_info.get("cover_url", ""), play_count=video_info.get("play_count", 0),
                     like_count=video_info.get("like_count", 0), comment_count=video_info.get("comment_count", 0),
                     share_count=video_info.get("share_count", 0), published_at=published_at))
    db.flush()



def update_account(
    db: Session, account_id: int, data: AccountUpdate
) -> Optional[MonitorAccount]:
    account = get_account(db, account_id)
    if not account:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account
def delete_account(db: Session, account_id: int) -> bool:
    account = get_account(db, account_id)
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


async def trigger_check(db: Session, account_id: int) -> Optional[MonitorHistory]:
    """手动触发单账号检查。"""
    account = get_account(db, account_id)
    if not account:
        return None
    return await check_account(db, account)


# ---------------------------------------------------------------------------
# Scheduled batch checks
# ---------------------------------------------------------------------------

async def run_scheduled_checks(db_factory: Callable[[], Session]) -> None:
    """由调度器调用：批量检查所有 active 且到期的账号，受 max_concurrent_checks 限制。"""
    db: Session = db_factory()
    try:
        settings = get_settings(db)
        max_concurrent = settings.max_concurrent_checks

        now = datetime.utcnow()
        accounts = (
            db.query(MonitorAccount)
            .filter(MonitorAccount.is_active == True)
            .all()
        )

        # 筛选到期需要检查的账号
        due_accounts = []
        for acc in accounts:
            if acc.last_checked_at is None:
                due_accounts.append(acc)
            else:
                next_check = acc.last_checked_at + timedelta(seconds=acc.monitor_interval)
                if now >= next_check:
                    due_accounts.append(acc)

        if not due_accounts:
            return

        logger.info(f"Scheduled check: {len(due_accounts)} accounts due")

        # 分批并发执行，受 max_concurrent_checks 限制
        semaphore = asyncio.Semaphore(max_concurrent)

        due_ids = [account.id for account in due_accounts]

        async def _bounded_check(account_id: int) -> None:
            async with semaphore:
                worker_db = db_factory()
                try:
                    account = worker_db.get(MonitorAccount, account_id)
                    if account and account.is_active:
                        await check_account(worker_db, account)
                except HTTPException as e:
                    if e.status_code != 409:
                        logger.error("Scheduled account id=%s failed (HTTP %s)", account_id, e.status_code)
                except Exception as e:
                    worker_db.rollback()
                    logger.error("Scheduled account id=%s failed (%s)", account_id, type(e).__name__)
                finally:
                    worker_db.close()

        tasks = [_bounded_check(account_id) for account_id in due_ids]
        await asyncio.gather(*tasks)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings(db: Session) -> MonitorSettings:
    """获取全局设置，不存在则创建默认值。"""
    settings = db.query(MonitorSettings).first()
    if not settings:
        settings = MonitorSettings(
            default_interval=3600,
            max_concurrent_checks=5,
            request_timeout=30,
            default_video_count=20,
            site_name="TikTok Monitor",
            logo_image=None,
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_settings(db: Session, data: SettingsUpdate) -> MonitorSettings:
    settings = get_settings(db)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def register_scheduler_jobs(scheduler: Any, db_factory: Callable[[], Session]) -> None:
    """注册 APScheduler 定时任务：每分钟执行一次 run_scheduled_checks。"""

    async def _job() -> None:
        await run_scheduled_checks(db_factory)

    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=1,
        id="scheduled_monitor_checks",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Registered scheduled monitor check job (every minute)")
