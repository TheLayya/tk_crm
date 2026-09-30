"""终端资产（设备）业务逻辑层

- 数据范围与对象级授权：服务层为权威执行点（非超管仅可见/可操作自己所属的设备）。
- 业务校验异常统一抛 DeviceServiceError(status_code, detail)。
- 所有变更写入 device_logs（old→new），值级截断保证 JSON 永远合法。
"""
import json
import logging
import threading
from typing import List, Optional, Tuple, cast

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.device import Device, DeviceLog
from app.models.proxy_node import ProxyNode
from app.models.team import User
from app.services.auth_service import get_user_data_scope, get_dept_member_usernames

logger = logging.getLogger(__name__)
_device_mutation_lock = threading.RLock()

# 节点可绑定状态（销售业务态中允许被设备引用）
BINDABLE_NODE_STATUSES = ("idle", "active")

# 单个 old/new 值在日志中的最大字符数
CHANGES_VALUE_LIMIT = 500

# 更新接口允许修改的字段白名单（防 setattr 注入改保留字段）
ALLOWED_UPDATE_FIELDS = {"name", "device_type", "owner_id", "node_id", "node_ids", "remark"}

# 显式禁止更新（即使出现在 data 中）
FORBIDDEN_UPDATE_FIELDS = {"id", "is_deleted", "created_at", "updated_at"}


class DeviceServiceError(Exception):
    """业务校验异常，携带 HTTP 状态码。"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _truncate_value(value: object, limit: int = CHANGES_VALUE_LIMIT) -> Optional[str]:
    """转为字符串并按长度截断（加截断标记）；None 保持 JSON null 语义。"""
    if value is None:
        return None
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "…(截断)"
    return text


def _write_device_log(
    db: Session,
    device_id: int,
    user_id: int,
    username: str,
    action: str,
    changes: dict,
) -> None:
    payload = json.dumps(changes, ensure_ascii=False)
    db.add(
        DeviceLog(
            device_id=device_id,
            user_id=user_id,
            username=username,
            action=action,
            changes=payload,
        )
    )


def _require_active_owner(db: Session, owner_id: int) -> User:
    owner = (
        db.query(User)
        .filter(User.id == owner_id, User.is_active == True)
        .first()
    )
    if owner is None:
        raise DeviceServiceError(404, "所属用户不存在")
    return owner


def _require_bindable_node(db: Session, node_id: int) -> ProxyNode:
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if node is None:
        raise DeviceServiceError(404, "绑定节点不存在")
    if node.status not in BINDABLE_NODE_STATUSES:
        raise DeviceServiceError(400, "该节点状态不可绑定（仅空闲/使用中节点可绑定）")
    return node


def _check_node_duplicate(
    db: Session, node_id: int, exclude_device_id: Optional[int] = None
) -> None:
    """节点唯一性预检查：排除当前设备自身（编辑保留原节点时放行）。"""
    query = db.query(Device).filter(
        Device.node_id == node_id,
        Device.is_deleted == False,
    )
    if exclude_device_id is not None:
        query = query.filter(Device.id != exclude_device_id)
    if query.first() is not None:
        raise DeviceServiceError(409, "该节点已绑定其他设备")


def _is_node_unique_error(exc: IntegrityError) -> bool:
    """仅当完整性冲突来自节点唯一约束时才返回 True，避免误分类其他约束错误。

    优先用结构化错误码（sqlite3 SQLITE_CONSTRAINT_UNIQUE），消息子串作跨驱动兜底。
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    error_code = getattr(orig, "sqlite_errorcode", None)
    if error_code is not None:
        return error_code == 2067 and "node_id" in str(orig)  # SQLITE_CONSTRAINT_UNIQUE
    message = str(orig)
    return "node_id" in message or "uq_devices_node_id" in message


def _recheck_node_bindable(db: Session, node_id: int) -> None:
    """提交前复核节点状态，缩小 check-then-use 窗口。

    说明（SQLite 环境）：SQLite 不支持 SELECT ... FOR UPDATE，无法获得行锁；
    本函数将窗口缩到复核与 flush 之间，残余竞态为业务规则级风险（非数据损坏），
    影响仅限设备绑定到刚变更状态的节点。生产库切换为支持行锁的数据库时，
    应将此复核替换为事务内行锁。
    """
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if node is None:
        # 节点在初检后被删除：受控 404 而非悬空外键 500
        raise DeviceServiceError(404, "绑定节点不存在")
    if node.status not in BINDABLE_NODE_STATUSES:
        raise DeviceServiceError(400, "该节点状态不可绑定（仅空闲/使用中节点可绑定）")


def _visible_owner_ids(db: Session, user: User) -> Optional[set[int]]:
    """Return owner IDs visible under the user's role data scope."""
    if user.is_super_admin:
        return None
    scope = get_user_data_scope(db, user)
    if scope == "all":
        return None
    if scope == "dept":
        usernames = get_dept_member_usernames(db, user)
        ids = {
            int(owner_id)
            for owner_id, in db.query(User.id).filter(User.username.in_(usernames)).all()
        }
        return ids or {int(user.id)}
    return {int(user.id)}


def _ensure_owner(db: Session, device: Device, user: User, action: str = "操作") -> None:
    """对象级授权：按角色数据范围检查设备所属人。"""
    visible_owner_ids = _visible_owner_ids(db, user)
    if visible_owner_ids is None or device.owner_id in visible_owner_ids:
        return
    if device.owner_id != user.id:
        raise DeviceServiceError(403, f"无权{action}此设备")


def list_devices(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    keyword: Optional[str] = None,
    device_type: Optional[str] = None,
    owner_id: Optional[int] = None,
    current_user_id: Optional[int] = None,
    is_super_admin: bool = False,
    owner_ids: Optional[set[int]] = None,
) -> Tuple[List[Device], int]:
    """设备列表：非超管强制仅见自己所属；已删除设备不返回。

    授权上下文显式传入：is_super_admin 默认 False（fail-closed），
    调用方（API 层）必须明确声明调用者身份。
    """
    if not is_super_admin and current_user_id is None:
        # 防 fail-open：缺少用户上下文时绝不返回全量数据
        raise DeviceServiceError(400, "内部错误：缺少用户上下文")

    query = db.query(Device).filter(Device.is_deleted == False)

    if keyword:
        query = query.filter(Device.name.contains(keyword))
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if owner_id and (is_super_admin or owner_ids is not None):
        query = query.filter(Device.owner_id == owner_id)
    if owner_ids is not None:
        query = query.filter(Device.owner_id.in_(owner_ids))
    elif not is_super_admin and current_user_id is not None:
        query = query.filter(Device.owner_id == current_user_id)

    total = query.count()
    devices = (
        query.order_by(Device.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return devices, total


def get_device(db: Session, device_id: int, user: User) -> Optional[Device]:
    """获取未删除设备（get/update/delete 共用）；越权抛 403。"""
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.is_deleted == False)
        .first()
    )
    if device is not None:
        _ensure_owner(db, device, user)
    return device


def create_device(db: Session, data: dict, user: User) -> Device:
    with _device_mutation_lock:
        return _create_device_locked(db, data, user)

def _create_device_locked(db: Session, data: dict, user: User) -> Device:
    """创建设备。非超管 owner 强制为当前用户。"""
    # owner 解析
    owner_id = data.get("owner_id")
    if user.is_super_admin:
        if owner_id is None:
            raise DeviceServiceError(400, "所属人必填")
    else:
        if owner_id is not None and owner_id != user.id:
            raise DeviceServiceError(400, "无权为他人创建设备")
        # 遗留 Column 风格模型的属性在 mypy 下为 Column[int]，运行时是 int
        owner_id = cast(int, user.id)

    _require_active_owner(db, owner_id)

    # 节点校验
    node_id = data.get("node_id")
    if node_id is not None:
        _require_bindable_node(db, node_id)
        _check_node_duplicate(db, node_id)

    device = Device(
        name=data["name"],
        device_type=data["device_type"],
        owner_id=owner_id,
        node_id=node_id,
        remark=data.get("remark"),
    )
    db.add(device)
    try:
        if node_id is not None:
            _recheck_node_bindable(db, node_id)
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if _is_node_unique_error(e):
            logger.warning("create_device: node %s unique conflict", node_id)
            raise DeviceServiceError(409, "该节点已绑定其他设备")
        logger.exception("create_device: unexpected integrity error")
        raise

    _write_device_log(
        db,
        device.id,
        cast(int, user.id),
        cast(str, user.username),
        "CREATE",
        {
            "name": {"old": None, "new": _truncate_value(device.name)},
            "device_type": {"old": None, "new": _truncate_value(device.device_type)},
            "owner_id": {"old": None, "new": _truncate_value(device.owner_id)},
            "node_id": {"old": None, "new": _truncate_value(device.node_id)},
            "remark": {"old": None, "new": _truncate_value(device.remark)},
        },
    )
    db.commit()
    db.refresh(device)
    return device


def update_device(db: Session, device: Device, data: dict, user: User) -> Tuple[Device, dict]:
    """更新设备（PATCH 语义，data 仅含显式字段）。返回 (device, changes)。"""
    if device.is_deleted:
        raise DeviceServiceError(404, "设备不存在")
    _ensure_owner(db, device, user)

    changes: dict = {}

    # 字段白名单：拒绝未知字段与保留字段
    for field in data:
        if field in FORBIDDEN_UPDATE_FIELDS:
            raise DeviceServiceError(400, f"不允许更新的字段: {field}")
        if field not in ALLOWED_UPDATE_FIELDS:
            raise DeviceServiceError(400, f"不支持的字段: {field}")
    # 关系集合只能通过专用 relations 端点修改，避免旧 PATCH 只改 JSON 或只改首项。
    if "node_ids" in data:
        raise DeviceServiceError(400, "请使用关联管理接口修改代理节点关系")

    # name / device_type 不允许显式置空
    for field in ("name", "device_type"):
        if field in data and data[field] is None:
            raise DeviceServiceError(400, f"{field} 不能为空")

    # owner 变更仅超管
    if "owner_id" in data:
        if data["owner_id"] is None:
            raise DeviceServiceError(400, "owner_id 不能为空")
        if not user.is_super_admin:
            raise DeviceServiceError(400, "无权修改所属人")
        _require_active_owner(db, data["owner_id"])

    # 节点换绑/解绑校验
    target_node_id: Optional[int] = None
    if "node_id" in data:
        new_node_id = data["node_id"]
        if new_node_id is not None and new_node_id != device.node_id:
            _require_bindable_node(db, new_node_id)
            _check_node_duplicate(db, new_node_id, exclude_device_id=device.id)
            for other in db.query(Device).filter(Device.id != device.id, Device.is_deleted == False).all():
                occupied = set(other.node_ids or ([other.node_id] if other.node_id else []))
                if new_node_id in occupied:
                    raise DeviceServiceError(409, "该节点已绑定其他设备")
            target_node_id = new_node_id

    # 应用变更并记录差异
    for field, value in data.items():
        if field == "owner_id" and not user.is_super_admin:
            continue
        old = getattr(device, field)
        if old != value:
            changes[field] = {"old": _truncate_value(old), "new": _truncate_value(value)}
            setattr(device, field, value)
    if "node_id" in data:
        # 兼容旧 PATCH，同时保持单节点旧列与多节点 JSON 的同源一致。
        normalized = [data["node_id"]] if data["node_id"] is not None else []
        if device.node_ids != normalized:
            changes["node_ids"] = {"old": _truncate_value(device.node_ids), "new": normalized}
            device.node_ids = normalized

    if changes:
        try:
            if "node_id" in data:
                from app.services.op_account_service import sync_device_account_nodes
                sync_device_account_nodes(db, device)
            if target_node_id is not None:
                _recheck_node_bindable(db, target_node_id)
            db.flush()
        except IntegrityError as e:
            db.rollback()
            if _is_node_unique_error(e):
                logger.warning("update_device %s: node unique conflict", device.id)
                raise DeviceServiceError(409, "该节点已绑定其他设备")
            logger.exception("update_device %s: unexpected integrity error", device.id)
            raise
        _write_device_log(
            db, device.id, cast(int, user.id), cast(str, user.username), "UPDATE", changes
        )
        db.commit()
        db.refresh(device)

    return device, changes


def soft_delete_device(db: Session, device: Device, user: User) -> None:
    """软删除：置 is_deleted、清空 node_id（节点可再绑），历史日志保留。"""
    if device.is_deleted:
        raise DeviceServiceError(404, "设备不存在")
    _ensure_owner(db, device, user)

    _write_device_log(
        db,
        device.id,
        cast(int, user.id),
        cast(str, user.username),
        "DELETE",
        {
            "is_deleted": {"old": _truncate_value(device.is_deleted), "new": True},
            "node_id": {"old": _truncate_value(device.node_id), "new": None},
        },
    )
    device.is_deleted = True
    device.node_id = None
    device.node_ids = []
    from app.services.op_account_service import sync_device_account_nodes
    sync_device_account_nodes(db, device)
    db.commit()


def get_device_logs(
    db: Session, device_id: int, user: User, skip: int = 0, limit: int = 100
) -> Tuple[List[DeviceLog], int]:
    """设备历史轨迹：非超管仅自己所属且未删除；超管可查已删除设备（历史可追溯）。

    返回 (logs, total)，total 为独立 count（分页正确性）。
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise DeviceServiceError(404, "设备不存在")
    if device.is_deleted:
        if not user.is_super_admin:
            raise DeviceServiceError(404, "设备不存在")
    else:
        visible_owner_ids = _visible_owner_ids(db, user)
        if visible_owner_ids is not None and device.owner_id not in visible_owner_ids:
            raise DeviceServiceError(404, "设备不存在")

    query = db.query(DeviceLog).filter(DeviceLog.device_id == device_id)
    total = query.count()
    logs = query.order_by(DeviceLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs, total


def parse_log_changes(raw: Optional[str]) -> Optional[dict]:
    """安全解析日志 JSON；损坏数据返回 None 而非抛异常。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def get_bindable_nodes(
    db: Session,
    q: Optional[str] = None,
    exclude_device_id: Optional[int] = None,
    limit: int = 100,
) -> List[dict]:
    """可绑定节点：仅 idle/active，且排除已被其他未删除设备占用的节点。"""
    query = db.query(ProxyNode).filter(ProxyNode.status.in_(BINDABLE_NODE_STATUSES))

    if q:
        query = query.filter(or_(ProxyNode.ip.contains(q)))

    # 排除已占用节点（编辑设备时放行其自身已绑定的节点）
    bound = db.query(Device.node_id).filter(
        Device.node_id.isnot(None),
        Device.is_deleted == False,
    )
    if exclude_device_id is not None:
        bound = bound.filter(Device.id != exclude_device_id)
    query = query.filter(~ProxyNode.id.in_(bound))

    nodes = query.order_by(ProxyNode.id.desc()).limit(limit).all()
    return [
        {"id": n.id, "ip": n.ip, "port": n.port, "protocol": n.protocol}
        for n in nodes
    ]
