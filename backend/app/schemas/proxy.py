from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ProxyCreate(BaseModel):
    proxy_type: str = "socks5"  # "socks5", "http", "https"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: bool = True
    is_global: bool = False
    name: Optional[str] = None  # 可选，如果不提供则自动生成


class ProxyBatchCreate(BaseModel):
    """批量创建代理，支持 ip:port:username:password 格式"""
    proxies_text: str  # 多行文本，每行一个代理
    proxy_type: str = "socks5"  # 默认类型
    is_active: bool = True


class ProxyUpdate(BaseModel):
    proxy_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_global: Optional[bool] = None
    name: Optional[str] = None


class ProxyResponse(BaseModel):
    id: int
    name: str
    proxy_type: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None  # 返回密码，前端负责脱敏显示
    is_active: bool
    is_global: bool
    success_count: int
    fail_count: int
    last_test_at: Optional[datetime] = None
    last_test_result: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProxyTestResult(BaseModel):
    success: bool
    response_time: Optional[float] = None
    error: Optional[str] = None


class ProxyBatchResult(BaseModel):
    """批量创建结果"""
    success_count: int
    fail_count: int
    errors: List[str] = []
    created_proxies: List[ProxyResponse] = []
