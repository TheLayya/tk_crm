import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, cast

from sqlalchemy import case, func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.monitor import MonitorAccount
from app.models.video import OpAccountVideo, Video, VideoStats
from app.services.scraper_service import scraper_service
from app.services.table_query_service import apply_table_query, model_table_fields

logger = logging.getLogger(__name__)


def table_videos_query(db: Session, account_id: int, model: type[Video] | type[OpAccountVideo] = Video,
                       sort_by: str | None = None, sort_order: str = "asc", table_filters: object = None) -> Any:
    fields = model_table_fields(model, exclude=("cover_url",))
    return apply_table_query(db.query(model).filter(model.account_id == account_id), fields,
                             sort_by, sort_order, table_filters, stable_column=model.id,
                             default_sort=(model.published_at, "desc"))


def get_videos(db: Session, account_id: int, skip: int = 0, limit: int = 100, model: type[Video] | type[OpAccountVideo] = Video,
               sort_by: str | None = None, sort_order: str = "asc", table_filters: object = None) -> list[Video] | list[OpAccountVideo]:
    """获取指定账号的视频列表"""
    return cast(list[Video] | list[OpAccountVideo], (
        table_videos_query(db, account_id, model, sort_by, sort_order, table_filters)
        .offset(skip)
        .limit(limit)
        .all()
    ))


def get_yesterday_video_counts(db: Session, account_ids: List[int], now: Optional[datetime] = None, model: type[Video] | type[OpAccountVideo] = Video, collected_at: Optional[dict[int, datetime]] = None) -> dict[int, int | None]:
    if not account_ids:
        return {}
    start, end = _yesterday_beijing_bounds(now)
    rows = (
        db.query(
            model.account_id,
            func.count(model.published_at),
            func.sum(case(((model.published_at >= start) & (model.published_at < end), 1), else_=0)),
            func.max(model.updated_at),
        )
        .filter(model.account_id.in_(account_ids))
        .group_by(model.account_id)
        .all()
    )
    counts: dict[int, int | None] = {}
    for account_id, dated_count, yesterday_count, updated_at in rows:
        refreshed = (collected_at or {}).get(account_id) or updated_at
        counts[account_id] = int(yesterday_count) if dated_count and (yesterday_count or refreshed >= end) else None
    return counts


def get_yesterday_video_plays(db: Session, account_ids: List[int], now: Optional[datetime] = None, model: type[Video] | type[OpAccountVideo] = Video) -> dict[int, list[int]]:
    if not account_ids:
        return {}
    start, end = _yesterday_beijing_bounds(now)
    rows = (
        db.query(model.account_id, model.play_count)
        .filter(model.account_id.in_(account_ids), model.published_at >= start, model.published_at < end)
        .order_by(model.account_id, model.published_at.desc(), model.id.desc())
        .all()
    )
    plays: dict[int, list[int]] = {}
    for account_id, play_count in rows:
        plays.setdefault(account_id, []).append(int(play_count))
    return plays


def _yesterday_beijing_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    beijing = timezone(timedelta(hours=8))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    today = current.astimezone(beijing).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today.astimezone(timezone.utc).replace(tzinfo=None)
    return end - timedelta(days=1), end


def get_video_stats(db: Session, video_id: int) -> List[VideoStats]:
    """获取指定视频的历史统计快照列表（按时间升序）"""
    return (
        db.query(VideoStats)
        .filter(VideoStats.video_id == video_id)
        .order_by(VideoStats.recorded_at.asc())
        .all()
    )


async def fetch_and_save_videos(db: Session, account: MonitorAccount) -> int:
    from app.services.monitor_service import _check_guard, _checking_accounts
    account_id = account.id
    with _check_guard:
        if account_id in _checking_accounts:
            raise HTTPException(409, "该账号已有采集进行中，请等待完成")
        _checking_accounts.add(account_id)
    try:
        return await _fetch_and_save_videos(db, account)
    finally:
        with _check_guard:
            _checking_accounts.discard(account_id)


async def _fetch_and_save_videos(db: Session, account: MonitorAccount) -> int:
    """
    抓取账号的视频列表并持久化。
    - 对每个视频执行 upsert（根据 video_id 去重）
    - 为每个视频新增一条 VideoStats 统计快照
    返回本次新增的视频数量。
    """
    if not account.sec_uid:
        logger.warning(
            f"Account id={account.id} username={account.username} has no sec_uid, skipping video fetch"
        )
        raise HTTPException(422, "账号缺少 SEC_UID，请先采集账号资料")

    # 获取该账号绑定的代理（如启用）
    proxy = account.proxy if account.use_proxy else None
    from app.services.monitor_service import get_settings
    settings = get_settings(db)
    identity = (account.project_id, account.username)
    result = await scraper_service.fetch_user_videos(account.sec_uid, proxy=proxy,
                                                     max_count=settings.default_video_count,
                                                     timeout=settings.request_timeout)
    current_identity = db.query(MonitorAccount.project_id, MonitorAccount.username).filter(MonitorAccount.id == account.id).one_or_none()
    if current_identity != identity:
        db.rollback()
        raise HTTPException(409, "采集期间账号已修改，本次视频结果已丢弃")

    if not result['success'] or result.get('partial'):
        logger.error(
            f"Failed to fetch videos for account id={account.id}: {result.get('error')}"
        )
        raise HTTPException(502, str(result.get('error') or '视频采集未完成，原视频数据已保留'))

    video_items = result.get('data') or []
    new_count = save_video_items(db, account.id, video_items)
    db.commit()
    logger.info(
        f"fetch_and_save_videos: account id={account.id}, "
        f"fetched={len(video_items)}, new={new_count}"
    )
    return new_count


def save_video_items(db: Session, account_id: int, video_items: list[dict[str, Any]], model: type[Video] | type[OpAccountVideo] = Video) -> int:
    """Persist a fetched list; the caller commits the collection transaction."""
    new_count = 0
    now = datetime.utcnow()

    for item in video_items:
        video_id_str = item.get('video_id')
        if not video_id_str:
            continue

        # upsert: 查找已有记录
        query = db.query(model).filter(model.video_id == str(video_id_str), model.account_id == account_id)
        if model is Video and query.first() is None and db.query(Video.id).filter(Video.video_id == str(video_id_str)).first():
            raise ValueError("视频已属于另一个监控账号，未覆盖其记录")
        video = cast(Video | OpAccountVideo | None, query.first())

        # 解析 published_at
        published_at: Optional[datetime] = None
        raw_ts = item.get('published_at')
        if raw_ts:
            try:
                published_at = datetime.utcfromtimestamp(int(raw_ts))
            except (ValueError, TypeError, OSError):
                published_at = None

        if video is None:
            # 新视频
            video = model(
                account_id=account_id,
                video_id=str(video_id_str),
                title=item.get('title', ''),
                cover_url=item.get('cover_url', ''),
                play_count=item.get('play_count', 0),
                like_count=item.get('like_count', 0),
                comment_count=item.get('comment_count', 0),
                share_count=item.get('share_count', 0),
                published_at=published_at,
            )
            db.add(video)
            db.flush()  # 获取 video.id
            new_count += 1
            logger.debug(f"New video video_id={video_id_str} for account id={account_id}")
        else:
            # 更新已有视频的统计字段
            video.play_count = item.get('play_count', video.play_count)
            video.like_count = item.get('like_count', video.like_count)
            video.comment_count = item.get('comment_count', video.comment_count)
            video.share_count = item.get('share_count', video.share_count)
            video.title = item.get('title') or video.title
            video.cover_url = item.get('cover_url') or video.cover_url
            video.published_at = published_at or video.published_at
            video.updated_at = now

        # 新增 VideoStats 快照（每次采集都记录一条）
        if model is Video:
            stats_snapshot = VideoStats(
                video_id=video.id,
                play_count=item.get('play_count', 0),
                like_count=item.get('like_count', 0),
                comment_count=item.get('comment_count', 0),
                share_count=item.get('share_count', 0),
                recorded_at=now,
            )
            db.add(stats_snapshot)
    return new_count
