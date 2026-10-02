import hashlib
import json
import base64
import hmac
import struct
import time
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.card_key import CardKey, CardKeyEmailUsage, CardKeyPlatform, CardKeyProject
from app.models.op_account import EmailAccount, EmailAccountRelation, OpAccount
from app.models.team import User
from app.services.auth_service import require_permission, _get_user_permissions

router = APIRouter(prefix="/card-keys", tags=["Card keys"])


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    target_platform: str = Field(default="", max_length=100)
    members: list[str] = Field(default_factory=list, max_length=500)
    is_active: bool = True


class ImportBody(BaseModel):
    content: str = Field(min_length=1, max_length=10000000)


class PlatformBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


def _members(project):
    return [x for x in (project.member_usernames or "").split(",") if x]


def _manager(user, db):
    return user.is_super_admin or "card_key:manage" in _get_user_permissions(db, user.id)


def _allowed(project, user, db):
    return _manager(user, db) or "__all__" in _members(project) or user.username in _members(project)


def _project_json(project, db, user=None):
    total, available, claimed, consumed = db.query(
        func.count(CardKey.id),
        func.sum(case((CardKey.status == "available", 1), else_=0)),
        func.sum(case((CardKey.status == "claimed", 1), else_=0)),
        func.sum(case((CardKey.status == "consumed", 1), else_=0)),
    ).filter(CardKey.project_id == project.id).one()
    platform = (project.target_platform or "").strip()
    email_available = email_claimed = 0
    email_normal_available = 0
    if platform:
        email_query = db.query(EmailAccount).filter(EmailAccount.management_status == "闲置")
        email_available = email_query.filter(EmailAccount.claimed_by.is_(None), or_(EmailAccount.platform_tags.is_(None), ~EmailAccount.platform_tags.icontains(json.dumps(platform, ensure_ascii=False), autoescape=True))).count()
        email_claimed = db.query(EmailAccount).filter(EmailAccount.claimed_platform == platform, EmailAccount.claimed_by.isnot(None)).count()
        email_normal_available = email_query.filter(EmailAccount.claimed_by.is_(None), EmailAccount.gmail_check_status == "正常", or_(EmailAccount.platform_tags.is_(None), ~EmailAccount.platform_tags.icontains(json.dumps(platform, ensure_ascii=False), autoescape=True))).count()
    members = _members(project)
    member_stats = []
    usernames = {row.username for row in db.query(User).filter(User.is_active.is_(True)).all()} if "__all__" in members else set(members)
    key_rows = db.query(CardKey.claimed_by, CardKey.status, func.count(CardKey.id)).filter(CardKey.project_id == project.id, CardKey.claimed_by.isnot(None)).group_by(CardKey.claimed_by, CardKey.status).all()
    email_rows = db.query(CardKeyEmailUsage.username, func.count(CardKeyEmailUsage.id)).filter(CardKeyEmailUsage.project_id == project.id).group_by(CardKeyEmailUsage.username).all()
    key_stats = {}
    for username, status, count in key_rows:
        if status in {"claimed", "consumed"}:
            key_stats.setdefault(username, {"claimed": 0, "consumed": 0})[status] += count
    email_stats = dict(email_rows)
    usernames.update(key_stats)
    usernames.update(email_stats)
    for username in sorted(usernames):
        values = key_stats.get(username, {"claimed": 0, "consumed": 0})
        member_stats.append({"username": username, "claimed": values["claimed"], "consumed": values["consumed"], "emails_completed": email_stats.get(username, 0)})
    return {"id": project.id, "name": project.name, "description": project.description or "",
            "target_platform": project.target_platform or "",
            "members": members, "total": total or 0, "available": available or 0,
            "claimed": claimed or 0, "consumed": consumed or 0, "created_by": project.created_by,
            "created_at": _time_json(project.created_at), "is_active": project.is_active,
            "can_claim": bool(user and _allowed(project, user, db) and project.is_active),
            "email_available": email_available, "email_normal_available": email_normal_available,
            "email_claimed": email_claimed, "member_stats": member_stats,
            "emails_completed": sum(email_stats.values())}


def _time_json(value):
    return value.isoformat() + "Z" if value else None


def _platform_json(platform):
    return {"id": platform.id, "name": platform.name, "is_active": platform.is_active}


def _key_json(key):
    return {"id": key.id, "content": key.content, "status": key.status,
            "claimed_by": key.claimed_by, "claimed_at": _time_json(key.claimed_at),
            "consumed_at": _time_json(key.consumed_at), "history": key.history or [], "remark": key.remark}


def _email_json(email):
    import json
    try:
        platform_tags = json.loads(email.platform_tags or "[]")
    except (TypeError, ValueError):
        platform_tags = []
    return {"id": email.id, "email": email.email, "password": email.password,
            "recovery_email": email.recovery_email, "totp_secret": email.totp_secret,
            "platform_tags": platform_tags,
            "claimed_by": email.claimed_by, "claimed_at": _time_json(email.claimed_at),
            "claimed_platform": email.claimed_platform}


def _totp_code(secret):
    try:
        if not secret:
            return None, None
        normalized = "".join(str(secret).split()).replace("-", "").upper()
        key = base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)
        if not key:
            return None, None
        timestamp = int(time.time())
        counter = timestamp // 30
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
        return f"{number:06d}", 30 - (timestamp % 30)
    except (ValueError, TypeError, base64.binascii.Error):
        return None, None


def _history(key, action, username, now):
    events = list(key.history or [])
    if not events and key.claimed_by:
        events.append({"action": "claim", "username": key.claimed_by, "time": _time_json(key.claimed_at)})
    events.append({"action": action, "username": username, "time": _time_json(now)})
    return events


def _validate_project(body, db):
    if not body.name.strip():
        raise HTTPException(422, "请填写项目名称")
    names = list(dict.fromkeys(x.strip() for x in body.members if x.strip()))
    active = {u.username for u in db.query(User).filter(User.is_active.is_(True)).all()}
    if not names or any(name != "__all__" and name not in active for name in names):
        raise HTTPException(422, "请选择有效的协助成员")
    if "__all__" in names:
        return ["__all__"]
    return names


@router.get("/members")
def members(db: Session = Depends(get_db), _=Depends(require_permission("card_key:view"))):
    return [{"username": u.username, "real_name": u.real_name} for u in db.query(User)
            .filter(User.is_active.is_(True)).order_by(User.username).all()]


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db), _=Depends(require_permission("card_key:view"))):
    return [_platform_json(row) for row in db.query(CardKeyPlatform).order_by(CardKeyPlatform.is_active.desc(), CardKeyPlatform.name).all()]


@router.post("/platforms", status_code=201)
def create_platform(body: PlatformBody, db: Session = Depends(get_db), _=Depends(require_permission("card_key:manage"))):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "请填写平台名称")
    if db.query(CardKeyPlatform).filter(CardKeyPlatform.name.ilike(name)).first():
        raise HTTPException(409, "平台名称已存在")
    row = CardKeyPlatform(name=name, is_active=body.is_active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _platform_json(row)


@router.put("/platforms/{platform_id}")
def update_platform(platform_id: int, body: PlatformBody, db: Session = Depends(get_db), _=Depends(require_permission("card_key:manage"))):
    row = db.get(CardKeyPlatform, platform_id)
    if not row:
        raise HTTPException(404, "平台不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "请填写平台名称")
    duplicate = db.query(CardKeyPlatform).filter(CardKeyPlatform.id != platform_id, CardKeyPlatform.name.ilike(name)).first()
    if duplicate:
        raise HTTPException(409, "平台名称已存在")
    row.name, row.is_active = name, body.is_active
    db.commit()
    return _platform_json(row)


@router.get("")
def list_projects(db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    projects = db.query(CardKeyProject).order_by(CardKeyProject.updated_at.desc()).all()
    return [_project_json(p, db, user) for p in projects if _allowed(p, user, db) or db.query(CardKey.id).filter(
        CardKey.project_id == p.id, CardKey.claimed_by == user.username).first()]


@router.post("", status_code=201)
def create_project(body: ProjectBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:manage"))):
    names = _validate_project(body, db)
    project = CardKeyProject(name=body.name.strip(), description=body.description.strip(), target_platform=body.target_platform.strip() or None,
                             member_usernames=",".join(names), created_by=user.username, is_active=body.is_active)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_json(project, db)


@router.put("/{project_id}")
def update_project(project_id: int, body: ProjectBody, db: Session = Depends(get_db), _=Depends(require_permission("card_key:manage"))):
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if (body.target_platform.strip() or None) != project.target_platform and project.target_platform and db.query(EmailAccount).filter(
        EmailAccount.claimed_platform == project.target_platform, EmailAccount.claimed_by.isnot(None),
    ).first():
        raise HTTPException(409, "该平台仍有领取中的邮箱，请先完成或归还后修改平台")
    project.member_usernames = ",".join(_validate_project(body, db))
    project.name, project.description, project.target_platform, project.is_active = body.name.strip(), body.description.strip(), body.target_platform.strip() or None, body.is_active
    db.commit()
    return _project_json(project, db)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), _=Depends(require_permission("card_key:manage"))):
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.status != "available").first() or db.query(CardKeyEmailUsage).filter_by(project_id=project_id).first():
        raise HTTPException(409, "项目已有领取或完成记录，请结束项目以保留历史")
    if project.target_platform and db.query(EmailAccount).filter(EmailAccount.claimed_platform == project.target_platform, EmailAccount.claimed_by.isnot(None)).first():
        raise HTTPException(409, "该平台有领取中的邮箱，请先完成注册或归还")
    db.query(CardKey).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return {"deleted": True}


@router.post("/{project_id}/import")
def import_keys(project_id: int, body: ImportBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:manage"))):
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.is_active:
        raise HTTPException(409, "项目已结束，不能导入")
    values = [line.strip() for line in body.content.splitlines() if line.strip()]
    if not values or len(values) > 10000 or any(len(value) > 8192 for value in values):
        raise HTTPException(422, "每次导入1至10000行，每行最多8192字符")
    project.updated_at = datetime.utcnow()
    db.flush()
    added, duplicates = 0, 0
    for value in values:
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
        try:
            with db.begin_nested():
                db.add(CardKey(project_id=project_id, content=value, fingerprint=fingerprint, created_by=user.username))
                db.flush()
            added += 1
        except IntegrityError:
            duplicates += 1
    db.commit()
    return {"added": added, "duplicates": duplicates}


@router.get("/{project_id}/keys")
def list_keys(project_id: int, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
              status: str = "", mine: bool = False, keyword: str = "",
              db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    manager = _manager(user, db)
    query = db.query(CardKey).filter(CardKey.project_id == project_id)
    if not manager or mine:
        query = query.filter(CardKey.claimed_by == user.username)
    if not _allowed(project, user, db) and not db.query(CardKey.id).filter(
        CardKey.project_id == project_id, CardKey.claimed_by == user.username).first():
        raise HTTPException(403, "你不是该项目协助成员")
    if status:
        if status not in ("available", "claimed", "consumed", "invalid"):
            raise HTTPException(422, "无效状态")
        query = query.filter(CardKey.status == status)
    if not keyword.strip():
        return {"items": [_key_json(key) for key in query.order_by(CardKey.id.desc()).offset((page - 1) * page_size).limit(page_size)], "total": query.count()}
    rows = query.order_by(CardKey.id.desc()).all()
    if keyword.strip():
        needle = keyword.strip().casefold()
        rows = [key for key in rows if needle in (key.content or "").casefold()]
    start = (page - 1) * page_size
    return {"items": [_key_json(key) for key in rows[start:start + page_size]], "total": len(rows)}


@router.post("/{project_id}/claim")
def claim_key(project_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not _allowed(project, user, db):
        raise HTTPException(403, "你不是该项目协助成员")
    pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
    if pending:
        return _key_json(pending)
    if not project.is_active:
        raise HTTPException(409, "项目已结束，不能领取")
    key = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.status == "available").order_by(CardKey.id).first()
    if not key:
        raise HTTPException(409, "卡密已领完")
    now = datetime.utcnow()
    try:
        changed = db.execute(update(CardKey).where(and_(
            CardKey.id == key.id, CardKey.status == "available", CardKey.history == (key.history or []),
        )).values(
            status="claimed", claimed_by=user.username, pending_owner=user.username, claimed_at=now,
            history=_history(key, "claim", user.username, now))).rowcount
        if changed != 1:
            db.rollback()
            pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
            if pending:
                return _key_json(pending)
            raise HTTPException(409, "卡密已被其他成员领取，请重试")
        db.commit()
    except IntegrityError:
        db.rollback()
        pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
        if pending:
            return _key_json(pending)
        raise HTTPException(409, "领取冲突，请重试")
    db.refresh(key)
    return _key_json(key)


@router.post("/{project_id}/keys/{key_id}/consume")
def consume_key(project_id: int, key_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    key = db.query(CardKey).filter(CardKey.id == key_id, CardKey.project_id == project_id).first()
    if not key:
        raise HTTPException(404, "卡密不存在")
    if not _manager(user, db) and key.claimed_by != user.username:
        raise HTTPException(403, "只能确认自己领取的卡密")
    if key.status == "consumed":
        return {"id": key.id, "status": key.status}
    if key.status != "claimed":
        raise HTTPException(409, "卡密当前不可确认消耗")
    now = datetime.utcnow()
    changed = db.execute(update(CardKey).where(
        CardKey.id == key.id, CardKey.status == "claimed", CardKey.claimed_by == key.claimed_by,
        CardKey.claimed_at == key.claimed_at,
    ).values(status="consumed", consumed_at=now, pending_owner=None,
             history=_history(key, "consume", user.username, now))).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "卡密领取状态已变化，请刷新后操作")
    db.commit()
    db.refresh(key)
    return {"id": key.id, "status": key.status}


@router.post("/{project_id}/keys/{key_id}/release")
def release_key(project_id: int, key_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    key = db.query(CardKey).filter(CardKey.id == key_id, CardKey.project_id == project_id).first()
    if not key:
        raise HTTPException(404, "卡密不存在")
    if not _manager(user, db) and key.claimed_by != user.username:
        raise HTTPException(403, "只能归还自己领取的卡密")
    if key.status != "claimed":
        raise HTTPException(409, "只有已领取且未消耗的卡密可以归还")
    now = datetime.utcnow()
    changed = db.execute(update(CardKey).where(
        CardKey.id == key.id, CardKey.status == "claimed", CardKey.claimed_by == key.claimed_by,
        CardKey.claimed_at == key.claimed_at,
    ).values(status="available", pending_owner=None, claimed_by=None, claimed_at=None, consumed_at=None,
             history=_history(key, "release", user.username, now))).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "卡密领取状态已变化，请刷新后操作")
    db.commit()
    return {"id": key.id, "status": "available"}


class InvalidKeyBody(BaseModel):
    remark: str = Field(min_length=1, max_length=2000)


@router.post("/{project_id}/keys/{key_id}/invalid")
def mark_key_invalid(project_id: int, key_id: int, body: InvalidKeyBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    key = db.query(CardKey).filter(CardKey.id == key_id, CardKey.project_id == project_id).first()
    if not key:
        raise HTTPException(404, "卡密不存在")
    if not _manager(user, db) and (key.status != "claimed" or key.claimed_by != user.username):
        raise HTTPException(403, "只能报告自己领取的卡密")
    if not body.remark.strip():
        raise HTTPException(422, "请填写无效原因")
    if key.status == "invalid":
        return _key_json(key)
    if key.status not in {"available", "claimed"}:
        raise HTTPException(409, "已消耗卡密不能标记无效")
    now = datetime.utcnow()
    history = _history(key, "invalid", user.username, now)
    history[-1]["remark"] = body.remark.strip()
    changed = db.execute(update(CardKey).where(CardKey.id == key.id, CardKey.status == key.status, CardKey.history == (key.history or [])).values(status="invalid", pending_owner=None, remark=body.remark.strip(), history=history)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "卡密状态已变化，请刷新后重试")
    db.commit()
    db.refresh(key)
    return _key_json(key)


class KeyRemarkBody(BaseModel):
    remark: str = Field(max_length=2000)


@router.put("/{project_id}/keys/{key_id}/remark")
def update_key_remark(project_id: int, key_id: int, body: KeyRemarkBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    key = db.query(CardKey).filter_by(id=key_id, project_id=project_id).first()
    if not key:
        raise HTTPException(404, "卡密不存在")
    if not _manager(user, db) and key.claimed_by != user.username:
        raise HTTPException(403, "只能备注自己领取的卡密")
    history = _history(key, "remark", user.username, datetime.utcnow())
    history[-1]["remark"] = body.remark.strip()
    changed = db.execute(update(CardKey).where(CardKey.id == key.id, CardKey.history == (key.history or [])).values(remark=body.remark.strip(), history=history)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "记录已变化，请刷新后重试")
    db.commit()
    db.refresh(key)
    return _key_json(key)


@router.get("/{project_id}/work-report")
def work_report(project_id: int, date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), user=Depends(require_permission("card_key:manage"))):
    if not db.get(CardKeyProject, project_id):
        raise HTTPException(404, "项目不存在")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    start = datetime.combine(date_from, datetime.min.time()) - timedelta(hours=8) if date_from else None
    end = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1, hours=-8) if date_to else None
    items = []
    keys = db.query(CardKey).filter_by(project_id=project_id, status="consumed")
    usages = db.query(CardKeyEmailUsage, EmailAccount.email).outerjoin(EmailAccount, CardKeyEmailUsage.email_id == EmailAccount.id).filter(CardKeyEmailUsage.project_id == project_id)
    if start:
        keys = keys.filter(CardKey.consumed_at >= start)
        usages = usages.filter(CardKeyEmailUsage.completed_at >= start)
    if end:
        keys = keys.filter(CardKey.consumed_at < end)
        usages = usages.filter(CardKeyEmailUsage.completed_at < end)
    for key in keys.all():
        items.append({"kind": "卡密消耗", "record_id": key.id, "username": key.claimed_by, "time": _time_json(key.consumed_at), "reference": f"卡密 #{key.id}"})
    for usage, email in usages.all():
        items.append({"kind": "平台注册", "record_id": usage.id, "username": usage.username, "time": _time_json(usage.completed_at), "reference": f"{usage.platform} · {email or '邮箱已删除'}"})
    totals = {}
    for item in items:
        values = totals.setdefault(item["username"], {"username": item["username"], "keys_consumed": 0, "emails_completed": 0})
        values["keys_consumed" if item["kind"] == "卡密消耗" else "emails_completed"] += 1
    return {"members": sorted(totals.values(), key=lambda row: row["username"] or ""), "items": sorted(items, key=lambda row: row["time"] or "", reverse=True)}


@router.get("/{project_id}/email")
def get_claimed_email(project_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    email = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                           EmailAccount.claimed_platform == project.target_platform).first()
    return _email_json(email) if email else None


@router.post("/{project_id}/email/claim")
def claim_email(project_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    platform = (project.target_platform or "").strip() if project else ""
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    if not platform:
        raise HTTPException(422, "请先为项目设置目标平台")
    pending = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                             EmailAccount.claimed_platform == platform).first()
    if pending:
        return _email_json(pending)
    if not project.is_active:
        raise HTTPException(409, "项目已结束，不能领取新邮箱")
    candidates = db.query(EmailAccount).filter(
        EmailAccount.management_status == "闲置", EmailAccount.claimed_by.is_(None),
        or_(EmailAccount.platform_tags.is_(None), ~EmailAccount.platform_tags.icontains(json.dumps(platform, ensure_ascii=False), autoescape=True)),
    ).order_by(EmailAccount.id).all()
    for candidate in candidates:
        try:
            changed = db.execute(update(EmailAccount).where(
                EmailAccount.id == candidate.id, EmailAccount.management_status == "闲置",
                EmailAccount.claimed_by.is_(None), EmailAccount.platform_tags == candidate.platform_tags,
            ).values(claimed_by=user.username, claimed_at=datetime.utcnow(), claimed_platform=platform)).rowcount
        except IntegrityError:
            db.rollback()
            pending = db.query(EmailAccount).filter_by(claimed_by=user.username, claimed_platform=platform).first()
            if pending:
                return _email_json(pending)
            raise HTTPException(409, "领取状态已变化，请刷新后重试") from None
        if changed == 1:
            db.commit()
            db.refresh(candidate)
            return _email_json(candidate)
        db.rollback()
    raise HTTPException(409, "没有可用于该平台的未注册邮箱")


@router.get("/{project_id}/email/totp")
def get_claimed_email_totp(project_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    email = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                           EmailAccount.claimed_platform == project.target_platform).first()
    if not email:
        raise HTTPException(404, "没有找到你领取的邮箱")
    code, remaining = _totp_code(email.totp_secret)
    if not code:
        raise HTTPException(422, "该邮箱没有有效的 2FA 密钥")
    from fastapi.responses import JSONResponse
    return JSONResponse({"code": code, "remaining": remaining}, headers={"Cache-Control": "no-store"})


@router.post("/{project_id}/email/release")
def release_email(project_id: int, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    if not (project.target_platform or "").strip():
        raise HTTPException(422, "请先为项目设置目标平台")
    changed = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                             EmailAccount.claimed_platform == project.target_platform).update(
        {EmailAccount.claimed_by: None, EmailAccount.claimed_at: None, EmailAccount.claimed_platform: None},
        synchronize_session=False)
    db.commit()
    if not changed:
        raise HTTPException(404, "没有找到你领取的邮箱")
    return {"released": True}


class CompleteEmailBody(BaseModel):
    platform: str = Field(min_length=1, max_length=100)
    account: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    totp_secret: str | None = Field(default=None, max_length=255)


@router.post("/{project_id}/email/complete")
def complete_email(project_id: int, body: CompleteEmailBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    platform = body.platform.strip()
    if not platform or platform != project.target_platform:
        raise HTTPException(422, "注册平台必须与项目目标平台一致")
    email = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                           EmailAccount.claimed_platform == project.target_platform).first()
    if not email:
        raise HTTPException(404, "没有找到你领取的邮箱")
    account_name = (body.account or "").strip().lstrip("@")
    platform_key = platform.casefold()
    supported = platform_key in {"tiktok", "youtube", "instagram", "facebook"}
    if supported and not account_name:
        raise HTTPException(422, "请填写刚注册的平台用户名")
    if supported and not user.is_super_admin and "op_account:create" not in _get_user_permissions(db, user.id):
        raise HTTPException(403, "需要创建运营账号权限才能完成该平台注册")
    if supported and db.query(OpAccount).filter(OpAccount.platform == platform_key, OpAccount.account == account_name).first():
        raise HTTPException(409, "该平台账号已存在，请更换账号或在运营账号中关联")
    import json
    tags = _email_json(email)["platform_tags"]
    if platform.casefold() not in {tag.casefold() for tag in tags}:
        tags.append(platform)
    changed = db.execute(update(EmailAccount).where(
        EmailAccount.id == email.id, EmailAccount.claimed_by == user.username,
        EmailAccount.claimed_platform == platform, EmailAccount.claimed_at == email.claimed_at,
        EmailAccount.platform_tags == email.platform_tags,
    ).values(platform_tags=json.dumps(tags, ensure_ascii=False), claimed_by=None, claimed_at=None, claimed_platform=None)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "邮箱领取状态已变化，请刷新后重试")
    operation_account = None
    if supported:
        operation_account = OpAccount(
            platform=platform_key, account=account_name, password=body.password or None,
            totp_secret=body.totp_secret or None, email=email.email,
            registrant=user.username, operator=user.username,
            account_created_at=datetime.utcnow(), status="正常", source="项目注册",
        )
        db.add(operation_account)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "该平台账号已存在，请刷新后重试") from None
        db.add(EmailAccountRelation(email_id=email.id, op_account_id=operation_account.id, operator=user.username))
    db.add(CardKeyEmailUsage(project_id=project.id, email_id=email.id, username=user.username, platform=platform))
    db.commit()
    db.refresh(email)
    return {**_email_json(email), "op_account_id": operation_account.id if operation_account else None, "op_account": account_name if operation_account else None}
