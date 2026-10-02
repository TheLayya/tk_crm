import csv
import json
import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.op_account import EmailAccount, EmailAccountRelation, EmailAssetRelation, OpAccount
from app.models.card_key import CardKeyEmailUsage, CardKeyPlatform
from app.models.device import Device
from app.models.proxy_node import ProxyNode
from app.models.team import User
from app.schemas.op_account import (
    EmailAccountCreate, EmailAccountUpdate, EmailAccountResponse,
    EmailImportRequest, EmailRelationRequest, GmailCheckRequest,
)
from app.services.auth_service import require_permission, get_user_data_scope, get_dept_member_usernames
from app.services.gmail_checker_service import check_gmail_accounts, normalize_status
from app.services.op_account_service import parse_email_import_line
from app.services.sale_validation_service import validate_sale_information


router = APIRouter(prefix="/emails", tags=["emails"])


def _platform_json(row):
    return {"id": row.id, "name": row.name, "is_active": row.is_active}


@router.get("/platforms")
def list_email_platforms(db: Session = Depends(get_db), _=Depends(require_permission("email:view"))):
    return [_platform_json(row) for row in db.query(CardKeyPlatform).filter(
        CardKeyPlatform.is_active.is_(True),
    ).order_by(CardKeyPlatform.name).all()]


def scoped_query(db, model, user):
    query = db.query(model)
    scope = get_user_data_scope(db, user)
    if scope != "all":
        allowed = get_dept_member_usernames(db, user) if scope == "dept" else [user.username]
        query = query.filter(or_(model.registrant.in_(allowed), model.operator.in_(allowed)))
    return query


def get_email(db, email_id, user):
    email = scoped_query(db, EmailAccount, user).filter(EmailAccount.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="邮箱不存在或无权访问")
    return email


def validate_values(values):
    if "email" in values:
        email = (values["email"] or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", email):
            raise HTTPException(status_code=422, detail="请输入完整邮箱地址")
        values["email"] = email
    if "management_status" in values and values["management_status"] not in {"闲置", "使用中", "锁定", "废弃", "已出售"}:
        raise HTTPException(status_code=422, detail="使用状态无效")


def validate_sale(values):
    validate_sale_information({**values, "status": values.get("management_status")}, "已出售", require_date=True)


def save(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="邮箱已存在") from None


def email_response(email, count=0, db=None, platform_registrants=None):
    result = EmailAccountResponse.model_validate(email)
    try:
        result.platform_tags = json.loads(email.platform_tags or "[]")
    except (TypeError, ValueError):
        result.platform_tags = []
    result.current_relation_count = count
    result.platform_registrants = platform_registrants or {}
    if db:
        device = db.get(Device, email.device_id) if email.device_id else None
        node = db.get(ProxyNode, email.node_id) if email.node_id else None
        result.device_name = device.name if device else None
        result.node_ip = f"{node.ip}:{node.port}" if node else None
    return result


def validate_assets(db, values, user):
    device_id = values.get("device_id")
    node_id = values.get("node_id")
    scope = get_user_data_scope(db, user)
    allowed = get_dept_member_usernames(db, user) if scope == "dept" else [user.username]
    if device_id:
        device = db.get(Device, device_id)
        if not device or device.is_deleted or device.device_type != "phone":
            raise HTTPException(status_code=422, detail="请选择有效手机终端")
        owner = db.get(User, device.owner_id)
        if scope != "all" and (not owner or owner.username not in allowed):
            raise HTTPException(status_code=403, detail="无权绑定此终端")
    if node_id:
        node = db.get(ProxyNode, node_id)
        if not node or node.status not in {"idle", "active"}:
            raise HTTPException(status_code=422, detail="请选择可用节点")
        if scope != "all":
            visible = scoped_query(db, OpAccount, user).filter_by(node_id=node_id).first()
            email_visible = scoped_query(db, EmailAccount, user).filter_by(node_id=node_id).first()
            if not visible and not email_visible:
                raise HTTPException(status_code=403, detail="无权绑定此节点")


def record_assets(db, email, values, user):
    now = datetime.utcnow()
    for field in ("device_id", "node_id"):
        if field not in values or getattr(email, field) == values[field]:
            continue
        current = db.query(EmailAssetRelation).filter(
            EmailAssetRelation.email_id == email.id,
            getattr(EmailAssetRelation, field).isnot(None), EmailAssetRelation.unbound_at.is_(None),
        ).all()
        for relation in current:
            relation.unbound_at = now
            relation.unbound_by = user.username
        if values[field]:
            db.add(EmailAssetRelation(email_id=email.id, **{field: values[field]}, operator=user.username))


def prepare_trade(values):
    if "sellers" in values:
        values["sellers"] = json.dumps(values["sellers"] or [], ensure_ascii=False)
    for field in ("purchase_price", "sale_price"):
        if values.get(field) is not None and values[field] < 0:
            raise HTTPException(status_code=422, detail="采购和出售金额不能为负数")
    if "platform_tags" in values:
        values["platform_tags"] = json.dumps(list(dict.fromkeys(
            tag.strip() for tag in (values["platform_tags"] or []) if tag and tag.strip()
        )), ensure_ascii=False)


@router.get("")
def list_emails(keyword: str | None = None, management_status: str | None = None,
                platform: str | None = None,
                skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                db: Session = Depends(get_db), user=Depends(require_permission("email:view"))):
    query = scoped_query(db, EmailAccount, user)
    if keyword:
        query = query.filter(or_(EmailAccount.email.ilike(f"%{keyword}%"), EmailAccount.recovery_email.ilike(f"%{keyword}%")))
    if management_status:
        query = query.filter(EmailAccount.management_status == management_status)
    if platform:
        query = query.filter(EmailAccount.platform_tags.icontains(json.dumps(platform.strip(), ensure_ascii=False), autoescape=True))
    total = query.count()
    emails = query.order_by(EmailAccount.id.desc()).offset(skip).limit(limit).all()
    email_ids = [email.id for email in emails]
    counts = dict(db.query(EmailAccountRelation.email_id, func.count(EmailAccountRelation.id)).filter(
        EmailAccountRelation.email_id.in_(email_ids),
        EmailAccountRelation.unbound_at.is_(None),
    ).group_by(EmailAccountRelation.email_id).all())
    registrations = {}
    if email_ids:
        for email_id, platform_name, username in db.query(CardKeyEmailUsage.email_id, CardKeyEmailUsage.platform, CardKeyEmailUsage.username).filter(CardKeyEmailUsage.email_id.in_(email_ids)).order_by(CardKeyEmailUsage.completed_at.desc()).all():
            registrations.setdefault(email_id, {}).setdefault(platform_name, username)
    return {"total": total, "items": [email_response(email, counts.get(email.id, 0), db, registrations.get(email.id)) for email in emails]}


@router.post("", response_model=EmailAccountResponse)
def create_email(body: EmailAccountCreate, db: Session = Depends(get_db), user=Depends(require_permission("email:manage"))):
    values = body.model_dump()
    validate_values(values)
    validate_sale(values)
    validate_assets(db, values, user)
    prepare_trade(values)
    values["registrant"] = user.username
    email = EmailAccount(**values)
    db.add(email)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="邮箱已存在") from None
    for field in ("device_id", "node_id"):
        if values.get(field):
            db.add(EmailAssetRelation(email_id=email.id, **{field: values[field]}, operator=user.username))
    save(db)
    return email_response(email, db=db)


@router.post("/import")
def import_emails(body: EmailImportRequest, db: Session = Depends(get_db), user=Depends(require_permission("email:import"))):
    lines = [(number, line) for number, line in enumerate(body.text.lstrip("\ufeff").splitlines(), 1) if line.strip()]
    if not lines or len(lines) > 5000:
        raise HTTPException(status_code=422, detail="每次请输入 1-5000 行邮箱")
    rows = []
    for number, line in lines:
        result = {"line": number}
        try:
            values = parse_email_import_line(line)
            values["purchase_channel"] = body.purchase_channel
            values["purchase_price"] = body.purchase_price
            values["email"] = values.pop("account")
            result["email"] = values["email"]
            if db.query(EmailAccount).filter_by(email=values["email"]).first():
                result["_result"] = "duplicate"
            else:
                email = EmailAccount(**values, registrant=user.username)
                db.add(email)
                db.commit()
                result.update(_result="success", _id=email.id)
        except (ValueError, csv.Error):
            db.rollback()
            result.update(_result="failed", _reason="无法识别邮箱、字段数量或注册时间；支持 |、----、: 四或六字段，时间可填年份或完整日期")
        except IntegrityError:
            db.rollback()
            result["_result"] = "duplicate"
        rows.append(result)
    return {"total": len(rows), "success": sum(row["_result"] == "success" for row in rows),
            "duplicates": sum(row["_result"] == "duplicate" for row in rows),
            "failed": sum(row["_result"] == "failed" for row in rows), "rows": rows}


@router.post("/check")
def check_emails(body: GmailCheckRequest, db: Session = Depends(get_db), user=Depends(require_permission("email:check"))):
    from app.api.op_accounts import gmail_check_lock
    emails = [get_email(db, email_id, user) for email_id in dict.fromkeys(body.account_ids)]
    if any(not email.email.endswith("@gmail.com") for email in emails):
        raise HTTPException(status_code=422, detail="当前仅支持 Gmail 检测")
    if not gmail_check_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="已有 Gmail 检测进行中，请稍后重试")
    try:
        results = {row["email"].lower(): row for row in check_gmail_accounts([email.email for email in emails])}
        now = datetime.utcnow()
        for email in emails:
            raw = results[email.email]["status"]
            email.gmail_check_status = normalize_status(raw)
            email.gmail_check_raw_status = raw[:100]
            email.gmail_checked_at = now
        db.commit()
    except (httpx.HTTPError, ValueError, RuntimeError):
        db.rollback()
        raise HTTPException(status_code=502, detail="检测服务不可用，未覆盖原结果") from None
    finally:
        gmail_check_lock.release()
    return {"checked": len(emails)}


@router.get("/account-options")
def account_options(keyword: str = "", db: Session = Depends(get_db), user=Depends(require_permission("op_account:view"))):
    accounts = scoped_query(db, OpAccount, user).filter(OpAccount.platform != "gmail")
    if keyword:
        accounts = accounts.filter(OpAccount.account.ilike(f"%{keyword}%"))
    return [{"id": account.id, "label": f"{account.platform.upper()} · {account.account} · {account.status}"}
            for account in accounts.limit(100).all()]


@router.get("/for-account/{account_id}")
def account_emails(account_id: int, db: Session = Depends(get_db),
                   user=Depends(require_permission("email:view")), _=Depends(require_permission("op_account:view"))):
    if not scoped_query(db, OpAccount, user).filter_by(id=account_id).first():
        raise HTTPException(status_code=404, detail="运营账号不存在或无权访问")
    accessible = scoped_query(db, EmailAccount, user).with_entities(EmailAccount.id).subquery()
    rows = db.query(EmailAccountRelation).filter(
        EmailAccountRelation.op_account_id == account_id,
        EmailAccountRelation.email_id.in_(db.query(accessible.c.id)),
    ).order_by(EmailAccountRelation.bound_at.desc()).all()
    return [{"id": row.id, "email_id": row.email_id, "email": row.email_account.email,
             "bound_at": row.bound_at, "unbound_at": row.unbound_at,
             "check_status": row.email_account.gmail_check_status,
             "operator": row.operator, "unbound_by": row.unbound_by} for row in rows]


@router.put("/{email_id}", response_model=EmailAccountResponse)
def update_email(email_id: int, body: EmailAccountUpdate, db: Session = Depends(get_db), user=Depends(require_permission("email:manage"))):
    email = get_email(db, email_id, user)
    values = body.model_dump(exclude_unset=True)
    validate_values(values)
    validate_sale({**{field: getattr(email, field) for field in ("management_status", "sale_customer", "sale_price", "sale_date", "sellers")}, **values})
    validate_assets(db, values, user)
    prepare_trade(values)
    record_assets(db, email, values, user)
    for field, value in values.items():
        setattr(email, field, value)
    save(db)
    return email_response(email, db=db)


@router.delete("/{email_id}")
def delete_email(email_id: int, db: Session = Depends(get_db), user=Depends(require_permission("email:manage"))):
    email = get_email(db, email_id, user)
    if db.query(EmailAccountRelation).filter_by(email_id=email_id).first() or db.query(EmailAssetRelation).filter_by(email_id=email_id).first():
        raise HTTPException(status_code=409, detail="邮箱已有绑定历史，请设为废弃以保留追溯记录")
    db.delete(email)
    db.commit()
    return {"deleted": True}


@router.get("/{email_id}/asset-history")
def asset_history(email_id: int, db: Session = Depends(get_db), user=Depends(require_permission("email:view"))):
    get_email(db, email_id, user)
    rows = db.query(EmailAssetRelation).filter_by(email_id=email_id).order_by(EmailAssetRelation.bound_at.desc()).all()
    return [{"id": row.id, "kind": "手机" if row.device_id else "节点",
             "name": row.device.name if row.device else (f"{row.node.ip}:{row.node.port}" if row.node else "资源已删除"),
             "bound_at": row.bound_at, "unbound_at": row.unbound_at,
             "operator": row.operator, "unbound_by": row.unbound_by} for row in rows]


@router.get("/{email_id}/relations")
def relations(email_id: int, db: Session = Depends(get_db), user=Depends(require_permission("email:view"))):
    get_email(db, email_id, user)
    accessible = scoped_query(db, OpAccount, user).with_entities(OpAccount.id).subquery()
    rows = db.query(EmailAccountRelation).filter(
        EmailAccountRelation.email_id == email_id, EmailAccountRelation.op_account_id.in_(db.query(accessible.c.id)),
    ).order_by(EmailAccountRelation.bound_at.desc()).all()
    return [{"id": row.id, "op_account_id": row.op_account_id, "platform": row.op_account.platform,
             "account": row.op_account.account, "status": row.op_account.status,
             "bound_at": row.bound_at, "unbound_at": row.unbound_at,
             "operator": row.operator, "unbound_by": row.unbound_by, "remark": row.remark} for row in rows]


@router.post("/{email_id}/relations")
def bind_account(email_id: int, body: EmailRelationRequest, db: Session = Depends(get_db),
                 user=Depends(require_permission("email:manage")), _=Depends(require_permission("op_account:edit"))):
    email = get_email(db, email_id, user)
    account = scoped_query(db, OpAccount, user).filter(OpAccount.id == body.op_account_id, OpAccount.platform != "gmail").first()
    if not account:
        raise HTTPException(status_code=404, detail="运营账号不存在或无权访问")
    current = db.query(EmailAccountRelation).filter_by(email_id=email_id, op_account_id=account.id, unbound_at=None).first()
    if current:
        raise HTTPException(status_code=409, detail="已经绑定，无需重复绑定")
    if email.management_status in {"废弃", "锁定", "已出售"}:
        raise HTTPException(status_code=409, detail="锁定、废弃或已出售邮箱不能新增绑定")
    db.add(EmailAccountRelation(email_id=email_id, op_account_id=account.id, operator=user.username, remark=body.remark))
    email.management_status = "使用中"
    save(db)
    return {"bound": True}


@router.delete("/{email_id}/relations/{relation_id}")
def unbind_account(email_id: int, relation_id: int, db: Session = Depends(get_db),
                   user=Depends(require_permission("email:manage")), _=Depends(require_permission("op_account:edit"))):
    email = get_email(db, email_id, user)
    relation = db.query(EmailAccountRelation).filter_by(id=relation_id, email_id=email_id, unbound_at=None).first()
    if not relation or not scoped_query(db, OpAccount, user).filter_by(id=relation.op_account_id).first():
        raise HTTPException(status_code=404, detail="当前绑定不存在或无权访问")
    relation.unbound_at = datetime.utcnow()
    relation.unbound_by = user.username
    db.flush()
    if email.management_status == "使用中" and not db.query(EmailAccountRelation).filter_by(email_id=email_id, unbound_at=None).first():
        email.management_status = "闲置"
    db.commit()
    return {"unbound": True}
