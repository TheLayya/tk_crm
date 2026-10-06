from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    Integer, String, Text, Date, DateTime, Numeric,
    Enum as SAEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProxyNode(Base):
    __tablename__ = "proxy_nodes"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 原始节点信息（ip + port 必填）
    ip: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protocol: Mapped[str] = mapped_column(
        SAEnum("socks5", "http", "https", name="proxy_node_protocol_enum"),
        nullable=False,
        default="socks5",
    )

    # 中转节点信息（全部可选）
    relay_ip: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relay_protocol: Mapped[str | None] = mapped_column(
        SAEnum("socks5", "http", "https", name="proxy_node_relay_protocol_enum"),
        nullable=True,
    )

    # 采购信息（全部可选）
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_channel: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # 出售信息（全部可选）
    sale_customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sellers: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 数组，存储出售人 username 列表

    # 状态字段
    status: Mapped[str] = mapped_column(
        SAEnum("idle", "active", "sold", "disabled", name="proxy_node_status_enum"),
        nullable=False,
        default="idle",
        index=True,
    )

    # 测试字段
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_result: Mapped[str | None] = mapped_column(
        SAEnum("success", "failed", name="proxy_node_test_result_enum"),
        nullable=True,
    )
    last_test_latency: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 毫秒

    # 备注
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 系统字段
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
