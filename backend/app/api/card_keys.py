import hashlib
import json
import base64
import hmac
import struct
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.card_key import CardKey, CardKeyPlatform, CardKeyProject
from app.models.op_account import EmailAccount
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
    return {"id": project.id, "name": project.name, "description": project.description or "",
            "target_platform": project.target_platform or "",
            "members": _members(project), "total": total or 0, "available": available or 0,
            "claimed": claimed or 0, "consumed": consumed or 0, "created_by": project.created_by,
            "created_at": _time_json(project.created_at), "is_active": project.is_active,
            "can_claim": bool(user and _allowed(project, user, db) and project.is_active)}


def _time_json(value):
    return value.isoformat() + "Z" if value else None


def _platform_json(platform):
    return {"id": platform.id, "name": platform.name, "is_active": platform.is_active}


def _key_json(key):
    return {"id": key.id, "content": key.content, "status": key.status,
            "claimed_by": key.claimed_by, "claimed_at": _time_json(key.claimed_at),
            "consumed_at": _time_json(key.consumed_at), "history": key.history or []}


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
              status: str = "", mine: bool = False,
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
        if status not in ("available", "claimed", "consumed"):
            raise HTTPException(422, "无效状态")
        query = query.filter(CardKey.status == status)
    return {"items": [_key_json(key) for key in query.order_by(CardKey.id.desc()).offset((page - 1) * page_size).limit(page_size)],
            "total": query.count()}


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
    import json
    tags = _email_json(email)["platform_tags"]
    if platform.casefold() not in {tag.casefold() for tag in tags}:
        tags.append(platform)
    changed = db.execute(update(EmailAccount).where(
        EmailAccount.id == email.id, EmailAccount.claimed_by == user.username,
        EmailAccount.claimed_platform == platform, EmailAccount.claimed_at == email.claimed_at,
        EmailAccount.platform_tags == email.platform_tags,
    ).values(platform_tags=json.dumps(tags, ensure_ascii=False), claimed_by=None, claimed_at=None,
             claimed_platform=None)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "邮箱状态已变化，请刷新后重试")
    db.commit()
    db.refresh(email)
    return _email_json(email)
