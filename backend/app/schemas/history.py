from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class HistoryResponse(BaseModel):
    id: int
    account_id: int
    follower_count: int
    following_count: int
    like_count: int
    video_count: int
    check_status: str
    error_message: Optional[str] = None
    checked_at: datetime

    class Config:
        from_attributes = True


class TrendDataPoint(BaseModel):
    checked_at: datetime
    follower_count: int
    following_count: int
    like_count: int
    video_count: int
    followers_change: int
    likes_change: int


class TrendResponse(BaseModel):
    data_points: List[TrendDataPoint]
