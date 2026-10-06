from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.work_item import WorkItem, WorkItemCategorySettings
from app.models.team import User
from app.services.auth_service import require_permission

router = APIRouter(prefix="/work-items", tags=["Work items"])
WORK_ITEM_CATEGORIES = ("采购渠道", "VPS续费", "未结款项", "团队任务", "账号/节点", "其他")


class WorkItemBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "其他"
    content: str = ""
    reminder_users: list[str] = Field(default_factory=list)
    remind_at: Optional[datetime] = None
    is_done: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写标题")
        return value.strip()

    @field_validator("remind_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        if value and value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

def _categories(db: Session) -> list[str]:
    settings = db.get(WorkItemCategorySettings, 1)
    return settings.categories if settings else list(WORK_ITEM_CATEGORIES)


def _validate_category(category: str, db: Session) -> None:
    if category not in _categories(db):
        raise HTTPException(status_code=422, detail="备忘大类无效")


class CategoryBody(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=30)


def _reminder_users(body: WorkItemBody, db: Session) -> str:
    names = list(dict.fromkeys(body.reminder_users))
    if "__all__" in names:
        return ",__all__,"
    active = {user.username for user in db.query(User).filter(User.is_active.is_(True)).all()}
    if any(name not in active for name in names):
        raise HTTPException(status_code=400, detail="提醒成员不存在或已停用")
    return "," + ",".join(names) + "," if names else ""


@router.get("/members", response_model=None)
def reminder_members(db: Session = Depends(get_db), _: User = Depends(require_permission("work_item:view"))) -> list[dict[str, object]]:
    return [{"username": user.username, "real_name": user.real_name}
            for user in db.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()]


@router.get("/categories", response_model=None)
def work_item_categories(db: Session = Depends(get_db), _: User = Depends(require_permission("work_item:view"))) -> list[str]:
    return _categories(db)


@router.put("/categories", response_model=None)
def update_categories(body: CategoryBody, db: Session = Depends(get_db), _: User = Depends(require_permission("settings:edit"))) -> list[str]:
    names = [name.strip() for name in body.categories]
    if any(not name or len(name) > 32 for name in names) or len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="大类不能重复或为空，每项最多32字")
    if "其他" not in names:
        raise HTTPException(status_code=422, detail="请保留“其他”大类")
    used = {category for (category,) in db.query(WorkItem.category).distinct().all()}
    if used - set(names):
        raise HTTPException(status_code=400, detail="已有备忘使用的大类不能删除，请先调整对应备忘")
    settings = db.get(WorkItemCategorySettings, 1)
    if settings is None:
        settings = WorkItemCategorySettings(id=1, categories=names)
        db.add(settings)
    else:
        settings.categories = names
    db.commit()
    return names


def _serialize(item: WorkItem) -> dict[str, object]:
    reminder_users = [x for x in (item.reminder_users or "").split(",") if x]
    return {
        "id": item.id,
        "title": item.title,
        "category": item.category or "其他",
        "content": item.content or "",
        "reminder_users": reminder_users,
        "reminder_all": "__all__" in reminder_users,
        "remind_at": item.remind_at.isoformat() + "Z" if item.remind_at else None,
        "is_done": item.is_done,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("", response_model=None)
def list_work_items(
    keyword: Optional[str] = Query(None),
    status: str = Query("pending"),
    category: Optional[str] = Query(None),
    mine: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_item:view")),
) -> dict[str, object]:
    query = db.query(WorkItem)
    if status == "pending":
        query = query.filter(WorkItem.is_done.is_(False))
    elif status == "done":
        query = query.filter(WorkItem.is_done.is_(True))
    if category:
        query = query.filter(WorkItem.category == category)
    if mine:
        query = query.filter(or_(
            WorkItem.reminder_users.contains(",__all__,", autoescape=True),
            WorkItem.reminder_users.contains(f",{user.username},", autoescape=True),
        ))
    items = query.order_by(WorkItem.is_done.asc(), WorkItem.remind_at.asc().nullslast(), WorkItem.updated_at.desc()).all()
    if keyword:
        needle = keyword.casefold()
        items = [item for item in items if needle in item.title.casefold() or needle in (item.content or "").casefold()]
    return {"items": [_serialize(item) for item in items], "total": len(items)}


@router.get("/summary", response_model=None)
def work_item_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_item:view")),
) -> dict[str, object]:
    now = datetime.utcnow()
    soon = now + timedelta(days=7)
    assigned = db.query(WorkItem).filter(
        WorkItem.is_done.is_(False), or_(
            WorkItem.reminder_users.contains(",__all__,", autoescape=True),
            WorkItem.reminder_users.contains(f",{user.username},", autoescape=True),
        )
    ).all()
    return {
        "overdue": sum(1 for item in assigned if item.remind_at and item.remind_at < now),
        "due_soon": sum(1 for item in assigned if item.remind_at and now <= item.remind_at <= soon),
        "pending": len(assigned),
        "due": [{"id": item.id, "title": item.title} for item in assigned if item.remind_at and item.remind_at <= now],
    }


@router.post("", status_code=201, response_model=None)
def create_work_item(
    body: WorkItemBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_item:manage")),
) -> dict[str, object]:
    _validate_category(body.category, db)
    item = WorkItem(
        title=body.title.strip(),
        category=body.category,
        content=body.content,
        reminder_users=_reminder_users(body, db),
        remind_at=body.remind_at,
        is_done=body.is_done,
        created_by=user.username,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.put("/{item_id}", response_model=None)
def update_work_item(
    item_id: int,
    body: WorkItemBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("work_item:manage")),
) -> dict[str, object]:
    item = db.query(WorkItem).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="备忘不存在")
    _validate_category(body.category, db)
    item.title = body.title.strip()
    item.category = body.category
    item.content = body.content
    item.reminder_users = _reminder_users(body, db)
    item.remind_at = body.remind_at
    item.is_done = body.is_done
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.delete("/{item_id}", status_code=204, response_model=None)
def delete_work_item(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("work_item:manage")),
) -> None:
    item = db.query(WorkItem).filter(WorkItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="备忘不存在")
    db.delete(item)
    db.commit()
