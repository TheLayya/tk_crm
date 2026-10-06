"""终端资产（设备）模型

Device：设备（手机/电脑），多台设备可以共享代理节点。
DeviceLog：设备操作历史轨迹（old→new 变更），软删除设备后保留。
"""
from datetime import datetime
from sqlalchemy import JSON
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pc / phone
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proxy_nodes.id"), nullable=True
    )
    node_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class DeviceLog(Base):
    __tablename__ = "device_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 无 ondelete 级联：设备软删除后历史轨迹仍可追溯
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 不可变归属
    username: Mapped[str] = mapped_column(String(64), nullable=False)  # 展示冗余
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # CREATE / UPDATE / DELETE
    changes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON 字符串：{"field": {"old": ..., "new": ...}}
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
