from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime
from sqlalchemy import (
    Integer, String, Boolean, BigInteger,
    DateTime, ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.video import Video


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 创建人用户名
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    accounts: Mapped[list[MonitorAccount]] = relationship("MonitorAccount", back_populates="project", cascade="all, delete-orphan")
    members: Mapped[list[ProjectMember]] = relationship("ProjectMember", cascade="all, delete-orphan")


class ProjectMember(Base):
    """项目协作成员——创建人手动邀请，被邀请者可查看该项目及其账号。"""
    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), primary_key=True)


class MonitorProxy(Base):
    __tablename__ = "monitor_proxies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    proxy_type: Mapped[str] = mapped_column(SAEnum("socks5", "http", "https", name="proxy_type_enum"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_result: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "success" / "failed"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    accounts: Mapped[list[MonitorAccount]] = relationship("MonitorAccount", back_populates="proxy")


class MonitorAccount(Base):
    __tablename__ = "monitor_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tiktok_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sec_uid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monitor_interval: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)  # seconds
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 默认开启代理
    proxy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("monitor_proxies.id", ondelete="SET NULL"), nullable=True)
    enable_video_monitoring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 默认开启视频监控
    follower_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    following_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    video_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 账号注册时间
    region: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 地区/国家
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project: Mapped[Project] = relationship("Project", back_populates="accounts")
    proxy: Mapped[MonitorProxy | None] = relationship("MonitorProxy", back_populates="accounts")
    history: Mapped[list[MonitorHistory]] = relationship("MonitorHistory", back_populates="account", cascade="all, delete-orphan")
    videos: Mapped[list[Video]] = relationship("Video", back_populates="account", cascade="all, delete-orphan")


def latest_check_summary(history: MonitorHistory | None) -> dict[str, str | None]:
    if history is None:
        return {"latest_check_status": "pending", "latest_check_error": None}
    error = history.error_message
    state = history.check_status
    if error and error.startswith("ACCOUNT_NOT_FOUND:"):
        state = "not_found"
    elif error and "VERIFICATION_REQUIRED:" in error:
        state = "verification_required"
    elif error and "VIDEO_COLLECTION_FAILED:" in error and state == "success":
        state = "partial"
    return {"latest_check_status": state, "latest_check_error": error}


class MonitorHistory(Base):
    __tablename__ = "monitor_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    follower_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    following_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    video_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    check_status: Mapped[str] = mapped_column(SAEnum("success", "failed", name="check_status_enum"), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    account: Mapped[MonitorAccount] = relationship("MonitorAccount", back_populates="history")


class MonitorSettings(Base):
    __tablename__ = "monitor_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    default_interval: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)  # seconds
    max_concurrent_checks: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    request_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)  # seconds
    default_video_count: Mapped[int] = mapped_column(Integer, default=20, nullable=False)  # 默认监控视频数量
    site_name: Mapped[str] = mapped_column(String(100), default="TikTok Monitor", nullable=False)  # 网站名称
    logo_image: Mapped[str | None] = mapped_column(Text, nullable=True)  # Logo图片（base64编码）
    login_screen_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Backup & notification fields
    backup_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backup_interval_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_bot_token: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    telegram_chat_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    smtp_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_username: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_password: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    smtp_sender: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    email_recipient: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
