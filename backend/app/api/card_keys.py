import hashlib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.card_key import CardKey, CardKeyProject
from app.models.team import User
from app.services.auth_service import require_permission, _get_user_permissions

router = APIRouter(prefix="/card-keys", tags=["Card keys"])


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    members: list[str] = Field(default_factory=list, max_length=500)
    is_active: bool = True


class ImportBody(BaseModel):
    content: str = Field(min_length=1, max_length=10000000)


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
            "members": _members(project), "total": total or 0, "available": available or 0,
            "claimed": claimed or 0, "consumed": consumed or 0, "created_by": project.created_by,
            "created_at": _time_json(project.created_at), "is_active": project.is_active,
            "can_claim": bool(user and _allowed(project, user, db) and project.is_active)}


def _time_json(value):
    return value.isoformat() + "Z" if value else None


def _key_json(key):
    return {"id": key.id, "content": key.content, "status": key.status,
            "claimed_by": key.claimed_by, "claimed_at": _time_json(key.claimed_at),
            "consumed_at": _time_json(key.consumed_at), "history": key.history or []}


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


@router.get("")
def list_projects(db: Session = Depends(get_db), user=Depends(require_permission("card_key:view"))):
    projects = db.query(CardKeyProject).order_by(CardKeyProject.updated_at.desc()).all()
    return [_project_json(p, db, user) for p in projects if _allowed(p, user, db) or db.query(CardKey.id).filter(
        CardKey.project_id == p.id, CardKey.claimed_by == user.username).first()]


@router.post("", status_code=201)
def create_project(body: ProjectBody, db: Session = Depends(get_db), user=Depends(require_permission("card_key:manage"))):
    names = _validate_project(body, db)
    project = CardKeyProject(name=body.name.strip(), description=body.description.strip(),
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
    project.member_usernames = ",".join(_validate_project(body, db))
    project.name, project.description, project.is_active = body.name.strip(), body.description.strip(), body.is_active
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
