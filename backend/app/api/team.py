"""
Team management API: departments, members, roles, and logs.
"""
import hashlib
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.team import LoginLog, OperationLog, OperationToken, User
from app.services.auth_service import require_permission
from app.services.table_query_service import apply_table_query, model_table_fields
from app.services.team_service import (
    DepartmentNode,
    create_dept,
    create_member,
    create_role,
    delete_dept,
    delete_member,
    delete_role,
    disable_member,
    get_dept_tree,
    list_members,
    list_roles,
    reset_password,
    unlock_member,
    update_dept,
    update_member,
    update_role,
)

router = APIRouter(prefix="/team", tags=["Team"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _validate_operation_token(token: Optional[str], db: Session) -> None:
    """Validate X-Operation-Token header; raise 401 if invalid or expired."""
    if not token:
        raise HTTPException(status_code=401, detail="缺少操作令牌 X-Operation-Token")

    token_hash = _sha256(token)
    op_token = (
        db.query(OperationToken)
        .filter(OperationToken.token_hash == token_hash)
        .first()
    )

    if op_token is None or op_token.is_used or op_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="操作令牌无效或已过期，请重新进行二次确认")

    # Mark as used immediately
    op_token.is_used = True
    db.add(op_token)
    db.commit()


# ── Request schemas ───────────────────────────────────────────────────────────

class DeptCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None


class DeptUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None


class MemberCreate(BaseModel):
    username: str
    password: str
    real_name: Optional[str] = None
    department_id: Optional[int] = None
    is_active: bool = True
    role_ids: list[int] = []


class MemberUpdate(BaseModel):
    real_name: Optional[str] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None
    role_ids: Optional[list[int]] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: list[str] = []
    data_scope: str = "all"  # all / self


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[str]] = None
    data_scope: Optional[str] = None


# ── Department routes ─────────────────────────────────────────────────────────

@router.get("/dept/tree", response_model=None)
def get_department_tree(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:dept:view")),
) -> list[DepartmentNode]:
    return get_dept_tree(db)


@router.post("/dept", status_code=201, response_model=None)
def create_department(
    body: DeptCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:dept:create")),
) -> dict[str, object]:
    dept = create_dept(body.model_dump(), db)
    return {"id": dept.id, "name": dept.name, "parent_id": dept.parent_id}


@router.put("/dept/{id}", response_model=None)
def update_department(
    id: int,
    body: DeptUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:dept:edit")),
) -> dict[str, object]:
    dept = update_dept(id, body.model_dump(exclude_none=True), db)
    return {"id": dept.id, "name": dept.name, "parent_id": dept.parent_id}


@router.delete("/dept/{id}", status_code=204, response_model=None)
def delete_department(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:dept:delete")),
) -> None:
    delete_dept(id, db)


# ── Member routes ─────────────────────────────────────────────────────────────

@router.get("/member", response_model=None)
def get_members(
    dept_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    table_filters: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:view")),
) -> dict[str, object]:
    return list_members(dept_id, username, is_active, page, size, db, sort_by, sort_order, table_filters)


@router.post("/member", status_code=201, response_model=None)
def create_member_route(
    body: MemberCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:create")),
) -> dict[str, object]:
    user = create_member(body.model_dump(), db)
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "department_id": user.department_id,
        "is_active": user.is_active,
    }


@router.put("/member/{id}", response_model=None)
def update_member_route(
    id: int,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:edit")),
) -> dict[str, object]:
    user = update_member(id, body.model_dump(exclude_none=True), db)
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "department_id": user.department_id,
        "is_active": user.is_active,
    }


@router.delete("/member/{id}", status_code=204, response_model=None)
def delete_member_route(
    id: int,
    x_operation_token: Optional[str] = Header(None, alias="X-Operation-Token"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:delete")),
) -> None:
    _validate_operation_token(x_operation_token, db)
    delete_member(id, db)


@router.post("/member/{id}/reset-password", status_code=204, response_model=None)
def reset_member_password(
    id: int,
    body: ResetPasswordRequest,
    x_operation_token: Optional[str] = Header(None, alias="X-Operation-Token"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:reset_password")),
) -> None:
    _validate_operation_token(x_operation_token, db)
    reset_password(id, body.new_password, db)


@router.post("/member/{id}/unlock", status_code=204, response_model=None)
def unlock_member_route(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:member:edit")),
) -> None:
    """解除账号登录锁定（清除15分钟内的失败记录）"""
    unlock_member(id, db)


# ── Role routes ───────────────────────────────────────────────────────────────

@router.get("/role", response_model=None)
def get_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:role:view")),
) -> list[dict[str, object]]:
    return list_roles(db)


@router.post("/role", status_code=201, response_model=None)
def create_role_route(
    body: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:role:create")),
) -> dict[str, object]:
    role = create_role(body.model_dump(), db)
    return {"id": role.id, "name": role.name, "description": role.description}


@router.put("/role/{id}", response_model=None)
def update_role_route(
    id: int,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:role:edit")),
) -> dict[str, object]:
    role = update_role(id, body.model_dump(exclude_none=True), db)
    return {"id": role.id, "name": role.name, "description": role.description}


@router.delete("/role/{id}", status_code=204, response_model=None)
def delete_role_route(
    id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:role:delete")),
) -> None:
    delete_role(id, db)


# ── Log routes ────────────────────────────────────────────────────────────────

@router.get("/log/login", response_model=None)
def get_login_logs(
    username: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    table_filters: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:log:view")),
) -> dict[str, object]:
    query = db.query(LoginLog)

    if username:
        query = query.filter(LoginLog.username.ilike(f"%{username}%"))
    if start_time:
        query = query.filter(LoginLog.created_at >= start_time)
    if end_time:
        query = query.filter(LoginLog.created_at <= end_time)
    if result:
        query = query.filter(LoginLog.result == result)
    query = apply_table_query(query, model_table_fields(LoginLog), sort_by, sort_order, table_filters,
                              stable_column=LoginLog.id, default_sort=(LoginLog.created_at, "desc"))
    total = query.count()
    logs = query.offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": log.id,
                "username": log.username,
                "ip_address": log.ip_address,
                "result": log.result,
                "reason": log.reason,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }


@router.get("/log/operation", response_model=None)
def get_operation_logs(
    username: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    table_filters: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("team:log:view")),
) -> dict[str, object]:
    query = db.query(OperationLog)

    if username:
        query = query.filter(OperationLog.username.ilike(f"%{username}%"))
    if start_time:
        query = query.filter(OperationLog.created_at >= start_time)
    if end_time:
        query = query.filter(OperationLog.created_at <= end_time)
    if module:
        query = query.filter(OperationLog.module == module)
    if action:
        query = query.filter(OperationLog.action == action)
    query = apply_table_query(query, model_table_fields(OperationLog), sort_by, sort_order, table_filters,
                              stable_column=OperationLog.id, default_sort=(OperationLog.created_at, "desc"))
    total = query.count()
    logs = query.offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": log.id,
                "username": log.username,
                "ip_address": log.ip_address,
                "module": log.module,
                "action": log.action,
                "summary": log.summary,
                "result": log.result,
                "error": log.error,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }
