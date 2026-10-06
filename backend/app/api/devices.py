"""终端资产（设备）管理 API 路由层

路由前缀：/api/devices
授权矩阵（与实施计划一致）：
- 读操作（list/detail/logs/bindable-nodes）：require_permission("device:view"|"device:manage")
- 写操作（create/update/delete）：require_permission("device:manage")
- 非超管：仅自己所属设备（list 强制过滤；get/update/delete/logs 校验归属 403）
- 已删除设备：list/detail/update/delete 一律 404；仅超管可通过 logs 追溯
"""
import logging
import json
from typing import List, Optional, cast
from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device
from app.models.proxy_node import ProxyNode
from app.models.op_account import OpAccount
from app.models.team import User
from app.models.device import DeviceLog
from app.schemas.device import (
    DeviceCreate,
    DeviceDetail,
    DeviceLogOut,
    DeviceOut,
    DeviceUpdate,
    NodeSummary,
    DeviceAccountSummary,
)
from app.services import device_service
from app.services.account_summary_service import enrich_monitor_summaries
from app.services.auth_service import require_permission, get_user_data_scope, get_dept_member_usernames
from app.services.asset_scope_service import get_visible_node_ids, scoped_op_accounts

class DeviceRelationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: Optional[int] = None
    account_ids: Optional[list[int]] = None
    node_ids: list[int] = Field(default_factory=list)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["终端资产"])


# ---------------------------------------------------------------------------
# 响应组装
# ---------------------------------------------------------------------------

def _build_owner_map(db: Session, devices: List[Device]) -> dict:
    owner_ids = {d.owner_id for d in devices}
    if not owner_ids:
        return {}
    users = db.query(User).filter(User.id.in_(owner_ids)).all()
    return {u.id: u for u in users}


def _build_node_map(db: Session, devices: List[Device]) -> dict:
    node_ids = {nid for d in devices for nid in (d.node_ids or ([d.node_id] if d.node_id else []))}
    if not node_ids:
        return {}
    nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(node_ids)).all()
    return {n.id: n for n in nodes}


def _owner_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    # 遗留 Column 风格模型的属性运行时为 str
    return cast(Optional[str], user.real_name or user.username)


def _node_ip(node: Optional[ProxyNode]) -> Optional[str]:
    if node is None:
        return None
    return f"{node.ip}:{node.port}"


def _device_to_out(
    db: Session, device: Device, owner_map: dict, node_map: dict, current_user: User
) -> DeviceOut:
    owner = owner_map.get(device.owner_id)
    linked_node_ids = device.node_ids or ([device.node_id] if device.node_id else [])
    node = node_map.get(linked_node_ids[0]) if linked_node_ids else None
    accounts = db.query(OpAccount).filter(OpAccount.device_id == device.id).order_by(OpAccount.id).all()
    enrich_monitor_summaries(db, accounts, current_user)
    return DeviceOut(
        id=device.id,
        name=device.name,
        device_type=device.device_type,
        owner_id=device.owner_id,
        owner_name=_owner_name(owner),
        node_id=device.node_id,
        node_ids=device.node_ids or ([device.node_id] if device.node_id else []),
        node_ip=_node_ip(node),
        node_count=len(linked_node_ids),
        account_id=accounts[0].id if accounts else None,
        account_name=accounts[0].account if accounts else None,
        accounts=[DeviceAccountSummary(
            id=a.id,
            platform=a.platform,
            account=a.account,
            nickname=a.nickname,
            avatar_url=a.avatar_url,
            follower_count=a.follower_count,
            following_count=a.following_count,
            like_count=a.like_count,
            video_count=a.video_count,
            followers_change=a.followers_change,
            yesterday_video_count=a.yesterday_video_count,
            yesterday_video_plays=a.yesterday_video_plays,
        ) for a in accounts],
        remark=device.remark,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _node_summary(node: Optional[ProxyNode]) -> Optional[NodeSummary]:
    """节点摘要白名单字段（不含凭据）；NodeSummary extra=forbid 保证凭据字段不可能被序列化。"""
    if node is None:
        return None
    # 遗留 Column 风格模型的属性运行时为原生类型
    return NodeSummary(
        id=cast(int, node.id),
        ip=cast(str, node.ip),
        port=cast(int, node.port),
        protocol=cast(str, node.protocol),
        status=cast(str, node.status),
    )


# ---------------------------------------------------------------------------
# GET ""  — 设备列表（分页 + 筛选 + 数据范围）
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
def list_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None, pattern=r"^(pc|phone)$"),
    owner_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:view")),
):
    """设备列表。非超管强制仅返回自己所属设备（owner_id 参数忽略）。"""
    try:
        data_scope = get_user_data_scope(db, current_user)
        owner_ids = None
        if data_scope == "all":
            owner_ids = {user_id for (user_id,) in db.query(User.id).all()}
        elif data_scope == "dept":
            owner_ids = {
                user_id for (user_id,) in db.query(User.id).filter(
                    User.username.in_(get_dept_member_usernames(db, current_user))
                ).all()
            }
        elif data_scope == "self":
            owner_ids = {current_user.id}
        devices, total = device_service.list_devices(
            db,
            skip=skip,
            limit=limit,
            keyword=keyword,
            device_type=device_type,
            owner_id=owner_id if data_scope == "all" else None,
            # 遗留 Column 风格模型的属性运行时为 int/bool
            current_user_id=cast(int, current_user.id),
            is_super_admin=cast(bool, current_user.is_super_admin),
            owner_ids=owner_ids,
        )
        owner_map = _build_owner_map(db, devices)
        node_map = _build_node_map(db, devices)
        items = [_device_to_out(db, d, owner_map, node_map, current_user) for d in devices]
        return {"items": items, "total": total}
    except device_service.DeviceServiceError as e:
        # 服务层业务校验（如缺少用户上下文）保留原状态码，不吞成 500
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"list_devices failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET /bindable-nodes  — 可绑定节点下拉（必须在 /{device_id} 之前注册）
# ---------------------------------------------------------------------------

@router.get("/bindable-nodes", response_model=dict)
def bindable_nodes(
    q: Optional[str] = Query(None),
    exclude_device_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:manage")),
):
    """可绑定节点（idle/active 节点允许多台设备共享）。

    exclude_device_id 归属校验：非超管仅可放行自己所属的设备（防借他人设备 ID 探测其绑定节点）。
    """
    try:
        if exclude_device_id is not None and not current_user.is_super_admin:
            excluded = db.query(Device).filter(Device.id == exclude_device_id).first()
            if excluded is None or excluded.is_deleted:
                # 已删除/不存在按既有口径返回 404
                raise HTTPException(status_code=404, detail="设备不存在")
            scope = get_user_data_scope(db, current_user)
            allowed_owner_ids = None
            if scope == "self":
                allowed_owner_ids = {current_user.id}
            elif scope == "dept":
                allowed_owner_ids = {
                    user_id for (user_id,) in db.query(User.id).filter(
                        User.username.in_(get_dept_member_usernames(db, current_user))
                    ).all()
                }
            if allowed_owner_ids is not None and excluded.owner_id not in allowed_owner_ids:
                raise HTTPException(status_code=403, detail="无权操作此设备")
        items = device_service.get_bindable_nodes(
            db, q=q, exclude_device_id=exclude_device_id,
            allowed_node_ids=get_visible_node_ids(db, current_user),
        )
        return {"items": items, "total": len(items)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"bindable_nodes failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# POST ""  — 创建设备
# ---------------------------------------------------------------------------

@router.post("", response_model=DeviceOut, status_code=201)
def create_device(
    body: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:manage")),
):
    """创建设备。非超管 owner 强制为当前用户。"""
    try:
        device = device_service.create_device(db, body.model_dump(), current_user)
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"create_device failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    owner_map = _build_owner_map(db, [device])
    node_map = _build_node_map(db, [device])
    return _device_to_out(db, device, owner_map, node_map, current_user)


# ---------------------------------------------------------------------------
# GET /{device_id}  — 设备详情
# ---------------------------------------------------------------------------

@router.get("/{device_id}", response_model=DeviceDetail)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:view")),
):
    """设备详情。非超管仅可查看自己所属；已删除返回 404（服务层执行对象级授权）。"""
    try:
        device = device_service.get_device(db, device_id, current_user)
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"get_device failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    owner_map = _build_owner_map(db, [device])
    node_map = _build_node_map(db, [device])
    out = _device_to_out(db, device, owner_map, node_map, current_user)
    return DeviceDetail(
        **out.model_dump(),
        node=_node_summary(node_map.get(device.node_id) if device.node_id else None),
        nodes=[_node_summary(node_map[nid]) for nid in (device.node_ids or ([device.node_id] if device.node_id else [])) if nid in node_map],
    )


# ---------------------------------------------------------------------------
# PATCH /{device_id}  — 更新设备（PATCH 语义）
# ---------------------------------------------------------------------------

@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    body: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:manage")),
):
    """更新设备。非超管仅可更新自己所属；owner 仅超管可改；已删除返回 404（服务层执行授权）。"""
    try:
        device = device_service.get_device(db, device_id, current_user)
        if device is None:
            raise HTTPException(status_code=404, detail="设备不存在")
        device, _ = device_service.update_device(
            db, device, body.get_update_data(), current_user
        )
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update_device failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    owner_map = _build_owner_map(db, [device])
    node_map = _build_node_map(db, [device])
    return _device_to_out(db, device, owner_map, node_map, current_user)

@router.put("/{device_id}/relations", response_model=DeviceOut)
def update_device_relations(device_id: int, body: DeviceRelationsBody, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device:manage"))):
    try:
        device = device_service.get_device(db, device_id, current_user)
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    node_ids = body.node_ids
    nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(node_ids)).all() if node_ids else []
    if len(nodes) != len(set(node_ids)):
        raise HTTPException(status_code=404, detail="部分代理节点不存在")
    invalid = [n for n in nodes if n.status not in ("idle", "active")]
    if invalid:
        raise HTTPException(status_code=409, detail=f"节点 {invalid[0].ip}:{invalid[0].port} 当前状态不可绑定")
    visible_node_ids = get_visible_node_ids(db, current_user)
    if visible_node_ids is not None:
        if set(node_ids) - visible_node_ids:
            raise HTTPException(status_code=403, detail="无权关联部分代理节点")

    # 新客户端传 account_ids；旧客户端传 account_id，统一转换为列表。
    account_ids = list(dict.fromkeys(body.account_ids if body.account_ids is not None else ([body.account_id] if body.account_id else [])))
    from app.services.op_account_service import _write_audit_log, record_relation_snapshot
    selected_accounts = []
    visible_account_ids = {
        account_id for (account_id,) in scoped_op_accounts(db, current_user).with_entities(OpAccount.id).all()
    }
    if account_ids:
        if device.device_type != "phone":
            raise HTTPException(status_code=409, detail="运营账号只能绑定手机终端")
        selected_accounts = db.query(OpAccount).filter(OpAccount.id.in_(account_ids)).all()
        if len(selected_accounts) != len(account_ids):
            raise HTTPException(status_code=404, detail="部分账号不存在")
        for account in selected_accounts:
            if account.id not in visible_account_ids:
                raise HTTPException(status_code=403, detail="无权关联该运营账号")
            if account.device_id and account.device_id != device.id:
                old_device = db.query(Device).filter(Device.id == account.device_id, Device.is_deleted == False).first()
                raise HTTPException(status_code=409, detail=f"账号 {account.account} 已绑定终端 {old_device.name if old_device else account.device_id}")
    selected_ids = {a.id for a in selected_accounts}
    existing_accounts = db.query(OpAccount).filter(OpAccount.device_id == device.id).all()
    if any(item.id not in visible_account_ids and item.id not in selected_ids for item in existing_accounts):
        raise HTTPException(status_code=403, detail="无权解除其他成员的运营账号关联")
    for item in existing_accounts:
        if item.id not in selected_ids:
            _write_audit_log(db, item.id, "update", "node_id", str(item.node_id) if item.node_id else None, None, current_user.username)
            item.device_id = None
            item.node_id = None
            record_relation_snapshot(db, item, current_user.username)
            _write_audit_log(db, item.id, "update", "device_id", str(device.id), None, current_user.username)
    for account in selected_accounts:
        if account.device_id != device.id:
            _write_audit_log(db, account.id, "update", "device_id", account.device_id, str(device.id), current_user.username)
        account.device_id = device.id
    old_nodes = device.node_ids or ([device.node_id] if device.node_id else [])
    old_account = db.query(OpAccount).filter(OpAccount.device_id == device.id).first()
    device.node_ids = node_ids
    device.node_id = node_ids[0] if node_ids else None
    for account in selected_accounts:
        if account.node_id != device.node_id:
            _write_audit_log(db, account.id, "update", "node_id", str(account.node_id) if account.node_id else None, str(device.node_id) if device.node_id else None, current_user.username)
        account.node_id = device.node_id
        record_relation_snapshot(db, account, current_user.username)
    db.add(DeviceLog(device_id=device.id, user_id=current_user.id, username=current_user.username,
                     action="UPDATE", changes=json.dumps({"relations": {"old": {"account_id": old_account.id if old_account else None, "node_ids": old_nodes}, "new": {"account_ids": sorted(selected_ids), "node_ids": node_ids}}}, ensure_ascii=False)))
    db.commit(); db.refresh(device)
    return _device_to_out(db, device, _build_owner_map(db, [device]), _build_node_map(db, [device]), current_user)


# ---------------------------------------------------------------------------
# DELETE /{device_id}  — 删除设备（软删除）
# ---------------------------------------------------------------------------

@router.delete("/{device_id}", response_model=dict)
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:manage")),
):
    """软删除设备（历史轨迹保留）。非超管仅可删除自己所属；已删除返回 404（服务层执行授权）。"""
    try:
        device = device_service.get_device(db, device_id, current_user)
        if device is None:
            raise HTTPException(status_code=404, detail="设备不存在")
        device_service.soft_delete_device(db, device, current_user)
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_device failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    return {"deleted": True}


# ---------------------------------------------------------------------------
# GET /{device_id}/logs  — 设备历史轨迹
# ---------------------------------------------------------------------------

@router.get("/{resource_id}/association-history", response_model=dict)
def get_association_history(resource_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("device:view"))):
    from app.services.relation_history_service import relation_overview
    return relation_overview(db, "device", resource_id, current_user)


@router.get("/{device_id}/logs", response_model=dict)
def get_device_logs(
    device_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("device:view")),
):
    """设备历史轨迹（含已删除设备，仅超管可查已删除；服务层执行授权与计数）。"""
    try:
        logs, total = device_service.get_device_logs(
            db, device_id, current_user, skip=skip, limit=limit
        )
        items = [
            DeviceLogOut(
                id=log.id,
                user_id=log.user_id,
                username=log.username,
                action=log.action,
                changes=device_service.parse_log_changes(log.changes),
                **device_service.readable_device_log(db, log),
                created_at=log.created_at,
            )
            for log in logs
        ]
        return {"items": items, "total": total}
    except device_service.DeviceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"get_device_logs failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
