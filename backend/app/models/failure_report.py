from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.services.encryption_service import EncryptedType


class EncryptedScreenshots(EncryptedType):
    impl = Text
    cache_ok = True


class FailureReport(Base):
    __tablename__ = "failure_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("card_key_projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("card_keys.id", ondelete="RESTRICT"), nullable=True, index=True)
    email_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("email_accounts.id", ondelete="RESTRICT"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    batch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_metadata: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    screenshots: Mapped[str] = mapped_column(EncryptedScreenshots(), nullable=False, deferred=True)

    __table_args__ = (
        CheckConstraint("(key_id IS NOT NULL AND email_id IS NULL AND kind = 'card_key') OR (key_id IS NULL AND email_id IS NOT NULL AND kind = 'email')", name="ck_failure_report_parent"),
        CheckConstraint("image_count >= 0 AND image_count <= 5", name="ck_failure_report_image_count"),
    )
