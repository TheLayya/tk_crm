"""Shared ownership scope for operating accounts and proxy nodes."""
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.op_account import EmailAccount, OpAccount
from app.models.proxy_node import ProxyNode
from app.models.team import User
from app.services.auth_service import get_dept_member_usernames, get_user_data_scope


def get_scope_usernames(db: Session, user: User) -> set[str] | None:
    """None means unrestricted; an empty set never grants access."""
    scope = get_user_data_scope(db, user)
    if scope == "all":
        return None
    return set(get_dept_member_usernames(db, user)) if scope == "dept" else {user.username}


def get_scope_user_ids(db: Session, user: User) -> set[int] | None:
    names = get_scope_usernames(db, user)
    if names is None:
        return None
    return {user_id for (user_id,) in db.query(User.id).filter(User.username.in_(names)).all()}


def scoped_op_accounts(db: Session, user: User):
    """Accounts inherit their active terminal owner, never a shared node."""
    query = db.query(OpAccount)
    names = get_scope_usernames(db, user)
    if names is not None:
        devices = db.query(Device.id).filter(
            Device.is_deleted == False, Device.owner_id.in_(get_scope_user_ids(db, user)),
        )
        query = query.filter(or_(
            OpAccount.registrant.in_(names), OpAccount.operator.in_(names),
            OpAccount.device_id.in_(devices),
        ))
    return query


def require_op_account_scope(db: Session, account_ids: list[int], user: User) -> None:
    ids = set(account_ids)
    existing = {account_id for (account_id,) in db.query(OpAccount.id).filter(OpAccount.id.in_(ids)).all()}
    if existing != ids:
        raise HTTPException(status_code=404, detail="部分运营账号不存在")
    visible = {account_id for (account_id,) in scoped_op_accounts(db, user).with_entities(OpAccount.id).filter(OpAccount.id.in_(ids)).all()}
    if visible != ids:
        raise HTTPException(status_code=403, detail="无权操作部分运营账号")


def get_visible_node_ids(db: Session, user: User) -> set[int] | None:
    names = get_scope_usernames(db, user)
    if names is None:
        return None
    ids = {node_id for (node_id,) in db.query(ProxyNode.id).filter(ProxyNode.created_by.in_(names)).all()}
    devices = db.query(Device).filter(
        Device.is_deleted == False, Device.owner_id.in_(get_scope_user_ids(db, user)),
    ).all()
    for device in devices:
        ids.update(device.node_ids or ([device.node_id] if device.node_id else []))
    ids.update(node_id for (node_id,) in scoped_op_accounts(db, user).with_entities(OpAccount.node_id).filter(OpAccount.node_id.isnot(None)).all())
    ids.update(node_id for (node_id,) in db.query(EmailAccount.node_id).filter(
        EmailAccount.node_id.isnot(None),
        or_(EmailAccount.registrant.in_(names), EmailAccount.operator.in_(names)),
    ).all())
    return ids


def require_visible_op_account(db: Session, account_id: int, user: User) -> OpAccount:
    account = db.get(OpAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="运营账号不存在")
    require_op_account_scope(db, [account_id], user)
    return account


def require_account_relation_scope(db: Session, values: dict, user: User) -> None:
    owner_ids = get_scope_user_ids(db, user)
    if owner_ids is None:
        return
    if values.get("device_id") is not None:
        device = db.get(Device, values["device_id"])
        if device and device.owner_id not in owner_ids:
            raise HTTPException(status_code=403, detail="无权关联该终端")
    if values.get("node_id") is not None:
        if values["node_id"] not in get_visible_node_ids(db, user):
            raise HTTPException(status_code=403, detail="无权关联该节点")
