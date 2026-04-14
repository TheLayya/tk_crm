"""
Authentication API endpoints: login, refresh, logout, verify-password
"""
import uuid
import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import verify_password
from app.models.team import OperationToken
from app.services.auth_service import (
    login as auth_login,
    refresh_token as auth_refresh_token,
    logout as auth_logout,
    get_current_user_from_header,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class VerifyPasswordRequest(BaseModel):
    password: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Authenticate user and return access_token, refresh_token, user info and permissions.
    """
    ip = request.client.host if request.client else None
    return auth_login(body.username, body.password, ip, db)


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access_token and refresh_token pair.
    """
    return auth_refresh_token(body.refresh_token, db)


@router.post("/logout")
def logout(
    body: LogoutRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
):
    """
    Revoke the provided refresh token, logging the user out.
    """
    auth_logout(current_user.id, body.refresh_token, db)
    return {"message": "已成功登出"}


@router.post("/verify-password")
def verify_password_and_issue_token(
    body: VerifyPasswordRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
):
    """
    Verify the current user's password and issue a short-lived OperationToken (5 min).
    """
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="密码错误")

    raw_token = str(uuid.uuid4())
    token_hash = _sha256(raw_token)
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    op_token = OperationToken(
        user_id=current_user.id,
        token_hash=token_hash,
        operation="verify",
        is_used=False,
        expires_at=expires_at,
    )
    db.add(op_token)
    db.commit()

    return {"operation_token": raw_token}
