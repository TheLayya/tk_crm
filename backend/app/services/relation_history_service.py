import json
from fastapi import HTTPException
from app.models.device import Device, DeviceLog
from app.models.proxy_node import ProxyNode
from app.models.op_account import OpAccount, OpAuditLog
from app.services.auth_service import get_user_data_scope, get_dept_member_usernames


def account_relation_snapshot(db, account):
    device = db.get(Device, account.device_id) if account.device_id else None
    if device and device.is_deleted:
        device = None
    node_ids = (device.node_ids or ([device.node_id] if device.node_id else [])) if device and not device.is_deleted else ([account.node_id] if account.node_id else [])
    nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(node_ids)).all() if node_ids else []
    return {"device": {"id": device.id, "name": device.name} if device else None,
            "nodes": [{"id": node.id, "name": f"{node.ip}:{node.port}"} for node in nodes],
            "source": "沿用终端" if device else "直接关联"}


def visible_accounts(db, user):
    query = db.query(OpAccount)
    scope = get_user_data_scope(db, user)
    if not user.is_super_admin and scope != "all":
        allowed = get_dept_member_usernames(db, user) if scope == "dept" else [user.username]
        query = query.filter((OpAccount.registrant.in_(allowed)) | (OpAccount.operator.in_(allowed)))
    return query.all()


def parse_snapshot(log):
    try:
        value = json.loads(log.new_value or "null")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def relation_overview(db, kind, resource_id, user):
    accounts = visible_accounts(db, user)
    by_id = {account.id: account for account in accounts}
    model = {"account": OpAccount, "device": Device, "node": ProxyNode}[kind]
    resource = db.get(model, resource_id)
    if resource is None:
        raise HTTPException(404, "对象不存在")
    if kind == "account" and resource_id not in by_id:
        raise HTTPException(403, "无权查看账号关联")
    if kind == "device":
        from app.services.device_service import DeviceServiceError, get_device
        try:
            if get_device(db, resource_id, user) is None:
                raise HTTPException(404, "终端不存在")
        except DeviceServiceError as error:
            raise HTTPException(error.status_code, error.detail)
    if kind == "node" and not user.is_super_admin and get_user_data_scope(db, user) != "all":
        if not any(account.node_id == resource_id for account in accounts):
            raise HTTPException(403, "无权查看节点关联")
    if kind == "account":
        accounts = [by_id[resource_id]]
    ids = [account.id for account in accounts]
    logs = db.query(OpAuditLog).filter(OpAuditLog.op_account_id.in_(ids),
        OpAuditLog.field_name.in_(["device_id", "node_id", "relation_snapshot", "ban_snapshot"])
    ).order_by(OpAuditLog.created_at, OpAuditLog.id).all() if ids else []
    entries = {}
    current = []
    bans = []

    def touch(entry_kind, object_id, name=None, when=None, is_current=False, status=None):
        if not object_id:
            return
        key = (entry_kind, object_id)
        if key not in entries:
            related = db.get({"account": OpAccount, "device": Device, "node": ProxyNode}[entry_kind], object_id)
            display = name or (related.account if entry_kind == "account" and related else related.name if entry_kind == "device" and related else f"{related.ip}:{related.port}" if related else "历史对象已不存在")
            entries[key] = {"kind": entry_kind, "id": object_id, "name": display,
                            "first_recorded_at": None, "last_recorded_at": None,
                            "current": False, "status": status}
        entry = entries[key]
        if when:
            entry["first_recorded_at"] = min(entry["first_recorded_at"], when) if entry["first_recorded_at"] else when
            entry["last_recorded_at"] = max(entry["last_recorded_at"], when) if entry["last_recorded_at"] else when
        entry["current"] = entry["current"] or is_current

    for account in accounts:
        snapshot = account_relation_snapshot(db, account)
        related_bans = []
        for log in logs:
            if log.op_account_id != account.id:
                continue
            snapshot_log = parse_snapshot(log) if log.field_name.endswith("snapshot") else {}
            device = snapshot_log.get("device") or {}
            nodes = snapshot_log.get("nodes") or []
            if device.get("id"):
                if kind == "account": touch("device", device["id"], device.get("name"), log.created_at)
            for node in nodes:
                if kind == "account": touch("node", node["id"], node.get("name"), log.created_at)
            if log.field_name in ("device_id", "node_id"):
                for value in (log.old_value, log.new_value):
                    if value and str(value).isdecimal():
                        object_id = int(value)
                        if kind == "account": touch("device" if log.field_name == "device_id" else "node", object_id, when=log.created_at)
            matches = kind == "account" or (kind == "device" and device.get("id") == resource_id) or (kind == "node" and any(node["id"] == resource_id for node in nodes))
            if kind != "account" and log.field_name in ("device_id", "node_id"):
                matches = log.field_name == ("device_id" if kind == "device" else "node_id") and str(resource_id) in (str(log.old_value), str(log.new_value))
            if matches and kind != "account":
                touch("account", account.id, account.account, log.created_at, status=account.status)
                if kind == "node": touch("device", device.get("id"), device.get("name"), log.created_at)
                if kind == "device":
                    for node in nodes: touch("node", node["id"], node.get("name"), log.created_at)
            if log.field_name == "ban_snapshot" and matches:
                related_bans.append({"account": account.account, "recorded_at": log.created_at,
                                     "device": device.get("name") or "未关联终端",
                                     "nodes": [node["name"] for node in nodes]})
        bans.extend(related_bans)
        current_device = snapshot.get("device") or {}
        current_nodes = snapshot.get("nodes") or []
        matches_current = kind == "account" or (kind == "device" and account.device_id == resource_id) or (kind == "node" and any(node["id"] == resource_id for node in current_nodes))
        if matches_current:
            current.append({"account": account.account, "status": account.status, **snapshot})
            if kind != "account": touch("account", account.id, account.account, is_current=True, status=account.status)
        if kind == "account":
            touch("device", current_device.get("id"), current_device.get("name"), is_current=True)
            for node in current_nodes: touch("node", node["id"], node["name"], is_current=True)
    if kind in ("device", "node"):
        from app.services.device_service import _visible_owner_ids
        query = db.query(Device).filter(Device.is_deleted == False)
        owner_ids = _visible_owner_ids(db, user)
        if owner_ids is not None:
            query = query.filter(Device.owner_id.in_(owner_ids))
        devices = query.all()
        device_ids = [device.id for device in devices]
        device_logs = db.query(DeviceLog).filter(DeviceLog.device_id.in_(device_ids)).order_by(DeviceLog.created_at, DeviceLog.id).all() if device_ids else []
        for device in devices:
            if kind == "device" and device.id != resource_id:
                continue
            current_ids = device.node_ids or ([device.node_id] if device.node_id else [])
            if kind == "device":
                for node_id in current_ids: touch("node", node_id, is_current=True)
            elif resource_id in current_ids:
                touch("device", device.id, device.name, is_current=True)
            for log in device_logs:
                if log.device_id != device.id:
                    continue
                try:
                    changes = json.loads(log.changes or "{}")
                except (ValueError, TypeError):
                    continue
                recorded_ids = set()
                relations = changes.get("relations") or {}
                values = [relations.get("old_node_ids"), relations.get("new_node_ids")]
                values.extend((relations.get(side) or {}).get("node_ids") for side in ("old", "new"))
                for field in ("node_id", "node_ids"):
                    values.extend((changes.get(field) or {}).get(side) for side in ("old", "new"))
                for value in values:
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except ValueError:
                            continue
                    for node_id in value if isinstance(value, list) else [value]:
                        if node_id and str(node_id).isdecimal(): recorded_ids.add(int(node_id))
                if kind == "device":
                    for node_id in recorded_ids: touch("node", node_id, when=log.created_at)
                elif resource_id in recorded_ids:
                    touch("device", device.id, device.name, log.created_at)
    history = list(entries.values())
    return {"current": current, "history": history, "ban_snapshots": bans,
            "counts": {entry_kind: sum(entry["kind"] == entry_kind for entry in history) for entry_kind in ("account", "device", "node")},
            "historical_accounts_now_banned": sum(entry["kind"] == "account" and entry["status"] == "封禁" for entry in history),
            "note": "仅统计当前可见账号的已记录关联；旧记录可能缺失，首次/最近为记录时间，不是精确使用时段。封禁快照是系统登记封禁时的关联，不证明封禁原因。"}


def readable_account_log(db, log):
    field = log.field_name
    labels = {"status": "状态", "account": "账号名称", "operator": "使用人", "registrant": "注册人", "remark": "备注", "device_id": "终端", "node_id": "节点"}
    if field in ("relation_snapshot", "ban_snapshot"):
        snapshot = parse_snapshot(log)
        return {"summary": "登记封禁时的关联" if field == "ban_snapshot" else "关联快照",
                "details": ["终端：" + (snapshot.get("device") or {}).get("name", "未关联"),
                            "节点：" + (" / ".join(node["name"] for node in snapshot.get("nodes", [])) or "未关联")]}
    if field in ("device_id", "node_id"):
        def display(value):
            if not value or not str(value).isdecimal(): return "未关联"
            related = db.get(Device if field == "device_id" else ProxyNode, int(value))
            return related.name if related and field == "device_id" else f"{related.ip}:{related.port}" if related else "历史对象已不存在"
        return {"summary": ("解除" if not log.new_value else "关联" if not log.old_value else "切换") + labels[field],
                "details": [display(log.old_value) + " → " + display(log.new_value)]}
    if log.action == "create": return {"summary": "新增账号", "details": []}
    if field in ("password", "totp_secret", "email_password"):
        return {"summary": "修改账号凭据", "details": ["敏感值不在轨迹中展示"]}
    if field in labels:
        return {"summary": "修改" + labels[field], "details": [(log.old_value or "未设置") + " → " + (log.new_value or "未设置")]}
    return {"summary": "修改账号资料", "details": []}
