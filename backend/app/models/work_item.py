from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, JSON

from app.core.database import Base
from app.services.encryption_service import EncryptedType


class WorkItemCategorySettings(Base):
    __tablename__ = "work_item_category_settings"

    id = Column(Integer, primary_key=True)
    categories = Column(JSON, nullable=False)


class WorkItem(Base):
    __tablename__ = "work_items"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False, index=True)
    category = Column(String(32), nullable=False, default="其他", index=True)
    content = Column(EncryptedType(), nullable=False, default="")
    reminder_users = Column(Text, nullable=True)
    remind_at = Column(DateTime, nullable=True, index=True)
    is_done = Column(Boolean, nullable=False, default=False, index=True)
    created_by = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
