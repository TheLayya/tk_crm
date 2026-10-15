from fastapi.responses import JSONResponse
from typing import Any, Literal, TypedDict, cast


import hashlib
import json
import time
from uuid import uuid4
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from app.core.database import get_db
from app.models.card_key import CardKey, CardKeyBatch, CardKeyEmailUsage, CardKeyPlatform, CardKeyProject
from app.models.op_account import EmailAccount, EmailAccountRelation, OpAccount
from app.models.team import User
from app.services.auth_service import require_permission, _get_user_permissions
from app.services.table_query_service import apply_table_query, apply_table_rows, model_table_fields, parse_table_filters
from app.services.totp_service import totp_code

router = APIRouter(prefix="/card-keys", tags=["Card keys"])


class WorkReportItem(TypedDict):
    kind: str
    record_id: int
    username: str | None
    time: str | None
    reference: str


class WorkReportTotals(TypedDict):
    username: str | None
    keys_consumed: int
    emails_completed: int


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    target_platform: str = Field(default="", max_length=100)
    members: list[str] = Field(default_factory=list, max_length=500)
    is_active: bool = True


class ImportBody(BaseModel):
    content: str = Field(min_length=1, max_length=10000000)
    batch_name: str = Field(default="", max_length=200)
    remark: str = Field(default="", max_length=2000)


class BatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    remark: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "paused"] | None = None
    pause_reason: str | None = Field(default=None, max_length=2000)


class PlatformBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


def _members(project: CardKeyProject) -> list[str]:
    return [x for x in (project.member_usernames or "").split(",") if x]


def _manager(user: User, db: Session) -> bool:
    return user.is_super_admin or "card_key:manage" in _get_user_permissions(db, user.id)


def _allowed(project: CardKeyProject, user: User, db: Session) -> bool:
    return _manager(user, db) or "__all__" in _members(project) or user.username in _members(project)


def _active_batch() -> ColumnElement[bool]:
    return or_(CardKey.batch_id.is_(None), exists().where(
        CardKeyBatch.id == CardKey.batch_id, CardKeyBatch.status == "active"))


def _untouched_key() -> ColumnElement[bool]:
    return and_(CardKey.status == "available", CardKey.claimed_by.is_(None),
                CardKey.claimed_at.is_(None), CardKey.consumed_at.is_(None),
                CardKey.pending_owner.is_(None), CardKey.history == [])


def _project_json(project: CardKeyProject, db: Session, user: User | None = None) -> dict[str, object]:
    total, available, claimed, consumed = db.query(
        func.count(CardKey.id),
        func.sum(case((and_(CardKey.status == "available", _active_batch()), 1), else_=0)),
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
    key_stats: dict[str, dict[str, int]] = {}
    for username, status, count in key_rows:
        if status in {"claimed", "consumed"}:
            key_stats.setdefault(username, {"claimed": 0, "consumed": 0})[status] += count
    email_stats = {username: count for username, count in email_rows}
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


def _time_json(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _platform_json(platform: CardKeyPlatform) -> dict[str, object]:
    return {"id": platform.id, "name": platform.name, "is_active": platform.is_active}


def _key_json(key: CardKey) -> dict[str, object]:
    batch = key.batch
    return {"id": key.id, "content": key.content, "status": key.status,
            "batch_id": key.batch_id, "batch_no": batch.batch_no if batch else "",
            "batch_name": batch.name if batch else "历史未分批",
            "batch_status": batch.status if batch else "active", "batch_remark": batch.remark or "" if batch else "",
            "batch_pause_reason": batch.pause_reason or "" if batch else "",
            "claimed_by": key.claimed_by, "claimed_at": _time_json(key.claimed_at),
            "consumed_at": _time_json(key.consumed_at), "history": key.history or [], "remark": key.remark}


def _batch_json(batch: CardKeyBatch | None, project_id: int, db: Session, owner: str | None = None) -> dict[str, object]:
    query = db.query(CardKey).filter(CardKey.project_id == project_id,
                                     CardKey.batch_id == batch.id if batch else CardKey.batch_id.is_(None))
    if owner:
        query = query.filter(CardKey.claimed_by == owner)
    counts: dict[str, int] = {status: count for status, count in query.with_entities(CardKey.status, func.count(CardKey.id)).group_by(CardKey.status).all()}
    return {"id": batch.id if batch else 0, "project_id": project_id,
            "batch_no": batch.batch_no if batch else "", "name": batch.name if batch else "历史未分批",
            "remark": (batch.remark or "") if batch else "", "status": batch.status if batch else "active",
            "pause_reason": (batch.pause_reason or "") if batch else "", "history": (batch.history or []) if batch else [],
            "created_by": batch.created_by if batch else "", "created_at": _time_json(batch.created_at) if batch else None,
            "updated_at": _time_json(batch.updated_at) if batch else None,
            "total": sum(counts.values()), **{status: counts.get(status, 0) for status in ("available", "claimed", "consumed", "invalid")},
            "can_delete": bool(batch and batch.status != "archived" and not query.filter(~_untouched_key()).first()),
            "has_history": bool(query.filter(~_untouched_key()).first())}


def _email_json(email: EmailAccount) -> dict[str, object]:
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


def _totp_code(secret: object) -> tuple[str | None, int | None]:
    return totp_code(secret, now=time.time())


def _history(key: CardKey, action: str, username: str, now: datetime) -> list[dict[str, object]]:
    events = list(key.history or [])
    if not events and key.claimed_by:
        events.append({"action": "claim", "username": key.claimed_by, "time": _time_json(key.claimed_at)})
    events.append({"action": action, "username": username, "time": _time_json(now)})
    return events


def _validate_project(body: ProjectBody, db: Session) -> list[str]:
    if not body.name.strip():
        raise HTTPException(422, "请填写项目名称")
    names = list(dict.fromkeys(x.strip() for x in body.members if x.strip()))
    active = {u.username for u in db.query(User).filter(User.is_active.is_(True)).all()}
    if not names or any(name != "__all__" and name not in active for name in names):
        raise HTTPException(422, "请选择有效的协助成员")
    if "__all__" in names:
        return ["__all__"]
    return names


@router.get("/members", response_model=None)
def members(db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:view"))) -> list[dict[str, object]]:
    return [{"username": u.username, "real_name": u.real_name} for u in db.query(User)
            .filter(User.is_active.is_(True)).order_by(User.username).all()]


@router.get("/platforms", response_model=None)
def list_platforms(db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:view"))) -> list[dict[str, object]]:
    return [_platform_json(row) for row in db.query(CardKeyPlatform).order_by(CardKeyPlatform.is_active.desc(), CardKeyPlatform.name).all()]


@router.post("/platforms", status_code=201, response_model=None)
def create_platform(body: PlatformBody, db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
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


@router.put("/platforms/{platform_id}", response_model=None)
def update_platform(platform_id: int, body: PlatformBody, db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
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


@router.get("", response_model=None)
def list_projects(db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> list[dict[str, object]]:
    projects = db.query(CardKeyProject).order_by(CardKeyProject.updated_at.desc()).all()
    return [_project_json(p, db, user) for p in projects if _allowed(p, user, db) or db.query(CardKey.id).filter(
        CardKey.project_id == p.id, CardKey.claimed_by == user.username).first()]


@router.post("", status_code=201, response_model=None)
def create_project(body: ProjectBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    names = _validate_project(body, db)
    project = CardKeyProject(name=body.name.strip(), description=body.description.strip(), target_platform=body.target_platform.strip() or None,
                             member_usernames=",".join(names), created_by=user.username, is_active=body.is_active)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_json(project, db)


@router.put("/{project_id}", response_model=None)
def update_project(project_id: int, body: ProjectBody, db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
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


@router.delete("/{project_id}", response_model=None)
def delete_project(project_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    # Take the SQLite write transaction before checking history so a concurrent claim is either observed or excluded.
    db.execute(update(CardKeyProject).where(CardKeyProject.id == project_id).values(is_active=False))
    if db.query(CardKey).filter(CardKey.project_id == project_id, ~_untouched_key()).first() or db.query(CardKeyEmailUsage).filter_by(project_id=project_id).first():
        db.rollback()
        raise HTTPException(409, "项目已有领取或完成记录，请结束项目以保留历史")
    if project.target_platform and db.query(EmailAccount).filter(EmailAccount.claimed_platform == project.target_platform, EmailAccount.claimed_by.isnot(None)).first():
        db.rollback()
        raise HTTPException(409, "该平台有领取中的邮箱，请先完成注册或归还")
    db.query(CardKey).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(CardKeyBatch).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return {"deleted": True}


@router.post("/{project_id}/import", response_model=None)
def import_keys(project_id: int, body: ImportBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not project.is_active:
        raise HTTPException(409, "项目已结束，不能导入")
    values = [line.strip() for line in body.content.splitlines() if line.strip()]
    if not values or len(values) > 10000 or any(len(value) > 8192 for value in values):
        raise HTTPException(422, "每次导入1至10000行，每行最多8192字符")
    batch = CardKeyBatch(project_id=project_id,
                         batch_no=f"B{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}",
                         name=body.batch_name.strip() or "导入批次", remark=body.remark.strip() or None,
                         created_by=user.username)
    if not body.batch_name.strip():
        batch.name = batch.batch_no
    batch.history = [{"action": "import", "username": user.username, "time": _time_json(datetime.utcnow()), "remark": body.remark.strip()}]
    db.add(batch)
    db.flush()
    project.updated_at = datetime.utcnow()
    db.flush()
    added, duplicates = 0, 0
    for value in values:
        fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()
        try:
            with db.begin_nested():
                db.add(CardKey(project_id=project_id, batch_id=batch.id, content=value, fingerprint=fingerprint, created_by=user.username))
                db.flush()
            added += 1
        except IntegrityError:
            duplicates += 1
    db.commit()
    db.refresh(batch)
    return {"added": added, "duplicates": duplicates, "batch": _batch_json(batch, project_id, db)}


@router.get("/{project_id}/batches", response_model=None)
def list_batches(project_id: int, include_archived: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("card_key:view"))) -> list[dict[str, object]]:
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    allowed = _allowed(project, user, db)
    own_keys = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.claimed_by == user.username)
    if not allowed and not own_keys.first():
        raise HTTPException(403, "你不是该项目协助成员")
    rows = []
    visible_keys = db.query(CardKey).filter(CardKey.project_id == project_id) if allowed else own_keys
    owner = None if allowed else user.username
    if visible_keys.filter(CardKey.batch_id.is_(None)).first():
        rows.append(_batch_json(None, project_id, db, owner))
    query = db.query(CardKeyBatch).filter(CardKeyBatch.project_id == project_id)
    if not allowed:
        query = query.filter(CardKeyBatch.id.in_(own_keys.with_entities(CardKey.batch_id)))
    if not include_archived:
        query = query.filter(CardKeyBatch.status != "archived")
    rows.extend(_batch_json(batch, project_id, db, owner) for batch in query.order_by(CardKeyBatch.created_at.desc()).all())
    return rows


@router.put("/{project_id}/batches/{batch_id}", response_model=None)
def update_batch(project_id: int, batch_id: int, body: BatchBody, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    batch = db.query(CardKeyBatch).filter_by(id=batch_id, project_id=project_id).first()
    if not batch:
        raise HTTPException(404, "批次不存在")
    if batch.status == "archived":
        raise HTTPException(409, "已归档批次不能恢复或修改状态")
    if body.name is not None and not body.name.strip():
        raise HTTPException(422, "请填写批次名称")
    values: dict[str, Any] = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        values["name"] = body.name.strip()
    if body.remark is not None:
        values["remark"] = body.remark.strip() or None
    if body.status is not None:
        values["status"] = body.status
        values["pause_reason"] = ((body.pause_reason or "").strip() or None) if body.status == "paused" else None
    elif body.pause_reason is not None:
        values["pause_reason"] = body.pause_reason.strip() or None
    values["history"] = [*(batch.history or []), {"action": "update", "username": user.username,
                         "time": _time_json(values["updated_at"]), **{name: value for name, value in values.items() if name != "updated_at"}}]
    changed = db.execute(update(CardKeyBatch).where(CardKeyBatch.id == batch.id,
                         CardKeyBatch.status != "archived", CardKeyBatch.history == (batch.history or [])).values(**values)).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "批次状态已变化，请刷新后重试")
    db.commit()
    db.refresh(batch)
    return _batch_json(batch, project_id, db)


@router.delete("/{project_id}/batches/{batch_id}", response_model=None)
def delete_batch(project_id: int, batch_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    batch = db.query(CardKeyBatch).filter_by(id=batch_id, project_id=project_id).first()
    if not batch:
        raise HTTPException(404, "批次不存在")
    if batch.status == "archived":
        return {"deleted": False, "archived": True, "id": batch.id}
    # Claim/pause and delete share this write transaction; the status update prevents a new claim crossing this point.
    now = datetime.utcnow()
    changed = db.execute(update(CardKeyBatch).where(CardKeyBatch.id == batch.id,
                         CardKeyBatch.status != "archived", CardKeyBatch.history == (batch.history or [])).values(
        status="archived", pause_reason="批次已归档", updated_at=now,
        history=[*(batch.history or []), {"action": "archive", "username": user.username, "time": _time_json(now)}])).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "批次状态已变化，请刷新后重试")
    keys = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.batch_id == batch_id).all()
    if all((
            key.status == "available" and key.claimed_by is None and key.claimed_at is None and
            key.consumed_at is None and key.pending_owner is None and not (key.history or [])) for key in keys):
        count = len(keys)
        for key in keys:
            db.delete(key)
        db.delete(batch)
        db.commit()
        return {"deleted": True, "deleted_keys": count, "id": batch_id}
    db.commit()
    db.refresh(batch)
    return {"deleted": False, "archived": True, "id": batch.id, "batch": _batch_json(batch, project_id, db)}


@router.get("/{project_id}/keys", response_model=None)
def list_keys(project_id: int, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
              status: str = "", mine: bool = False, keyword: str = "",
              sort_by: str | None = None, sort_order: Literal["asc", "desc"] = "asc",
              table_filters: str | None = None, batch_id: int | None = Query(default=None, ge=0),
              db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    manager = _manager(user, db)
    query = db.query(CardKey).filter(CardKey.project_id == project_id)
    if batch_id is not None:
        query = query.filter(CardKey.batch_id == batch_id if batch_id else CardKey.batch_id.is_(None))
    if not manager or mine:
        query = query.filter(CardKey.claimed_by == user.username)
    if not _allowed(project, user, db) and not db.query(CardKey.id).filter(
        CardKey.project_id == project_id, CardKey.claimed_by == user.username).first():
        raise HTTPException(403, "你不是该项目协助成员")
    if status:
        if status not in ("available", "claimed", "consumed", "invalid"):
            raise HTTPException(422, "无效状态")
        query = query.filter(CardKey.status == status)
    fields = {"id": "number", "content": "text", "status": "enum", "claimed_by": "text",
              "claimed_at": "date", "consumed_at": "date", "remark": "text"}
    filters = parse_table_filters(table_filters, fields)
    if not keyword.strip() and sort_by != "content" and "content" not in filters:
        query = apply_table_query(query, model_table_fields(CardKey, names=[name for name in fields if name != "content"]),
                                  sort_by, sort_order, filters, stable_column=CardKey.id,
                                  default_sort=(CardKey.id, "desc"))
        return {"items": [_key_json(key) for key in query.offset((page - 1) * page_size).limit(page_size)],
                "total": query.count()}
    # ponytail: encrypted content must be decrypted before matching; add a search index if projects become large.
    rows = [_key_json(key) for key in query.order_by(CardKey.id.desc()).all()]
    if keyword.strip():
        needle = keyword.strip().casefold()
        rows = [key for key in rows if needle in (str(key.get("content") or "")).casefold()]
    rows = apply_table_rows(rows, fields, sort_by, sort_order, filters)
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": len(rows)}


@router.post("/{project_id}/claim", response_model=None)
def claim_key(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view")),
              batch_id: int | None = None) -> dict[str, object]:
    project = db.get(CardKeyProject, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if not _allowed(project, user, db):
        raise HTTPException(403, "你不是该项目协助成员")
    if batch_id is not None and batch_id < 0:
        raise HTTPException(422, "无效批次")
    pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
    if pending:
        pending_batch_id = pending.batch_id or 0
        requested_batch_id = batch_id if batch_id is not None else pending_batch_id
        if requested_batch_id != pending_batch_id:
            raise HTTPException(409, f"你已有批次 {pending_batch_id or '历史未分批'} 的待处理卡密，请先完成或归还")
        return _key_json(pending)
    if not project.is_active:
        raise HTTPException(409, "项目已结束，不能领取")
    if batch_id:
        batch = db.query(CardKeyBatch).filter_by(id=batch_id, project_id=project_id).first()
        if not batch:
            raise HTTPException(404, "批次不存在")
        if batch.status != "active":
            raise HTTPException(409, "该批次已暂停或归档，请选择其他批次")
    key_query = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.status == "available")
    if batch_id is not None:
        key_query = key_query.filter(CardKey.batch_id == batch_id if batch_id else CardKey.batch_id.is_(None))
    else:
        key_query = key_query.filter(_active_batch())
    key = key_query.order_by(CardKey.id).first()
    if not key:
        raise HTTPException(409, "卡密已领完")
    now = datetime.utcnow()
    try:
        predicate = [CardKey.id == key.id, CardKey.status == "available", CardKey.history == (key.history or []),
                     exists().where(CardKeyProject.id == project_id, CardKeyProject.is_active.is_(True))]
        if key.batch_id is not None:
            predicate.append(exists().where(CardKeyBatch.id == key.batch_id, CardKeyBatch.status == "active"))
        changed = db.execute(update(CardKey).where(and_(*predicate)).values(
            status="claimed", claimed_by=user.username, pending_owner=user.username, claimed_at=now,
            history=_history(key, "claim", user.username, now))).rowcount
        if changed != 1:
            db.rollback()
            pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
            if pending:
                if batch_id is not None and batch_id != (pending.batch_id or 0):
                    raise HTTPException(409, "你已有其他批次的待处理卡密，请先完成或归还")
                return _key_json(pending)
            raise HTTPException(409, "卡密已被其他成员领取，请重试")
        db.commit()
    except IntegrityError:
        db.rollback()
        pending = db.query(CardKey).filter(CardKey.project_id == project_id, CardKey.pending_owner == user.username).first()
        if pending:
            if batch_id is not None and batch_id != (pending.batch_id or 0):
                raise HTTPException(409, "你已有其他批次的待处理卡密，请先完成或归还")
            return _key_json(pending)
        raise HTTPException(409, "领取冲突，请重试")
    db.refresh(key)
    return _key_json(key)


@router.post("/{project_id}/keys/{key_id}/consume", response_model=None)
def consume_key(project_id: int, key_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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


@router.post("/{project_id}/keys/{key_id}/release", response_model=None)
def release_key(project_id: int, key_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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


@router.post("/{project_id}/keys/{key_id}/invalid", response_model=None)
def mark_key_invalid(project_id: int, key_id: int, body: InvalidKeyBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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


@router.put("/{project_id}/keys/{key_id}/remark", response_model=None)
def update_key_remark(project_id: int, key_id: int, body: KeyRemarkBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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


@router.get("/{project_id}/work-report", response_model=None)
def work_report(project_id: int, date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:manage"))) -> dict[str, object]:
    if not db.get(CardKeyProject, project_id):
        raise HTTPException(404, "项目不存在")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    start = datetime.combine(date_from, datetime.min.time()) - timedelta(hours=8) if date_from else None
    end = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1, hours=-8) if date_to else None
    items: list[WorkReportItem] = []
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
    totals: dict[str | None, WorkReportTotals] = {}
    for item in items:
        values = totals.setdefault(item["username"], {"username": item["username"], "keys_consumed": 0, "emails_completed": 0})
        values["keys_consumed" if item["kind"] == "卡密消耗" else "emails_completed"] += 1
    return {"members": sorted(totals.values(), key=lambda row: row["username"] or ""), "items": sorted(items, key=lambda row: row["time"] or "", reverse=True)}


@router.get("/{project_id}/email", response_model=None)
def get_claimed_email(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object] | None:
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    email = db.query(EmailAccount).filter(EmailAccount.claimed_by == user.username,
                                           EmailAccount.claimed_platform == project.target_platform).first()
    return _email_json(email) if email else None


@router.post("/{project_id}/email/claim", response_model=None)
def claim_email(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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
        EmailAccount.gmail_check_status == "正常",
        or_(EmailAccount.platform_tags.is_(None), ~EmailAccount.platform_tags.icontains(json.dumps(platform, ensure_ascii=False), autoescape=True)),
    ).order_by(EmailAccount.id).all()
    for candidate in candidates:
        try:
            changed = db.execute(update(EmailAccount).where(
                EmailAccount.id == candidate.id, EmailAccount.management_status == "闲置",
                EmailAccount.claimed_by.is_(None), EmailAccount.gmail_check_status == "正常",
                EmailAccount.platform_tags == candidate.platform_tags,
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


@router.get("/{project_id}/email/totp", response_model=None)
def get_claimed_email_totp(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> JSONResponse:
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
    return JSONResponse({"code": code, "remaining": remaining}, headers={"Cache-Control": "no-store"})


@router.post("/{project_id}/email/release", response_model=None)
def release_email(project_id: int, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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


class EmailFailureBody(BaseModel):
    remark: str = Field(min_length=1, max_length=2000)


@router.post("/{project_id}/email/fail", response_model=None)
def fail_email(project_id: int, body: EmailFailureBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
    project = db.get(CardKeyProject, project_id)
    if not project or not _allowed(project, user, db):
        raise HTTPException(404, "项目不存在或无权访问")
    platform = (project.target_platform or "").strip()
    if not platform:
        raise HTTPException(422, "请先为项目设置目标平台")
    email = db.query(EmailAccount).filter(
        EmailAccount.claimed_by == user.username,
        EmailAccount.claimed_platform == platform,
    ).first()
    if not email:
        raise HTTPException(404, "没有找到你领取的邮箱")
    remark = body.remark.strip()
    if not remark:
        raise HTTPException(422, "请填写失败原因")
    changed = db.execute(update(EmailAccount).where(
        EmailAccount.id == email.id,
        EmailAccount.management_status == email.management_status,
        EmailAccount.claimed_by == user.username,
        EmailAccount.claimed_platform == platform,
        EmailAccount.claimed_at == email.claimed_at,
        EmailAccount.platform_tags == email.platform_tags,
    ).values(
        management_status="废弃", remark=remark, claimed_by=None, claimed_at=None,
        claimed_platform=None, operator=user.username,
    )).rowcount
    if changed != 1:
        db.rollback()
        raise HTTPException(409, "邮箱领取状态已变化，请刷新后重试")
    db.commit()
    db.refresh(email)
    return {"failed": True, "email_id": email.id, "management_status": email.management_status, "remark": email.remark}


class CompleteEmailBody(BaseModel):
    platform: str = Field(min_length=1, max_length=100)
    account: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=255)
    totp_secret: str | None = Field(default=None, max_length=255)


@router.post("/{project_id}/email/complete", response_model=None)
def complete_email(project_id: int, body: CompleteEmailBody, db: Session = Depends(get_db), user: User = Depends(require_permission("card_key:view"))) -> dict[str, object]:
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
    tags = cast(list[str], _email_json(email)["platform_tags"])
    if platform.casefold() not in {tag.casefold() for tag in tags}:
        tags.append(platform)
    changed = db.execute(update(EmailAccount).where(
        EmailAccount.id == email.id, EmailAccount.claimed_by == user.username,
        EmailAccount.claimed_platform == platform, EmailAccount.claimed_at == email.claimed_at,
        EmailAccount.platform_tags == email.platform_tags,
    ).values(platform_tags=json.dumps(tags, ensure_ascii=False), claimed_by=None, claimed_at=None, claimed_platform=None, operator=user.username)).rowcount
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
