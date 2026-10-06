from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Integer, String, Boolean, BigInteger,
    DateTime, ForeignKey, Text, Enum as SAEnum,
    Numeric, Date, UniqueConstraint, Index, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.services.encryption_service import EncryptedType

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.monitor import Project
    from app.models.proxy_node import ProxyNode
    from app.models.video import OpAccountVideo


class OpAccount(Base):
    __tablename__ = "op_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    # 一个手机终端可以同时绑定多个运营账号；唯一性由账号与终端的关联业务处理。
    device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proxy_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(SAEnum("tiktok", "youtube", "instagram", "facebook", "gmail", name="op_platform_enum"), nullable=False)

    # 手动维护字段
    account: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password: Mapped[str | None] = mapped_column(EncryptedType, nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(EncryptedType, nullable=True)
    recovery_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_password: Mapped[str | None] = mapped_column(EncryptedType, nullable=True)
    email_login_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_manage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("正常", "自用", "封禁", "已售", name="op_status_enum"),
        default="正常",
        nullable=False,
        index=True,
    )
    registrant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # TikTok 专属字段
    tiktok_mid_video: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiktok_showcase: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiktok_phone_live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiktok_partner_live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # 采购字段
    purchase_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 出售字段
    sale_customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sellers: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组，存储出售人 username 列表

    # 采集字段
    platform_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform_sec_uid: Mapped[str | None] = mapped_column(String(512), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    follower_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    previous_follower_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    following_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    account_created_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collect_status: Mapped[str] = mapped_column(
        SAEnum("pending", "success", "failed", "unsupported", name="op_collect_status_enum"),
        default="pending",
        nullable=False,
    )
    collect_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    gmail_check_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    gmail_check_raw_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gmail_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 系统字段
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "account", name="uq_op_account_platform_account"),
    )

    project: Mapped[Project | None] = relationship("Project", backref="op_accounts")
    videos: Mapped[list[OpAccountVideo]] = relationship("OpAccountVideo", back_populates="account", cascade="all, delete-orphan")


class OpCollectTask(Base):
    __tablename__ = "op_collect_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    status: Mapped[str] = mapped_column(
        SAEnum("running", "completed", "failed", name="op_task_status_enum"),
        default="running",
        nullable=False,
    )
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class OpAuditLog(Base):
    __tablename__ = "op_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    op_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # create / update / delete
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EmailAccount(Base):
    __tablename__ = "email_accounts"
    __table_args__ = (Index("uq_email_pending_platform", "claimed_by", "claimed_platform", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password: Mapped[str | None] = mapped_column(EncryptedType, nullable=True)
    recovery_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(EncryptedType, nullable=True)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    account_created_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    platform_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proxy_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sellers: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_status: Mapped[str] = mapped_column(
        SAEnum("闲置", "使用中", "锁定", "废弃", "已出售", name="email_management_status_enum"),
        default="闲置",
        nullable=False,
        index=True,
    )
    gmail_check_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    gmail_check_raw_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gmail_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    registrant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EmailAccountRelation(Base):
    __tablename__ = "email_account_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    op_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unbound_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("uq_email_current_relation", "email_id", "op_account_id", unique=True,
              sqlite_where=text("unbound_at IS NULL")),
    )

    email_account: Mapped[EmailAccount] = relationship("EmailAccount", backref="relations")
    op_account: Mapped[OpAccount] = relationship("OpAccount", backref="email_relations")


class EmailAssetRelation(Base):
    __tablename__ = "email_asset_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proxy_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    bound_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unbound_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    email_account: Mapped[EmailAccount] = relationship("EmailAccount", backref="asset_relations")
    device: Mapped[Device | None] = relationship("Device")
    node: Mapped[ProxyNode | None] = relationship("ProxyNode")
