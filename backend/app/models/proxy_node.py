from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Numeric,
    Enum as SAEnum, Index
)
from app.core.database import Base


class ProxyNode(Base):
    __tablename__ = "proxy_nodes"

    # 主键
    id = Column(Integer, primary_key=True, index=True)

    # 原始节点信息（ip + port 必填）
    ip = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    protocol = Column(
        SAEnum("socks5", "http", "https", name="proxy_node_protocol_enum"),
        nullable=False,
        default="socks5",
    )

    # 中转节点信息（全部可选）
    relay_ip = Column(String(255), nullable=True)
    relay_port = Column(Integer, nullable=True)
    relay_protocol = Column(
        SAEnum("socks5", "http", "https", name="proxy_node_relay_protocol_enum"),
        nullable=True,
    )

    # 采购信息（全部可选）
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(10, 2), nullable=True)
    purchase_channel = Column(String(255), nullable=True, index=True)
    expire_date = Column(Date, nullable=True, index=True)

    # 出售信息（全部可选）
    sale_customer = Column(String(255), nullable=True)
    sale_price = Column(Numeric(10, 2), nullable=True)
    sellers = Column(Text, nullable=True)  # JSON 数组，存储出售人 username 列表

    # 状态字段
    status = Column(
        SAEnum("idle", "active", "sold", "disabled", name="proxy_node_status_enum"),
        nullable=False,
        default="idle",
        index=True,
    )

    # 测试字段
    last_test_at = Column(DateTime, nullable=True)
    last_test_result = Column(
        SAEnum("success", "failed", name="proxy_node_test_result_enum"),
        nullable=True,
    )
    last_test_latency = Column(Integer, nullable=True)  # 毫秒

    # 备注
    remark = Column(Text, nullable=True)

    # 系统字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
