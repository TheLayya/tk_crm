from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, BigInteger,
    DateTime, ForeignKey, Text, Enum as SAEnum,
    Numeric, Date, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.services.encryption_service import EncryptedType


class OpAccount(Base):
    __tablename__ = "op_accounts"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    platform = Column(SAEnum("tiktok", "youtube", "instagram", "facebook", name="op_platform_enum"), nullable=False)

    # 手动维护字段
    account = Column(String(255), nullable=False, index=True)
    password = Column(EncryptedType, nullable=True)
    totp_secret = Column(EncryptedType, nullable=True)
    email = Column(String(255), nullable=True)
    email_password = Column(EncryptedType, nullable=True)
    email_login_url = Column(String(512), nullable=True)
    phone = Column(String(50), nullable=True)
    phone_manage_url = Column(String(512), nullable=True)
    country = Column(String(100), nullable=True)
    source = Column(String(50), nullable=True)
    tags = Column(Text, nullable=True)  # JSON 数组
    remark = Column(Text, nullable=True)
    status = Column(
        SAEnum("正常", "自用", "封禁", "已售", name="op_status_enum"),
        default="正常",
        nullable=False,
        index=True,
    )
    registrant = Column(String(255), nullable=True)
    operator = Column(String(255), nullable=True)

    # TikTok 专属字段
    tiktok_mid_video = Column(Boolean, nullable=True)
    tiktok_showcase = Column(Boolean, nullable=True)
    tiktok_phone_live = Column(Boolean, nullable=True)
    tiktok_partner_live = Column(Boolean, nullable=True)

    # 采购字段
    purchase_channel = Column(String(255), nullable=True)
    purchase_price = Column(Numeric(10, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)

    # 出售字段
    sale_customer = Column(String(255), nullable=True)
    sale_price = Column(Numeric(10, 2), nullable=True)
    sale_date = Column(Date, nullable=True)
    sellers = Column(Text, nullable=True)  # JSON 数组，存储出售人 username 列表

    # 采集字段
    platform_user_id = Column(String(255), nullable=True)
    platform_sec_uid = Column(String(512), nullable=True)
    nickname = Column(String(255), nullable=True)
    avatar_url = Column(String(1024), nullable=True)
    follower_count = Column(BigInteger, nullable=True)
    following_count = Column(BigInteger, nullable=True)
    like_count = Column(BigInteger, nullable=True)
    video_count = Column(BigInteger, nullable=True)
    account_created_at = Column(DateTime, nullable=True)
    last_collected_at = Column(DateTime, nullable=True)
    collect_status = Column(
        SAEnum("pending", "success", "failed", "unsupported", name="op_collect_status_enum"),
        default="pending",
        nullable=False,
    )
    collect_error = Column(Text, nullable=True)

    # 系统字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "account", name="uq_op_account_platform_account"),
    )

    project = relationship("Project", backref="op_accounts")


class OpCollectTask(Base):
    __tablename__ = "op_collect_tasks"

    id = Column(String(36), primary_key=True)  # UUID
    status = Column(
        SAEnum("running", "completed", "failed", name="op_task_status_enum"),
        default="running",
        nullable=False,
    )
    total = Column(Integer, default=0, nullable=False)
    completed = Column(Integer, default=0, nullable=False)
    success = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class OpAuditLog(Base):
    __tablename__ = "op_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    op_account_id = Column(Integer, ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # create / update / delete
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
