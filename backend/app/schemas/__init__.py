from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    BatchAccountCreate,
    BatchAccountResult,
    BatchAccountResultItem,
    BatchActionRequest,
)
from app.schemas.history import HistoryResponse, TrendResponse
from app.schemas.proxy import ProxyCreate, ProxyUpdate, ProxyResponse, ProxyTestResult
from app.schemas.video import VideoResponse, VideoStatsResponse
from app.schemas.settings import SettingsUpdate, SettingsResponse

__all__ = [
    # project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    # account
    "AccountCreate",
    "AccountUpdate",
    "AccountResponse",
    "BatchAccountCreate",
    "BatchAccountResult",
    "BatchAccountResultItem",
    "BatchActionRequest",
    # history
    "HistoryResponse",
    "TrendResponse",
    # proxy
    "ProxyCreate",
    "ProxyUpdate",
    "ProxyResponse",
    "ProxyTestResult",
    # video
    "VideoResponse",
    "VideoStatsResponse",
    # settings
    "SettingsUpdate",
    "SettingsResponse",
]
