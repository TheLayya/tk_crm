"""终端资产（设备）相关 Schema"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    device_type: str = Field(..., pattern=r"^(pc|phone)$")
    # 非超管无需传（服务层强制为当前用户）；超管必填（服务层校验）
    owner_id: Optional[int] = None
    node_id: Optional[int] = None
    node_ids: list[int] = Field(default_factory=list)
    remark: Optional[str] = None


class DeviceUpdate(BaseModel):
    """PATCH 语义：仅显式设置的字段参与更新。node_id 显式 None = 解绑。

    extra="forbid"：未知/保留字段（如 is_deleted）在 schema 层直接 422。
    """
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    device_type: Optional[str] = Field(None, pattern=r"^(pc|phone)$")
    owner_id: Optional[int] = None
    node_id: Optional[int] = None
    node_ids: Optional[list[int]] = None
    remark: Optional[str] = None

    def get_update_data(self) -> dict:
        """返回仅包含显式设置字段的字典（PATCH 语义）。"""
        return self.model_dump(exclude_unset=True)


class DeviceAccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    account: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    like_count: Optional[int] = None
    video_count: Optional[int] = None
    followers_change: Optional[int] = None
    yesterday_video_count: Optional[int] = None
    yesterday_video_plays: Optional[list[int]] = None


class DeviceOut(BaseModel):
    """列表/响应：不含任何节点凭据字段。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    device_type: str
    owner_id: int
    owner_name: Optional[str] = None
    node_id: Optional[int] = None
    node_ids: list[int] = Field(default_factory=list)
    node_ip: Optional[str] = None
    node_count: int = 0
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    # 一个手机可绑定多个运营账号；account_id/account_name 保留首个账号兼容旧客户端。
    accounts: list["DeviceAccountSummary"] = Field(default_factory=list)
    remark: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NodeSummary(BaseModel):
    """设备详情中的节点摘要——显式白名单，extra=forbid 保证任何凭据字段不可能被序列化。"""
    model_config = ConfigDict(extra="forbid")

    id: int
    ip: str
    port: int
    protocol: str
    status: str


class DeviceDetail(DeviceOut):
    """详情：附节点摘要（白名单字段，不含凭据）。"""
    node: Optional[NodeSummary] = None
    nodes: list[NodeSummary] = []


class DeviceLogOut(BaseModel):
    id: int
    user_id: int
    username: str
    action: str
    changes: Optional[dict] = None
    summary: Optional[str] = None
    details: list[str] = Field(default_factory=list)
    created_at: datetime
