from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, field_validator


class AccountCreate(BaseModel):
    project_id: int
    username: str
    nickname: Optional[str] = None
    tiktok_id: Optional[str] = None
    sec_uid: Optional[str] = None
    monitor_interval: Optional[int] = None  # None means use default from MonitorSettings
    use_proxy: bool = True  # 默认开启代理
    proxy_id: Optional[int] = None
    enable_video_monitoring: bool = True  # 默认开启视频监控
    is_active: bool = True


class AccountUpdate(BaseModel):
    nickname: Optional[str] = None
    tiktok_id: Optional[str] = None
    sec_uid: Optional[str] = None
    is_active: Optional[bool] = None
    monitor_interval: Optional[int] = None
    use_proxy: Optional[bool] = None
    proxy_id: Optional[int] = None
    enable_video_monitoring: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None  # Added for frontend display
    username: str
    nickname: Optional[str] = None
    tiktok_id: Optional[str] = None
    sec_uid: Optional[str] = None  # Added missing field
    is_active: bool
    monitor_interval: int
    use_proxy: bool
    proxy_id: Optional[int] = None
    enable_video_monitoring: bool
    follower_count: int
    following_count: int
    like_count: int
    video_count: int
    last_checked_at: Optional[datetime] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    account_created_at: Optional[datetime] = None
    region: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchAccountCreate(BaseModel):
    project_id: int
    usernames: str  # 多行文本，每行一个用户名
    monitor_interval: Optional[int] = None  # None means use default from MonitorSettings


class BatchAccountResultItem(BaseModel):
    username: str
    status: str  # "success", "duplicate", "failed"
    reason: Optional[str] = None


class BatchAccountResult(BaseModel):
    total: int
    success: int
    duplicates: int
    failed: int
    results: List[BatchAccountResultItem]


class BatchActionRequest(BaseModel):
    account_ids: List[int]
    action: str  # "enable", "disable", "delete", "move"
    target_project_id: Optional[int] = None


class AccountListResponse(BaseModel):
    items: List[AccountResponse]
    total: int
