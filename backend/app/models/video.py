from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("monitor_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(String(255), unique=True, nullable=False, index=True)  # TikTok 原始 video id
    title = Column(Text, nullable=True)
    cover_url = Column(String(1024), nullable=True)
    play_count = Column(BigInteger, default=0, nullable=False)
    like_count = Column(BigInteger, default=0, nullable=False)
    comment_count = Column(BigInteger, default=0, nullable=False)
    share_count = Column(BigInteger, default=0, nullable=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account = relationship("MonitorAccount", back_populates="videos")
    stats = relationship("VideoStats", back_populates="video", cascade="all, delete-orphan")


class VideoStats(Base):
    __tablename__ = "video_stats"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    play_count = Column(BigInteger, default=0, nullable=False)
    like_count = Column(BigInteger, default=0, nullable=False)
    comment_count = Column(BigInteger, default=0, nullable=False)
    share_count = Column(BigInteger, default=0, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    video = relationship("Video", back_populates="stats")


class OpAccountVideo(Base):
    __tablename__ = "op_account_videos"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("op_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(String(255), nullable=False)
    title = Column(Text, nullable=True)
    cover_url = Column(String(1024), nullable=True)
    play_count = Column(BigInteger, default=0, nullable=False)
    like_count = Column(BigInteger, default=0, nullable=False)
    comment_count = Column(BigInteger, default=0, nullable=False)
    share_count = Column(BigInteger, default=0, nullable=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    account = relationship("OpAccount", back_populates="videos")
    __table_args__ = (UniqueConstraint("account_id", "video_id", name="uq_op_account_video"),)
