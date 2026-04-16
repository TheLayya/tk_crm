from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


# ---------------------------------------------------------------------------
# 创建请求
# ---------------------------------------------------------------------------

class ProxyNodeCreate(BaseModel):
    # 原始节点信息（ip + port 必填）
    ip: str
    port: int = Field(..., ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: Literal["socks5", "http", "https"] = "socks5"

    # 中转节点信息（全部可选）
    relay_ip: Optional[str] = None
    relay_port: Optional[int] = Field(None, ge=1, le=65535)
    relay_protocol: Optional[Literal["socks5", "http", "https"]] = None

    # 采购信息（全部可选）
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    purchase_channel: Optional[str] = None
    expire_date: Optional[date] = None

    # 出售信息（全部可选）
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sellers: Optional[List[str]] = None  # 出售人 username 列表

    # 状态字段
    status: Literal["idle", "active", "sold", "disabled"] = "idle"

    # 备注
    remark: Optional[str] = None


# ---------------------------------------------------------------------------
# 更新请求（所有字段可选，PATCH 语义）
# ---------------------------------------------------------------------------

class ProxyNodeUpdate(BaseModel):
    # 原始节点信息
    ip: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: Optional[Literal["socks5", "http", "https"]] = None

    # 中转节点信息
    relay_ip: Optional[str] = None
    relay_port: Optional[int] = Field(None, ge=1, le=65535)
    relay_protocol: Optional[Literal["socks5", "http", "https"]] = None

    # 采购信息
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    purchase_channel: Optional[str] = None
    expire_date: Optional[date] = None

    # 出售信息
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sellers: Optional[List[str]] = None  # 出售人 username 列表

    # 状态字段
    status: Optional[Literal["idle", "active", "sold", "disabled"]] = None

    # 测试字段（允许手动覆写）
    last_test_at: Optional[datetime] = None
    last_test_result: Optional[Literal["success", "failed"]] = None
    last_test_latency: Optional[int] = None

    # 备注
    remark: Optional[str] = None

    def get_update_data(self) -> dict:
        """返回仅包含显式设置字段的字典（PATCH 语义）。"""
        return self.model_dump(exclude_unset=True)


# ---------------------------------------------------------------------------
# 响应体
# ---------------------------------------------------------------------------

class ProxyNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    # 原始节点信息
    ip: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None  # 返回原始值，前端负责掩码显示
    protocol: str

    # 中转节点信息
    relay_ip: Optional[str] = None
    relay_port: Optional[int] = None
    relay_protocol: Optional[str] = None

    # 采购信息
    purchase_date: Optional[date] = None
    purchase_price: Optional[Decimal] = None
    purchase_channel: Optional[str] = None
    expire_date: Optional[date] = None

    # 出售信息
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sellers: List[str] = []  # 出售人 username 列表

    # 状态字段
    status: str

    # 测试字段
    last_test_at: Optional[datetime] = None
    last_test_result: Optional[str] = None
    last_test_latency: Optional[int] = None

    # 备注
    remark: Optional[str] = None

    # 系统字段
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 筛选参数
# ---------------------------------------------------------------------------

class ProxyNodeFilter(BaseModel):
    status: Optional[List[str]] = None           # 多值筛选
    protocol: Optional[List[str]] = None         # 多值筛选
    purchase_channel: Optional[str] = None       # 模糊搜索
    sale_customer: Optional[str] = None          # 模糊搜索
    expire_date_from: Optional[date] = None      # 到期日期范围起
    expire_date_to: Optional[date] = None        # 到期日期范围止


# ---------------------------------------------------------------------------
# 导入结果
# ---------------------------------------------------------------------------

class ProxyNodeImportResult(BaseModel):
    success_count: int
    fail_count: int
    errors: List[str] = []


# ---------------------------------------------------------------------------
# 连通性测试结果
# ---------------------------------------------------------------------------

class ProxyNodeTestResult(BaseModel):
    node_id: int
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None


class ProxyNodeBatchTestResult(BaseModel):
    success_count: int
    fail_count: int
    results: List[ProxyNodeTestResult] = []


# ---------------------------------------------------------------------------
# 统计结果
# ---------------------------------------------------------------------------

class ChannelStats(BaseModel):
    channel: str
    count: int
    total_cost: Decimal


class ProxyNodeStats(BaseModel):
    total: int
    by_status: Dict[str, int]        # {"idle": N, "active": N, "sold": N, "disabled": N}
    total_purchase_cost: Decimal
    total_sale_revenue: Decimal
    net_profit: Decimal
    by_channel: List[ChannelStats] = []
