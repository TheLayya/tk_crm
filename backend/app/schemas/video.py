from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class VideoResponse(BaseModel):
    id: int
    account_id: int
    video_id: str
    title: Optional[str] = None
    cover_url: Optional[str] = None
    play_count: int
    like_count: int
    comment_count: int
    share_count: int
    published_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VideoStatsResponse(BaseModel):
    id: int
    video_id: int
    play_count: int
    like_count: int
    comment_count: int
    share_count: int
    recorded_at: datetime

    class Config:
        from_attributes = True
