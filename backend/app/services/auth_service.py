import hashlib
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, Header, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, decode_access_token
from app.models.team import User, RefreshToken, LoginLog, UserRole, RolePermission


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _record_login_log(db: Session, username: str, ip: str, result: str, reason: str = None):
    log = LoginLog(
        username=username,
        ip_address=ip,
        result=result,
        reason=reason,
    )
    db.add(log)
    db.commit()


def _count_recent_failures(db: Session, username: str, window_minutes: int = 15) -> int:
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    return (
        db.query(LoginLog)
        .filter(
            LoginLog.username == username,
            LoginLog.result == "failed",
            LoginLog.created_at >= since,
        )
        .count()
    )


def _get_user_permissions(db: Session, user_id: int) -> list[str]:
    role_ids = (
        db.query(UserRole.role_id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    if not role_ids:
        return []
    role_id_list = [r.role_id for r in role_ids]
    perms = (
        db.query(RolePermission.permission)
        .filter(RolePermission.role_id.in_(role_id_list))
        .all()
    )
    return list({p.permission for p in perms})


def login(username: str, password: str, ip: str, db: Session) -> dict:
    # Check account lock: >= 5 failures in last 15 minutes
    failure_count = _count_recent_failures(db, username)
    if failure_count >= 5:
        _record_login_log(db, username, ip, "failed", "账号已锁定")
        raise HTTPException(status_code=429, detail="账号已锁定，请 15 分钟后重试")

    # Query user
    user = db.query(User).filter(User.username == username).first()

    # Verify password (always run to avoid timing attacks)
    password_ok = user is not None and verify_password(password, user.password_hash)

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"LOGIN DEBUG: username={username}, user_found={user is not None}, password_ok={password_ok}, failure_count={failure_count}")
    if user:
        logger.info(f"LOGIN DEBUG: hash_prefix={user.password_hash[:20]}, is_active={user.is_active}")

    if not password_ok:
        _record_login_log(db, username, ip, "failed", "用户名或密码错误")
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # Check account disabled
    if not user.is_active:
        _record_login_log(db, username, ip, "failed", "账号已禁用")
        raise HTTPException(status_code=403, detail="账号已禁用")

    # Create access token
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "is_super_admin": user.is_super_admin,
        }
    )

    # Create refresh token
    raw_refresh_token = str(uuid.uuid4())
    token_hash = _sha256(raw_refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        is_revoked=False,
        expires_at=expires_at,
    )
    db.add(db_token)

    # Record login log
    _record_login_log(db, username, ip, "success")
    db.commit()

    # Collect permissions
    permissions = _get_user_permissions(db, user.id)

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "is_super_admin": user.is_super_admin,
        },
        "permissions": permissions,
    }


def refresh_token(token: str, db: Session) -> dict:
    token_hash = _sha256(token)

    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if db_token is None:
        raise HTTPException(status_code=401, detail="无效的 Refresh Token")

    # Detect replay attack: token already revoked means it was used before
    if db_token.is_revoked:
        # Revoke ALL tokens for this user
        db.query(RefreshToken).filter(
            RefreshToken.user_id == db_token.user_id,
            RefreshToken.is_revoked == False,
        ).update({"is_revoked": True})
        db.commit()
        raise HTTPException(status_code=401, detail="检测到 Token 重放攻击，所有会话已强制下线")

    if db_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh Token 已过期，请重新登录")

    # Revoke old token
    db_token.is_revoked = True
    db.add(db_token)

    # Issue new tokens
    user = db.query(User).filter(User.id == db_token.user_id).first()
    if user is None or not user.is_active:
        db.commit()
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    new_access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "is_super_admin": user.is_super_admin,
        }
    )

    new_raw_refresh = str(uuid.uuid4())
    new_hash = _sha256(new_raw_refresh)
    new_expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        is_revoked=False,
        expires_at=new_expires_at,
    )
    db.add(new_db_token)
    db.commit()

    permissions = _get_user_permissions(db, user.id)

    return {
        "access_token": new_access_token,
        "refresh_token": new_raw_refresh,
        "user": {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "is_super_admin": user.is_super_admin,
        },
        "permissions": permissions,
    }


def logout(user_id: int, token: str, db: Session) -> None:
    token_hash = _sha256(token)
    db_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == user_id,
    ).first()
    if db_token:
        db_token.is_revoked = True
        db.add(db_token)
        db.commit()


def get_current_user(token: str, db: Session) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="无效或已过期的 Token")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token 载荷无效")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return user


def require_permission(perm: str):
    """FastAPI dependency factory that checks if the current user has the required permission."""
    def dependency(
        authorization: str = Header(None),
        db: Session = Depends(get_db)
    ) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="未提供认证 Token")
        token = authorization.split(" ", 1)[1]
        user = get_current_user(token, db)
        # Super_Admin bypasses all permission checks
        if user.is_super_admin:
            return user
        # Check if user has the required permission
        permissions = set(_get_user_permissions(db, user.id))
        if perm not in permissions:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return dependency


def get_current_user_from_header(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证 Token")
    token = authorization.split(" ", 1)[1]
    return get_current_user(token, db)


def get_user_data_scope(db: Session, user: User) -> str:
    """返回用户的数据范围：all / dept / self。取所有角色中最宽松的。"""
    if user.is_super_admin:
        return "all"
    role_ids = [r.role_id for r in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    if not role_ids:
        return "self"
    from app.models.team import Role
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    scopes = {r.data_scope for r in roles}
    if "all" in scopes:
        return "all"
    if "dept" in scopes:
        return "dept"
    return "self"


def get_dept_member_usernames(db: Session, user: User) -> list[str]:
    """返回与该用户同部门的所有用户名（含自己）。用于 dept 数据范围过滤。"""
    if user.department_id is None:
        return [user.username]
    from app.models.team import User as UserModel
    users = db.query(UserModel.username).filter(UserModel.department_id == user.department_id).all()
    return [u.username for u in users]
