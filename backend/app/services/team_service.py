from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.team import Department, User, LoginLog


# ── Department Services ──────────────────────────────────────────────────────

def get_dept_tree(db: Session) -> list:
    """Recursively build a tree of all departments."""
    depts = db.query(Department).all()

    # Build a dict keyed by id for quick lookup
    nodes = {
        d.id: {"id": d.id, "name": d.name, "parent_id": d.parent_id, "children": []}
        for d in depts
    }

    roots = []
    for node in nodes.values():
        parent_id = node["parent_id"]
        if parent_id is None:
            roots.append(node)
        elif parent_id in nodes:
            nodes[parent_id]["children"].append(node)

    return roots


def create_dept(data: dict, db: Session) -> Department:
    """Create a new department node."""
    parent_id = data.get("parent_id")
    name = data["name"]

    # Verify parent exists
    if parent_id is not None:
        parent = db.query(Department).filter(Department.id == parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父部门不存在")

    # Check same-level name uniqueness
    existing = (
        db.query(Department)
        .filter(Department.parent_id == parent_id, Department.name == name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="同级部门名称重复")

    dept = Department(name=name, parent_id=parent_id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def update_dept(id: int, data: dict, db: Session) -> Department:
    """Update a department's name and optionally its parent."""
    dept = db.query(Department).filter(Department.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")

    new_parent_id = data.get("parent_id", dept.parent_id)

    # Check for circular reference when parent changes
    if new_parent_id is not None and new_parent_id != dept.parent_id:
        # Walk the ancestor chain of new_parent_id; dept.id must not appear
        ancestor_id = new_parent_id
        visited = set()
        while ancestor_id is not None:
            if ancestor_id == id:
                raise HTTPException(status_code=400, detail="不能将部门移动到其自身的子部门下（循环引用）")
            if ancestor_id in visited:
                break  # Shouldn't happen in a valid tree, but guard against infinite loop
            visited.add(ancestor_id)
            ancestor = db.query(Department).filter(Department.id == ancestor_id).first()
            if not ancestor:
                break
            ancestor_id = ancestor.parent_id

    if "name" in data:
        dept.name = data["name"]

    if "parent_id" in data:
        dept.parent_id = new_parent_id

    db.commit()
    db.refresh(dept)
    return dept


def delete_dept(id: int, db: Session) -> None:
    """Delete a department if it has no children and no members."""
    dept = db.query(Department).filter(Department.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")

    # Check for child departments
    child_count = db.query(Department).filter(Department.parent_id == id).count()
    if child_count > 0:
        raise HTTPException(status_code=400, detail="请先删除或迁移子部门")

    # Check for members
    member_count = db.query(User).filter(User.department_id == id).count()
    if member_count > 0:
        raise HTTPException(status_code=400, detail="请先移除部门成员")

    db.delete(dept)
    db.commit()


# ── Member Services ──────────────────────────────────────────────────────────

from app.models.team import UserRole, Role, RefreshToken
from app.core.security import hash_password


def list_members(
    dept_id: int | None,
    username: str | None,
    is_active: bool | None,
    page: int,
    size: int,
    db: Session,
) -> dict:
    """List members with optional filters and pagination."""
    query = db.query(User)

    if dept_id is not None:
        query = query.filter(User.department_id == dept_id)
    if username is not None:
        query = query.filter(User.username.ilike(f"%{username}%"))
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    users = query.offset((page - 1) * size).limit(size).all()

    items = []
    for u in users:
        roles = (
            db.query(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == u.id)
            .all()
        )
        items.append({
            "id": u.id,
            "username": u.username,
            "real_name": u.real_name,
            "department_id": u.department_id,
            "is_active": u.is_active,
            "is_super_admin": u.is_super_admin,
            "created_at": u.created_at,
            "roles": [{"id": r.id, "name": r.name} for r in roles],
        })

    return {"total": total, "items": items, "page": page, "size": size}


def create_member(data: dict, db: Session) -> User:
    """Create a new member account."""
    username = data["username"]
    password = data["password"]

    # Check username uniqueness
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")

    # Validate password length
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="密码长度不得少于 8 个字符")

    user = User(
        username=username,
        password_hash=hash_password(password),
        real_name=data.get("real_name"),
        department_id=data.get("department_id"),
        is_active=data.get("is_active", True),
    )
    db.add(user)
    db.flush()  # get user.id before assigning roles

    seen_roles = set()
    for role_id in data.get("role_ids", []):
        if role_id not in seen_roles:
            seen_roles.add(role_id)
            db.add(UserRole(user_id=user.id, role_id=role_id))

    db.commit()
    db.refresh(user)
    return user


def update_member(id: int, data: dict, db: Session) -> User:
    """Update a member's profile and roles."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")

    if user.is_super_admin:
        raise HTTPException(status_code=403, detail="超级管理员不可修改")

    if "real_name" in data:
        user.real_name = data["real_name"]
    if "department_id" in data:
        user.department_id = data["department_id"]
    if "is_active" in data:
        user.is_active = data["is_active"]
        if not data["is_active"]:
            # Revoke all refresh tokens when disabling
            db.query(RefreshToken).filter(
                RefreshToken.user_id == id, RefreshToken.is_revoked == False
            ).update({"is_revoked": True})

    if "role_ids" in data:
        db.query(UserRole).filter(UserRole.user_id == id).delete()
        for role_id in data["role_ids"]:
            db.add(UserRole(user_id=id, role_id=role_id))

    db.commit()
    db.refresh(user)
    return user


def delete_member(id: int, db: Session) -> None:
    """Delete a member and revoke all their refresh tokens."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")

    if user.is_super_admin:
        raise HTTPException(status_code=403, detail="超级管理员不可删除或禁用")

    db.query(RefreshToken).filter(
        RefreshToken.user_id == id, RefreshToken.is_revoked == False
    ).update({"is_revoked": True})

    db.delete(user)
    db.commit()


def disable_member(id: int, db: Session) -> User:
    """Disable a member account (idempotent) and revoke their refresh tokens."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")

    if user.is_super_admin:
        raise HTTPException(status_code=403, detail="超级管理员不可删除或禁用")

    if not user.is_active:
        return user  # already disabled – idempotent

    user.is_active = False
    db.query(RefreshToken).filter(
        RefreshToken.user_id == id, RefreshToken.is_revoked == False
    ).update({"is_revoked": True})

    db.commit()
    db.refresh(user)
    return user


def unlock_member(id: int, db: Session) -> None:
    """Clear recent login failures to unlock a locked account."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(minutes=15)
    db.query(LoginLog).filter(
        LoginLog.username == user.username,
        LoginLog.result == "failed",
        LoginLog.created_at >= since,
    ).delete()
    db.commit()


def reset_password(id: int, new_password: str, db: Session) -> None:
    """Reset a member's password and revoke all their refresh tokens."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="成员不存在")

    user.password_hash = hash_password(new_password)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == id, RefreshToken.is_revoked == False
    ).update({"is_revoked": True})

    db.commit()


# ── Role Services ────────────────────────────────────────────────────────────

from app.models.team import RolePermission

PREDEFINED_PERMISSIONS = {
    "monitor:view", "monitor:check", "monitor:proxy",
    "op_account:view", "op_account:create", "op_account:edit", "op_account:delete",
    "op_account:import", "op_account:export", "op_account:collect",
    "settings:view", "settings:edit",
    "team:dept:view", "team:dept:create", "team:dept:edit", "team:dept:delete",
    "team:member:view", "team:member:create", "team:member:edit", "team:member:delete",
    "team:member:reset_password",
    "team:role:view", "team:role:create", "team:role:edit", "team:role:delete",
    "team:log:view",
}


def list_roles(db: Session) -> list:
    """Return all roles with their permissions."""
    roles = db.query(Role).all()
    result = []
    for role in roles:
        perms = (
            db.query(RolePermission.permission)
            .filter(RolePermission.role_id == role.id)
            .all()
        )
        result.append({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "data_scope": role.data_scope,
            "created_at": role.created_at,
            "permissions": [p[0] for p in perms],
        })
    return result


def create_role(data: dict, db: Session) -> Role:
    """Create a new role with permissions."""
    name = data["name"]
    permissions = data.get("permissions", [])

    # Check name uniqueness
    if db.query(Role).filter(Role.name == name).first():
        raise HTTPException(status_code=409, detail="角色名称已存在")

    # Validate permissions
    invalid = set(permissions) - PREDEFINED_PERMISSIONS
    if invalid:
        raise HTTPException(status_code=422, detail=f"包含未知权限标识符: {', '.join(invalid)}")

    role = Role(name=name, description=data.get("description"), data_scope=data.get("data_scope", "all"))
    db.add(role)
    db.flush()

    for perm in permissions:
        db.add(RolePermission(role_id=role.id, permission=perm))

    db.commit()
    db.refresh(role)
    return role


def update_role(id: int, data: dict, db: Session) -> Role:
    """Update a role's name, description, and permissions."""
    role = db.query(Role).filter(Role.id == id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if "permissions" in data:
        invalid = set(data["permissions"]) - PREDEFINED_PERMISSIONS
        if invalid:
            raise HTTPException(status_code=422, detail=f"包含未知权限标识符: {', '.join(invalid)}")

        db.query(RolePermission).filter(RolePermission.role_id == id).delete()
        for perm in data["permissions"]:
            db.add(RolePermission(role_id=id, permission=perm))

    if "name" in data:
        role.name = data["name"]
    if "description" in data:
        role.description = data["description"]
    if "data_scope" in data:
        role.data_scope = data["data_scope"]

    db.commit()
    db.refresh(role)
    return role


def delete_role(id: int, db: Session) -> None:
    """Delete a role if no members are using it."""
    role = db.query(Role).filter(Role.id == id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    user_count = db.query(UserRole).filter(UserRole.role_id == id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该角色已被 {user_count} 名成员使用，请先解除关联",
        )

    db.delete(role)
    db.commit()
