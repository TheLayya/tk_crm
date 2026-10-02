from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, PositiveInt, StringConstraints, field_validator


class OpAccountCreate(BaseModel):
    # 必填
    platform: Literal["tiktok", "youtube", "instagram", "facebook", "gmail"]
    account: str
    device_id: Optional[int] = None
    node_id: Optional[int] = None

    # 手动维护字段（可选）
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    recovery_email: Optional[str] = None
    email: Optional[str] = None
    email_password: Optional[str] = None
    email_login_url: Optional[str] = None
    phone: Optional[str] = None
    phone_manage_url: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None  # JSON 数组字符串
    remark: Optional[str] = None
    status: Optional[str] = "正常"
    registrant: Optional[str] = None
    operator: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = Field(default=None, ge=1, le=9999)

    # TikTok 专属
    tiktok_mid_video: Optional[bool] = None
    tiktok_showcase: Optional[bool] = None
    tiktok_phone_live: Optional[bool] = None
    tiktok_partner_live: Optional[bool] = None

    # 采购字段
    purchase_channel: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    purchase_date: Optional[date] = None

    # 出售字段
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: Optional[List[str]] = None  # 出售人 username 列表

    class Config:
        from_attributes = True


class OpAccountUpdate(BaseModel):
    platform: Optional[Literal["tiktok", "youtube", "instagram", "facebook", "gmail"]] = None
    account: Optional[str] = None
    device_id: Optional[int] = None
    node_id: Optional[int] = None

    password: Optional[str] = None
    totp_secret: Optional[str] = None
    recovery_email: Optional[str] = None
    email: Optional[str] = None
    email_password: Optional[str] = None
    email_login_url: Optional[str] = None
    phone: Optional[str] = None
    phone_manage_url: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
    remark: Optional[str] = None
    status: Optional[str] = None
    registrant: Optional[str] = None
    operator: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = Field(default=None, ge=1, le=9999)

    tiktok_mid_video: Optional[bool] = None
    tiktok_showcase: Optional[bool] = None
    tiktok_phone_live: Optional[bool] = None
    tiktok_partner_live: Optional[bool] = None

    purchase_channel: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    purchase_date: Optional[date] = None

    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: Optional[List[str]] = None  # 出售人 username 列表

    class Config:
        from_attributes = True


class OpAccountResponse(BaseModel):
    id: int
    platform: str

    account: str
    device_id: Optional[int] = None
    node_id: Optional[int] = None
    device_name: Optional[str] = None
    node_ip: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    recovery_email: Optional[str] = None
    email: Optional[str] = None
    email_password: Optional[str] = None
    email_login_url: Optional[str] = None
    phone: Optional[str] = None
    phone_manage_url: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
    remark: Optional[str] = None
    status: str
    registrant: Optional[str] = None
    operator: Optional[str] = None

    tiktok_mid_video: Optional[bool] = None
    tiktok_showcase: Optional[bool] = None
    tiktok_phone_live: Optional[bool] = None
    tiktok_partner_live: Optional[bool] = None

    purchase_channel: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    purchase_date: Optional[date] = None

    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: List[str] = []  # 出售人 username 列表

    @field_validator('sellers', mode='before')
    @classmethod
    def normalize_sellers(cls, value):
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return value or []

    platform_user_id: Optional[str] = None
    platform_sec_uid: Optional[str] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    follower_count: Optional[int] = None
    monitor_account_id: Optional[int] = None
    followers_change: Optional[int] = None
    yesterday_video_count: Optional[int] = None
    yesterday_video_plays: Optional[List[int]] = None
    following_count: Optional[int] = None
    like_count: Optional[int] = None
    video_count: Optional[int] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = Field(default=None, ge=1, le=9999)
    last_collected_at: Optional[datetime] = None
    collect_status: str
    collect_error: Optional[str] = None
    gmail_check_status: Optional[str] = None
    gmail_check_raw_status: Optional[str] = None
    gmail_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailAccountCreate(BaseModel):
    email: str
    password: Optional[str] = None
    recovery_email: Optional[str] = None
    totp_secret: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = Field(default=None, ge=1, le=9999)
    country: Optional[str] = None
    platform_tags: Optional[List[str]] = None
    device_id: Optional[int] = None
    node_id: Optional[int] = None
    purchase_channel: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    purchase_price: Decimal = Field(ge=0)
    purchase_date: Optional[date] = None
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: Optional[List[str]] = None
    management_status: Optional[str] = "闲置"
    registrant: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None


class EmailAccountUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    recovery_email: Optional[str] = None
    totp_secret: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = Field(default=None, ge=1, le=9999)
    country: Optional[str] = None
    platform_tags: Optional[List[str]] = None
    device_id: Optional[int] = None
    node_id: Optional[int] = None
    purchase_channel: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    purchase_date: Optional[date] = None
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: Optional[List[str]] = None
    management_status: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None


class EmailAccountResponse(BaseModel):
    id: int
    email: str
    password: Optional[str] = None
    recovery_email: Optional[str] = None
    totp_secret: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_created_year: Optional[int] = None
    country: Optional[str] = None
    platform_tags: List[str] = []
    platform_registrants: dict[str, str] = {}
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    claimed_platform: Optional[str] = None
    device_id: Optional[int] = None
    node_id: Optional[int] = None
    device_name: Optional[str] = None
    node_ip: Optional[str] = None
    purchase_channel: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    purchase_date: Optional[date] = None
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: List[str] = []
    management_status: str
    gmail_check_status: Optional[str] = None
    gmail_check_raw_status: Optional[str] = None
    gmail_checked_at: Optional[datetime] = None
    registrant: Optional[str] = None
    operator: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    current_relation_count: int = 0

    class Config:
        from_attributes = True

    @field_validator("platform_tags", mode="before")
    @classmethod
    def normalize_platform_tags(cls, value):
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return value or []

    @field_validator("sellers", mode="before")
    @classmethod
    def normalize_sellers(cls, value):
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return value or []


class EmailImportRequest(BaseModel):
    text: str
    purchase_channel: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    purchase_price: Decimal = Field(ge=0)


class EmailRelationRequest(BaseModel):
    op_account_id: PositiveInt
    remark: Optional[str] = None


class EmailAssetRelationRequest(BaseModel):
    device_id: Optional[PositiveInt] = None
    node_id: Optional[PositiveInt] = None
    remark: Optional[str] = None

    @field_validator("node_id")
    @classmethod
    def require_one_asset(cls, value, info):
        if value is None and info.data.get("device_id") is None:
            raise ValueError("请选择终端或节点")
        return value


class OpImportResult(BaseModel):
    total: int
    success: int
    duplicates: int
    failed: int
    rows: List[Dict[str, Any]] = []
    task_id: Optional[str] = None


class CollectTaskResponse(BaseModel):
    task_id: str
    status: str
    total: int
    completed: int
    success: int
    failed: int

    class Config:
        from_attributes = True


class BatchStatusUpdate(BaseModel):
    ids: List[int]
    status: str
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_date: Optional[date] = None
    sellers: Optional[List[str]] = None  # 出售人 username 列表


class GmailCheckRequest(BaseModel):
    account_ids: List[PositiveInt] = Field(min_length=1, max_length=50)
    consent: Literal[True]


class BatchAssignOperator(BaseModel):
    ids: List[PositiveInt] = Field(min_length=1)
    operator: str = Field(min_length=1, max_length=64)

    @field_validator('operator')
    @classmethod
    def validate_operator(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('请选择成员')
        return value


class AuditLogResponse(BaseModel):
    summary: Optional[str] = None
    details: List[str] = []
    id: int
    action: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    operator: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
