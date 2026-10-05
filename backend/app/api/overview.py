from collections import defaultdict
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device
from app.models.op_account import EmailAccount, OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import User
from app.services.account_summary_service import enrich_monitor_summaries
from app.services.auth_service import (
    get_dept_member_usernames,
    get_user_data_scope,
    require_permission,
    _get_user_permissions,
)

router = APIRouter(prefix="/overview", tags=["数据总览"])


def _name(user: Optional[User]) -> str:
    return (user.real_name or user.username) if user else "未分配"


def _scope_usernames(db: Session, user: User) -> Optional[set[str]]:
    scope = get_user_data_scope(db, user)
    if scope == "all":
        return None
    return set(get_dept_member_usernames(db, user)) if scope == "dept" else {user.username}


def _visible_account(account: OpAccount, usernames: Optional[set[str]]) -> bool:
    return usernames is None or account.registrant in usernames or account.operator in usernames


def _visible_email(email: EmailAccount, usernames: Optional[set[str]]) -> bool:
    return usernames is None or email.registrant in usernames or email.operator in usernames


@router.get("")
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:view")),
    _accounts=Depends(require_permission("op_account:view")),
    _nodes=Depends(require_permission("proxy_node:view")),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    def in_period(value):
        return date_from is None and date_to is None or value is not None and (date_from is None or value >= date_from) and (date_to is None or value <= date_to)

    usernames = _scope_usernames(db, current_user)
    users = {u.id: u for u in db.query(User).all()}
    devices = [d for d in db.query(Device).filter(Device.is_deleted == False).all()
               if usernames is None or (d.owner_id in users and users[d.owner_id].username in usernames)]
    accounts = [a for a in db.query(OpAccount).all() if _visible_account(a, usernames) and a.platform != "gmail"]
    enrich_monitor_summaries(db, accounts, current_user)
    permissions = set(_get_user_permissions(db, current_user.id))
    emails_visible = current_user.is_super_admin or bool(permissions & {"email:view", "op_account:view"})
    emails = [e for e in db.query(EmailAccount).all() if _visible_email(e, usernames)] if emails_visible else []
    nodes = db.query(ProxyNode).all()
    if usernames is not None:
        visible_node_ids = {a.node_id for a in accounts if a.node_id}
        visible_node_ids.update(e.node_id for e in emails if e.node_id)
        visible_node_ids.update(nid for d in devices for nid in (d.node_ids or ([d.node_id] if d.node_id else [])))
        nodes = [n for n in nodes if n.created_by in usernames or n.id in visible_node_ids]

    node_map = {n.id: n for n in nodes}
    accounts_by_device = defaultdict(list)
    for account in accounts:
        if account.device_id:
            accounts_by_device[account.device_id].append(account)

    device_rows = []
    for device in devices:
        ids = device.node_ids or ([device.node_id] if device.node_id else [])
        device_rows.append({
            "id": device.id,
            "name": device.name,
            "device_type": device.device_type,
            "owner": _name(users.get(device.owner_id)),
            "owner_id": device.owner_id,
            "nodes": [{"id": n.id, "name": f"{n.ip}:{n.port}", "status": n.status} for n in (node_map[i] for i in ids if i in node_map)],
            "accounts": [{
                "id": a.id, "platform": a.platform, "account": a.account,
                "status": a.status, "nickname": a.nickname, "operator": a.operator,
                "avatar_url": a.avatar_url, "follower_count": a.follower_count,
                "following_count": a.following_count, "like_count": a.like_count,
                "video_count": a.video_count, "followers_change": getattr(a, "followers_change", None),
                "yesterday_video_count": getattr(a, "yesterday_video_count", None),
                "yesterday_video_plays": getattr(a, "yesterday_video_plays", None),
                "last_collected_at": a.last_collected_at,
            } for a in accounts_by_device[device.id]],
        })

    def grouped(items, key, amount):
        result = defaultdict(lambda: {"count": 0, "amount": Decimal("0")})
        for item in items:
            group = getattr(item, key) or "未填写"
            result[group]["count"] += 1
            result[group]["amount"] += Decimal(str(getattr(item, amount) or 0))
        return [{"name": k, **v} for k, v in sorted(result.items(), key=lambda x: (-x[1]["amount"], x[0]))]

    financial_items = [("运营账号", a) for a in accounts] + [("代理节点", n) for n in nodes] + [("邮箱", e) for e in emails]
    cost_items = [(kind, item) for kind, item in financial_items if item.purchase_price is not None and in_period(item.purchase_date)]
    revenue_items = [(kind, item) for kind, item in financial_items if item.sale_price is not None and in_period(getattr(item, "sale_date", None))]
    by_asset = []
    for kind in ("运营账号", "代理节点", "邮箱"):
        purchases = [item for asset_kind, item in cost_items if asset_kind == kind]
        sales = [item for asset_kind, item in revenue_items if asset_kind == kind]
        by_asset.append({
            "name": kind,
            "cost": sum((item.purchase_price for item in purchases), Decimal("0")),
            "revenue": sum((item.sale_price for item in sales), Decimal("0")),
            "cost_count": len(purchases),
            "revenue_count": len(sales),
        })
    deleted_device_ids = {device_id for (device_id,) in db.query(Device.id).filter(Device.is_deleted == True).all()}
    linked_node_ids = {nid for d in devices for nid in (d.node_ids or ([d.node_id] if d.node_id else []))}
    linked_node_ids.update(a.node_id for a in accounts if a.node_id)
    linked_node_ids.update(e.node_id for e in emails if e.node_id)
    quality = {
        "unassigned_devices": sum(1 for d in devices if d.owner_id not in users),
        "unbound_devices": sum(1 for d in devices if not any(nid in node_map for nid in (d.node_ids or ([d.node_id] if d.node_id else [])))),
        "unbound_accounts": sum(1 for a in accounts if not a.device_id or a.device_id in deleted_device_ids),
        "unassigned_accounts": sum(1 for a in accounts if not (a.operator or "").strip()),
        "uncollected_accounts": sum(1 for a in accounts if not a.last_collected_at),
        "expired_nodes": sum(1 for n in nodes if n.expire_date and n.expire_date < date.today()),
        "stale_accounts": sum(1 for a in accounts if a.last_collected_at and a.last_collected_at < datetime.utcnow() - timedelta(days=7)),
        "expiring_nodes": sum(1 for n in nodes if n.expire_date and date.today() <= n.expire_date <= date.today() + timedelta(days=7)),
        "failed_nodes": sum(1 for n in nodes if n.last_test_result == "failed"),
        "missing_purchase_amount": sum(1 for a in accounts if a.purchase_price is None) + sum(1 for n in nodes if n.purchase_price is None) + sum(1 for e in emails if e.purchase_price is None),
    }
    return {
        "generated_at": datetime.utcnow(),
        "assets": {
            "devices": {"total": len(devices), "phone": sum(d.device_type == "phone" for d in devices), "pc": sum(d.device_type == "pc" for d in devices)},
            "nodes": {"total": len(nodes), "by_status": {s: sum(n.status == s for n in nodes) for s in ("idle", "active", "sold", "disabled")}},
            "accounts": {"total": len(accounts), "by_status": {s: sum(a.status == s for a in accounts) for s in ("正常", "自用", "封禁", "已售")}},
            "emails": {"total": len(emails), "by_status": {s: sum(e.management_status == s for e in emails) for s in ("闲置", "使用中", "锁定", "废弃", "已出售")}},
        },
        "device_rows": device_rows,
        "finance": {
            "entered_cost": sum((item.purchase_price for _, item in cost_items), Decimal("0")),
            "entered_revenue": sum((item.sale_price for _, item in revenue_items), Decimal("0")),
            "by_asset": by_asset,
            "cost_by_channel": grouped([item for _, item in cost_items], "purchase_channel", "purchase_price"),
            "revenue_by_customer": grouped([item for _, item in revenue_items], "sale_customer", "sale_price"),
            "date_from": date_from,
            "date_to": date_to,
            "missing_cost_dates": sum(1 for _, item in financial_items if item.purchase_price is not None and item.purchase_date is None),
            "missing_revenue_dates": sum(1 for _, item in financial_items if item.sale_price is not None and getattr(item, "sale_date", None) is None),
        },
        "unbound_accounts": [{
            "id": a.id, "account": a.account, "platform": a.platform, "status": a.status, "operator": a.operator,
            "nickname": a.nickname, "avatar_url": a.avatar_url, "follower_count": a.follower_count,
            "following_count": a.following_count, "like_count": a.like_count, "video_count": a.video_count,
            "followers_change": getattr(a, "followers_change", None),
            "yesterday_video_count": getattr(a, "yesterday_video_count", None),
            "yesterday_video_plays": getattr(a, "yesterday_video_plays", None),
        } for a in accounts if not a.device_id or a.device_id in deleted_device_ids],
        "unbound_nodes": [{"id": n.id, "name": f"{n.ip}:{n.port}", "status": n.status, "expire_date": n.expire_date} for n in nodes if n.id not in linked_node_ids],
        "quality": quality,
    }
