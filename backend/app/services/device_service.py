"""终端资产（设备）业务逻辑层

- 数据范围与对象级授权：服务层为权威执行点（非超管仅可见/可操作自己所属的设备）。
- 业务校验异常统一抛 DeviceServiceError(status_code, detail)。
- 所有变更写入 device_logs（old→new），值级截断保证 JSON 永远合法。
"""
import json
import logging
import threading
from collections.abc import Mapping
from typing import List, Optional, Tuple, TypedDict, cast

from sqlalchemy import Integer, String, case, cast as sql_cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.device import Device, DeviceLog
from app.models.op_account import OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import User
from app.services.auth_service import get_user_data_scope, get_dept_member_usernames
from app.services.asset_scope_service import get_visible_node_ids
from app.services.table_query_service import apply_table_query, apply_table_rows, field_kind, model_table_fields, parse_table_filters

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


class ReadableDeviceLog(TypedDict):
    summary: str
    details: list[str]


DeviceChanges = dict[str, dict[str, object]]


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
    changes: DeviceChanges,
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


def _require_bindable_node(db: Session, node_id: int, user: User) -> ProxyNode:
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if node is None:
        raise DeviceServiceError(404, "绑定节点不存在")
    if node.status not in BINDABLE_NODE_STATUSES:
        raise DeviceServiceError(400, "该节点状态不可绑定（仅空闲/使用中节点可绑定）")
    visible_ids = get_visible_node_ids(db, user)
    if visible_ids is not None and node_id not in visible_ids:
        raise DeviceServiceError(403, "无权关联该代理节点")
    return node





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
    sort_by: str | None = None,
    sort_order: str = "asc",
    table_filters: str | None = None,
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

    first_node_id = func.coalesce(func.json_extract(Device.node_ids, "$[0]"), Device.node_id)
    fields = model_table_fields(Device, exclude=("is_deleted", "node_ids"))
    fields.update({
        "owner_name": select(func.coalesce(func.nullif(User.real_name, ""), User.username)).where(
            User.id == Device.owner_id).scalar_subquery(),
        "node_ip": select(ProxyNode.ip + ":" + sql_cast(ProxyNode.port, String)).where(
            ProxyNode.id == first_node_id).scalar_subquery(),
        "node_count": sql_cast(case(
            (func.json_array_length(Device.node_ids) > 0, func.json_array_length(Device.node_ids)),
            (Device.node_id.isnot(None), 1), else_=0), Integer),
        "account_name": select(OpAccount.account).where(OpAccount.device_id == Device.id).order_by(
            OpAccount.id).limit(1).scalar_subquery(),
        "accounts": select(sql_cast(func.group_concat(
            OpAccount.account + " " + func.coalesce(OpAccount.nickname, ""), " "), String)).where(
            OpAccount.device_id == Device.id).scalar_subquery(),
    })
    query = apply_table_query(query, fields, sort_by, sort_order, table_filters,
                              stable_column=Device.id, default_sort=(Device.created_at, "desc"))
    total = query.count()
    devices = (
        query
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


def create_device(db: Session, data: Mapping[str, object], user: User) -> Device:
    with _device_mutation_lock:
        return _create_device_locked(db, data, user)

def _create_device_locked(db: Session, data: Mapping[str, object], user: User) -> Device:
    """创建设备。非超管 owner 强制为当前用户。"""
    # owner 解析
    owner_id = cast(int | None, data.get("owner_id"))
    if user.is_super_admin:
        if owner_id is None:
            raise DeviceServiceError(400, "所属人必填")
    else:
        if owner_id is not None and owner_id != user.id:
            raise DeviceServiceError(400, "无权为他人创建设备")
        owner_id = user.id

    _require_active_owner(db, owner_id)

    # 节点校验
    if data.get("node_ids"):
        raise DeviceServiceError(400, "请使用关联管理接口修改代理节点关系")
    node_id = cast(int | None, data.get("node_id"))
    if node_id is not None:
        _require_bindable_node(db, node_id, user)


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

        logger.exception("create_device: unexpected integrity error")
        raise

    _write_device_log(
        db,
        device.id,
        user.id,
        user.username,
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


def update_device(db: Session, device: Device, data: Mapping[str, object], user: User) -> Tuple[Device, DeviceChanges]:
    """更新设备（PATCH 语义，data 仅含显式字段）。返回 (device, changes)。"""
    if device.is_deleted:
        raise DeviceServiceError(404, "设备不存在")
    _ensure_owner(db, device, user)

    changes: DeviceChanges = {}

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
        _require_active_owner(db, cast(int, data["owner_id"]))

    # 节点换绑/解绑校验
    target_node_id: Optional[int] = None
    if "node_id" in data:
        new_node_id = cast(int | None, data["node_id"])
        if new_node_id is not None and new_node_id != device.node_id:
            _require_bindable_node(db, new_node_id, user)

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
        normalized = [cast(int, data["node_id"])] if data["node_id"] is not None else []
        if device.node_ids != normalized:
            changes["node_ids"] = {"old": _truncate_value(device.node_ids), "new": normalized}
            device.node_ids = normalized

    if changes:
        try:
            if "node_id" in data:
                from app.services.op_account_service import sync_device_account_nodes
                sync_device_account_nodes(db, device, user.username)
            if target_node_id is not None:
                _recheck_node_bindable(db, target_node_id)
            db.flush()
        except IntegrityError as e:
            db.rollback()

            logger.exception("update_device %s: unexpected integrity error", device.id)
            raise
        _write_device_log(
            db, device.id, user.id, user.username, "UPDATE", changes
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
        user.id,
        user.username,
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
    sync_device_account_nodes(db, device, user.username)
    db.commit()


def get_device_logs(
    db: Session, device_id: int, user: User, skip: int = 0, limit: int = 100,
    sort_by: str | None = None, sort_order: str = "asc", table_filters: str | None = None,
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
    fields = model_table_fields(DeviceLog)
    row_fields = {name: field_kind(column) for name, column in fields.items()}
    row_fields.update({"summary": "text", "details": "text"})
    filters = parse_table_filters(table_filters, row_fields)
    if sort_by in {"summary", "details"} or {"summary", "details"}.intersection(filters):
        # ponytail: readable history resolves references in Python; use SQL projections if histories become large.
        logs = query.order_by(DeviceLog.created_at.desc(), DeviceLog.id.desc()).all()
        rows = [{**{name: getattr(log, name) for name in fields}, **readable_device_log(db, log)} for log in logs]
        rows = apply_table_rows(rows, row_fields, sort_by, sort_order, filters)
        log_map = {log.id: log for log in logs}
        return [log_map[row["id"]] for row in rows[skip:skip + limit]], len(rows)
    query = apply_table_query(query, fields, sort_by, sort_order, filters,
                              stable_column=DeviceLog.id, default_sort=(DeviceLog.created_at, "desc"))
    total = query.count()
    logs = query.offset(skip).limit(limit).all()
    return logs, total


def parse_log_changes(raw: Optional[str]) -> Optional[dict[str, object]]:
    """安全解析日志 JSON；损坏数据返回 None 而非抛异常。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return cast(dict[str, object], parsed) if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def readable_device_log(db: Session, log: DeviceLog) -> ReadableDeviceLog:
    changes = parse_log_changes(log.changes) or {}
    details: list[str] = []

    def reference(model: type[ProxyNode] | type[OpAccount] | type[User], value: object) -> str:
        if value is None:
            return "未关联"
        if isinstance(value, str) and value.isdecimal():
            value = int(value)
        if not isinstance(value, int):
            return "历史对象无法识别"
        item = db.get(model, value)
        if item is None:
            return "历史对象已不存在"
        if isinstance(item, ProxyNode):
            return f"{item.ip}:{item.port}"
        if isinstance(item, OpAccount):
            return item.account
        owner = cast(User, item)
        return owner.real_name or owner.username

    def relation_values(state: Mapping[str, object], plural: str, singular: str) -> list[object]:
        value = state.get(plural, state.get(singular))
        return cast(list[object], value) if isinstance(value, list) else ([] if value is None else [value])

    def relation_details(label: str, model: type[ProxyNode] | type[OpAccount] | type[User], old: list[object], new: list[object]) -> None:
        removed = [value for value in old if value not in new]
        added = [value for value in new if value not in old]
        if added:
            details.append(f"关联{label}：" + "、".join(reference(model, value) for value in added))
        if removed:
            details.append(f"解除{label}：" + "、".join(reference(model, value) for value in removed))

    name = cast(Mapping[str, object], changes.get("name") or {}).get("new")
    kind = cast(Mapping[str, object], changes.get("device_type") or {}).get("new")
    summary = {"CREATE": f"新增{'手机' if kind == 'phone' else '电脑' if kind == 'pc' else '终端'}{(' ' + str(name)) if name else ''}",
               "UPDATE": "更新终端", "DELETE": "删除终端"}.get(log.action, "终端操作")
    for field, change in changes.items():
        if not isinstance(change, dict):
            continue
        typed_change = cast(dict[str, object], change)
        old, new = typed_change.get("old"), typed_change.get("new")
        if field == "relations":
            if isinstance(old, dict) or isinstance(new, dict):
                old_state = cast(dict[str, object], old) if isinstance(old, dict) else {}
                new_state = cast(dict[str, object], new) if isinstance(new, dict) else {}
                for label, model, plural, singular in (("节点", ProxyNode, "node_ids", "node_id"),
                                                       ("账号", OpAccount, "account_ids", "account_id")):
                    relation_details(label, model, relation_values(old_state, plural, singular),
                                     relation_values(new_state, plural, singular))
            elif "old_node_ids" in change or "new_node_ids" in change:
                relation_details("节点", ProxyNode, cast(list[object], typed_change.get("old_node_ids") or []), cast(list[object], typed_change.get("new_node_ids") or []))
            summary = "调整终端关联"
            continue
        if old == new or (not old and not new):
            continue
        if field == "node_id" and "node_ids" in changes:
            continue
        if field in ("node_id", "node_ids"):
            relation_details("节点", ProxyNode, cast(list[object], old) if isinstance(old, list) else ([] if old is None else [old]),
                             cast(list[object], new) if isinstance(new, list) else ([] if new is None else [new]))
        elif field == "owner_id":
            details.append("所属人：" + (reference(User, old) + " → " if old is not None else "") + reference(User, new))
        elif field == "remark":
            details.append("清空备注" if not new else "设置备注：" + str(new))
        elif field in ("name", "device_type") and log.action != "CREATE":
            label = "名称" if field == "name" else "类型"
            labels: dict[object, object] = {"phone": "手机", "pc": "电脑"}
            details.append(f"{label}：{labels.get(old, old) or '未设置'} → {labels.get(new, new) or '未设置'}")
    return {"summary": summary, "details": details}


def get_bindable_nodes(
    db: Session,
    q: Optional[str] = None,
    exclude_device_id: Optional[int] = None,
    limit: int = 100,
    allowed_node_ids: Optional[set[int]] = None,
) -> List[dict[str, object]]:
    """返回可共享绑定的空闲或使用中节点。"""
    query = db.query(ProxyNode).filter(ProxyNode.status.in_(BINDABLE_NODE_STATUSES))
    if allowed_node_ids is not None:
        query = query.filter(ProxyNode.id.in_(allowed_node_ids))

    if q:
        query = query.filter(or_(ProxyNode.ip.contains(q)))



    nodes = query.order_by(ProxyNode.id.desc()).limit(limit).all()
    return [
        {"id": n.id, "ip": n.ip, "port": n.port, "protocol": n.protocol}
        for n in nodes
    ]
