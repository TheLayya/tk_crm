import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Callable

from sqlalchemy.orm import Session

from app.models.monitor import MonitorAccount, MonitorHistory, MonitorSettings
from app.schemas.account import AccountCreate, AccountUpdate
from app.schemas.settings import SettingsUpdate
from app.services.scraper_service import scraper_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

def get_accounts(
    db: Session,
    project_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    allowed_project_ids: Optional[List[int]] = None,
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
    return query.offset(skip).limit(limit).all()


def count_accounts(
    db: Session,
    project_id: Optional[int] = None,
    keyword: Optional[str] = None,
    is_active: Optional[bool] = None,
    allowed_project_ids: Optional[List[int]] = None,
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
    return query.count()


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

    def _trigger_first_check():
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
    
    result = await scraper_service.fetch_user_info(account.username, proxy=proxy)

    now = datetime.utcnow()

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
        
        # 如果启用了视频监控且有 sec_uid，抓取视频列表
        if account.enable_video_monitoring and account.sec_uid:
            try:
                from app.models.video import Video
                
                # 获取设置中的默认视频数量
                settings = get_settings(db)
                max_video_count = settings.default_video_count
                
                video_result = await scraper_service.fetch_user_videos(
                    account.sec_uid, 
                    proxy=proxy,
                    max_count=max_video_count
                )
                if video_result["success"] and video_result.get("data"):
                    videos_data = video_result["data"]
                    logger.info(f"Account {account.username}: fetched {len(videos_data)} videos")

                    # 保存或更新视频记录
                    for video_info in videos_data:
                        try:
                            existing_video = db.query(Video).filter(
                                Video.account_id == account.id,
                                Video.video_id == video_info["video_id"]
                            ).first()

                            if existing_video:
                                existing_video.title = video_info.get("title", existing_video.title)
                                existing_video.cover_url = video_info.get("cover_url", existing_video.cover_url)
                                existing_video.play_count = video_info.get("play_count", existing_video.play_count)
                                existing_video.like_count = video_info.get("like_count", existing_video.like_count)
                                existing_video.comment_count = video_info.get("comment_count", existing_video.comment_count)
                                existing_video.share_count = video_info.get("share_count", existing_video.share_count)
                            else:
                                new_video = Video(
                                    account_id=account.id,
                                    video_id=video_info["video_id"],
                                    title=video_info.get("title", ""),
                                    cover_url=video_info.get("cover_url", ""),
                                    play_count=video_info.get("play_count", 0),
                                    like_count=video_info.get("like_count", 0),
                                    comment_count=video_info.get("comment_count", 0),
                                    share_count=video_info.get("share_count", 0),
                                    published_at=datetime.utcfromtimestamp(video_info["published_at"]) if video_info.get("published_at") else None
                                )
                                db.add(new_video)
                                db.flush()  # 立即写入，提前暴露冲突
                        except Exception as ve:
                            logger.warning(f"Account {account.username}: skip video {video_info.get('video_id')} - {ve}")
                            db.rollback()
                            # rollback 后重新查一次，改为 update
                            try:
                                existing_video = db.query(Video).filter(
                                    Video.account_id == account.id,
                                    Video.video_id == video_info["video_id"]
                                ).first()
                                if existing_video:
                                    existing_video.play_count = video_info.get("play_count", existing_video.play_count)
                                    existing_video.like_count = video_info.get("like_count", existing_video.like_count)
                                    existing_video.comment_count = video_info.get("comment_count", existing_video.comment_count)
                                    existing_video.share_count = video_info.get("share_count", existing_video.share_count)
                            except Exception:
                                pass
                else:
                    logger.warning(f"Account {account.username}: failed to fetch videos - {video_result.get('error')}")
            except Exception as e:
                logger.error(f"Account {account.username}: error processing videos - {e}")
    else:
        account.last_checked_at = now
        error_msg = result.get("error", "Unknown error")[:500] if result else "No result"
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

async def run_scheduled_checks(db_factory: Callable) -> None:
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

        async def _bounded_check(acc: MonitorAccount):
            async with semaphore:
                try:
                    await check_account(db, acc)
                except Exception as e:
                    logger.error(f"Error checking account {acc.username}: {e}")

        tasks = [_bounded_check(acc) for acc in due_accounts]
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

def register_scheduler_jobs(scheduler, db_factory: Callable) -> None:
    """注册 APScheduler 定时任务：每分钟执行一次 run_scheduled_checks。"""

    async def _job():
        await run_scheduled_checks(db_factory)

    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=1,
        id="scheduled_monitor_checks",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Registered scheduled monitor check job (every 1 minute)")
