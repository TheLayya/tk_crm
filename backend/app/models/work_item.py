from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.services.encryption_service import EncryptedType


class WorkItemCategorySettings(Base):
    __tablename__ = "work_item_category_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="其他", index=True)
    content: Mapped[str] = mapped_column(EncryptedType(), nullable=False, default="")
    reminder_users: Mapped[str | None] = mapped_column(Text, nullable=True)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
