from sqlalchemy import func

from app.models.monitor import MonitorAccount, MonitorHistory
from app.models.video import OpAccountVideo
from app.services import video_service
from app.services.project_service import get_visible_project_ids
from app.services.auth_service import _get_user_permissions, get_user_data_scope, get_dept_member_usernames


def enrich_monitor_summaries(db, items, current_user):
    data_scope = get_user_data_scope(db, current_user)
    scope_usernames = get_dept_member_usernames(db, current_user) if data_scope == "dept" else None
    monitor_by_name = {}
    if current_user.is_super_admin or "monitor:view" in _get_user_permissions(db, current_user.id):
        names = [item.account.lstrip("@").lower() for item in items if item.platform == "tiktok"]
        query = db.query(MonitorAccount).filter(func.lower(MonitorAccount.username).in_(names))
        allowed_ids = get_visible_project_ids(db, current_user.username, data_scope, scope_usernames)
        if allowed_ids is not None:
            query = query.filter(MonitorAccount.project_id.in_(allowed_ids))
        for monitor in query.order_by(MonitorAccount.id).all():
            monitor_by_name.setdefault(monitor.username.lower(), monitor)
    monitor_ids = [monitor.id for monitor in monitor_by_name.values()]
    yesterday_counts = video_service.get_yesterday_video_counts(db, monitor_ids)
    yesterday_plays = video_service.get_yesterday_video_plays(db, monitor_ids)
    own_collected_at = {
        item.id: item.video_collected_at
        for item in items
        if item.platform == "tiktok" and item.video_collected_at is not None
    }
    op_ids = list(own_collected_at)
    op_counts = video_service.get_yesterday_video_counts(
        db, op_ids, model=OpAccountVideo,
        collected_at=own_collected_at,
    )
    op_plays = video_service.get_yesterday_video_plays(db, op_ids, model=OpAccountVideo)
    _, today_start = video_service._yesterday_beijing_bounds()
    for item in items:
        monitor = monitor_by_name.get(item.account.lstrip("@").lower()) if item.platform == "tiktok" else None
        item.monitor_account_id = monitor.id if monitor else None
        item.followers_change = (
            item.follower_count - item.previous_follower_count
            if item.follower_count is not None and item.previous_follower_count is not None
            else None
        )
        item.yesterday_video_count = yesterday_counts.get(monitor.id) if monitor else None
        item.yesterday_video_plays = yesterday_plays.get(monitor.id, []) if monitor and item.yesterday_video_count is not None else None
        own_videos = item.id in own_collected_at
        item.video_source = "op" if own_videos or not monitor else "monitor"
        if own_videos:
            item.yesterday_video_count = op_counts.get(item.id)
            if item.id not in op_counts and item.video_collected_at >= today_start:
                item.yesterday_video_count = 0
            item.yesterday_video_plays = op_plays.get(item.id, []) if item.yesterday_video_count is not None else None
        if monitor and item.followers_change is None:
            history = db.query(MonitorHistory).filter(
                MonitorHistory.account_id == monitor.id, MonitorHistory.check_status == "success"
            ).order_by(MonitorHistory.checked_at.desc(), MonitorHistory.id.desc()).limit(2).all()
            if len(history) == 2:
                item.followers_change = history[0].follower_count - history[1].follower_count
