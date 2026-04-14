"""
Project CRUD API endpoints
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services import project_service
from app.services.auth_service import (
    require_permission,
    get_current_user_from_header,
    get_user_data_scope,
    get_dept_member_usernames,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _resolve_allowed_ids(db, current_user):
    """根据当前用户的数据范围，返回可见项目 ID 列表（None 表示全部可见）。"""
    data_scope = get_user_data_scope(db, current_user)
    dept_usernames = get_dept_member_usernames(db, current_user) if data_scope == "dept" else None
    return project_service.get_visible_project_ids(
        db, current_user.username, data_scope, dept_usernames
    ), data_scope


@router.get("", response_model=List[ProjectResponse])
def get_projects(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    allowed_ids, _ = _resolve_allowed_ids(db, current_user)
    return project_service.get_projects(db, allowed_ids=allowed_ids)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    allowed_ids, _ = _resolve_allowed_ids(db, current_user)
    if allowed_ids is not None and project_id not in allowed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    try:
        return project_service.create_project(db, data, created_by=current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    # 只有创建人或 all 范围的用户才能修改
    _, data_scope = _resolve_allowed_ids(db, current_user)
    if data_scope == "self" and project.created_by != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有项目创建人才能修改")
    try:
        return project_service.update_project(db, project_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _, data_scope = _resolve_allowed_ids(db, current_user)
    if data_scope == "self" and project.created_by != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有项目创建人才能删除")
    try:
        project_service.delete_project(db, project_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return None


# ---------------------------------------------------------------------------
# 协作成员管理
# ---------------------------------------------------------------------------

class ProjectMembersUpdate(BaseModel):
    usernames: List[str]


@router.get("/{project_id}/members", response_model=List[str])
def get_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    allowed_ids, _ = _resolve_allowed_ids(db, current_user)
    if allowed_ids is not None and project_id not in allowed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
    return project_service.get_project_members(db, project_id)


@router.put("/{project_id}/members", response_model=List[str])
def set_project_members(
    project_id: int,
    data: ProjectMembersUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("monitor:view")),
):
    """设置项目协作成员（全量替换）。只有创建人或 all 范围用户可操作。"""
    project = project_service.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _, data_scope = _resolve_allowed_ids(db, current_user)
    if data_scope == "self" and project.created_by != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有项目创建人才能管理协作成员")
    project_service.set_project_members(db, project_id, data.usernames)
    return project_service.get_project_members(db, project_id)
