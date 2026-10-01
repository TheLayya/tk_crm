from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON

from app.core.database import Base
from app.services.encryption_service import EncryptedType


class CardKeyProject(Base):
    __tablename__ = "card_key_projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    member_usernames = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CardKey(Base):
    __tablename__ = "card_keys"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("card_key_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(EncryptedType(), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    pending_owner = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="available", index=True)
    claimed_by = Column(String(64), nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    history = Column(JSON, nullable=False, default=list)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_card_key_fingerprint"),
        UniqueConstraint("project_id", "pending_owner", name="uq_card_key_pending_owner"),
    )
