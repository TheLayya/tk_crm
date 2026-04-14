import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.monitor import Project, MonitorAccount, ProjectMember
from app.schemas.project import ProjectCreate, ProjectUpdate

logger = logging.getLogger(__name__)


def get_visible_project_ids(db: Session, username: str, data_scope: str, dept_usernames: List[str] = None) -> Optional[List[int]]:
    """
    返回该用户可见的项目 ID 列表。
    - all: 返回 None（不过滤，全部可见）
    - dept: 本部门所有人创建的项目
    - self: 自己创建的 + 被邀请协作的
    """
    if data_scope == "all":
        return None
    if data_scope == "dept":
        names = dept_usernames or [username]
        rows = db.query(Project.id).filter(Project.created_by.in_(names)).all()
        return [r.id for r in rows]
    # self
    owned = db.query(Project.id).filter(Project.created_by == username).all()
    invited = db.query(ProjectMember.project_id).filter(ProjectMember.username == username).all()
    ids = {r.id for r in owned} | {r.project_id for r in invited}
    return list(ids)


def get_projects(db: Session, scope_username: Optional[str] = None, allowed_ids: Optional[List[int]] = None) -> List[Project]:
    """获取项目列表，附带 account_count。"""
    query = db.query(Project).order_by(Project.created_at.desc())
    if allowed_ids is not None:
        query = query.filter(Project.id.in_(allowed_ids))
    projects = query.all()
    # 批量统计每个项目的账号数
    counts = (
        db.query(MonitorAccount.project_id, func.count(MonitorAccount.id).label("cnt"))
        .group_by(MonitorAccount.project_id)
        .all()
    )
    count_map = {row.project_id: row.cnt for row in counts}
    for project in projects:
        project.account_count = count_map.get(project.id, 0)
    return projects


def get_project(db: Session, project_id: int) -> Optional[Project]:
    """获取单个项目（附带 account_count）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        project.account_count = (
            db.query(func.count(MonitorAccount.id))
            .filter(MonitorAccount.project_id == project_id)
            .scalar()
        )
    return project


def create_project(db: Session, data: ProjectCreate, created_by: Optional[str] = None) -> Project:
    """创建项目，名称唯一校验。"""
    existing = db.query(Project).filter(Project.name == data.name).first()
    if existing:
        raise ValueError(f"Project name '{data.name}' already exists")

    project = Project(
        name=data.name,
        description=data.description,
        created_by=created_by,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    project.account_count = 0
    return project


def update_project(
    db: Session, project_id: int, data: ProjectUpdate
) -> Optional[Project]:
    """更新项目字段。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None

    update_data = data.model_dump(exclude_unset=True)

    # 名称唯一校验（排除自身）
    if "name" in update_data and update_data["name"] != project.name:
        conflict = (
            db.query(Project)
            .filter(Project.name == update_data["name"], Project.id != project_id)
            .first()
        )
        if conflict:
            raise ValueError(f"Project name '{update_data['name']}' already exists")

    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    project.account_count = (
        db.query(func.count(MonitorAccount.id))
        .filter(MonitorAccount.project_id == project_id)
        .scalar()
    )
    return project


def delete_project(db: Session, project_id: int) -> None:
    """删除项目。若项目下仍有账号则拒绝删除，抛出 ValueError。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise LookupError(f"Project {project_id} not found")

    account_count = (
        db.query(func.count(MonitorAccount.id))
        .filter(MonitorAccount.project_id == project_id)
        .scalar()
    )
    if account_count > 0:
        raise ValueError(
            f"Cannot delete project with {account_count} account(s). "
            "Please remove or move all accounts first."
        )

    db.delete(project)
    db.commit()


# ---------------------------------------------------------------------------
# 协作成员管理
# ---------------------------------------------------------------------------

def get_project_members(db: Session, project_id: int) -> List[str]:
    """返回项目协作成员用户名列表（不含创建人）。"""
    rows = db.query(ProjectMember.username).filter(ProjectMember.project_id == project_id).all()
    return [r.username for r in rows]


def set_project_members(db: Session, project_id: int, usernames: List[str]) -> None:
    """全量替换项目协作成员。"""
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
    for username in set(usernames):
        db.add(ProjectMember(project_id=project_id, username=username))
    db.commit()
