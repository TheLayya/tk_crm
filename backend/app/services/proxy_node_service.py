import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.proxy_node import ProxyNode
from app.services.sale_validation_service import validate_sale_information
from app.schemas.proxy_node import (
    ChannelStats,
    ProxyNodeCreate,
    ProxyNodeFilter,
    ProxyNodeStats,
    ProxyNodeUpdate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sellers JSON helpers
# ---------------------------------------------------------------------------

def _serialize_sellers(sellers: Optional[List[str]]) -> Optional[str]:
    if sellers is None:
        return None
    return json.dumps(sellers, ensure_ascii=False)


def _deserialize_sellers(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _deserialize_node(node: ProxyNode) -> ProxyNode:
    """反序列化节点的 JSON 字段。"""
    if node:
        node.sellers = _deserialize_sellers(node.sellers)
    return node


def _apply_filter(query, filter: ProxyNodeFilter):
    """将 ProxyNodeFilter 中的条件应用到 query，返回新 query。"""
    if filter.status:
        query = query.filter(ProxyNode.status.in_(filter.status))
    if filter.protocol:
        query = query.filter(ProxyNode.protocol.in_(filter.protocol))
    if filter.purchase_channel:
        query = query.filter(
            ProxyNode.purchase_channel.like(f"%{filter.purchase_channel}%")
        )
    if filter.sale_customer:
        query = query.filter(
            ProxyNode.sale_customer.like(f"%{filter.sale_customer}%")
        )
    if filter.expire_date_from:
        query = query.filter(ProxyNode.expire_date >= filter.expire_date_from)
    if filter.expire_date_to:
        query = query.filter(ProxyNode.expire_date <= filter.expire_date_to)
    return query


def get_nodes(
    db: Session,
    filter: ProxyNodeFilter,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[ProxyNode], int]:
    """带筛选的分页查询，返回 (nodes_list, total_count)。"""
    query = db.query(ProxyNode)
    query = _apply_filter(query, filter)

    total = query.count()
    nodes = query.offset(skip).limit(limit).all()
    for node in nodes:
        _deserialize_node(node)

    logger.debug(f"get_nodes: total={total}, skip={skip}, limit={limit}, returned={len(nodes)}")
    return nodes, total


def get_node(db: Session, node_id: int) -> Optional[ProxyNode]:
    """按 ID 查询节点，不存在返回 None。"""
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    return _deserialize_node(node) if node else None


def create_node(db: Session, data: ProxyNodeCreate) -> ProxyNode:
    """创建节点，默认值已在 Schema 中定义。"""
    data_dict = data.model_dump()
    validate_sale_information(data_dict, "sold")
    data_dict['sellers'] = _serialize_sellers(data_dict.get('sellers'))
    node = ProxyNode(**data_dict)
    db.add(node)
    db.commit()
    db.refresh(node)
    logger.info(f"Created proxy node id={node.id} ip={node.ip}:{node.port}")
    return _deserialize_node(node)


def update_node(
    db: Session, node_id: int, data: ProxyNodeUpdate
) -> Optional[ProxyNode]:
    """部分更新节点，自动刷新 updated_at；节点不存在返回 None。"""
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if not node:
        return None

    update_data = data.get_update_data()
    validate_sale_information({**{field: getattr(node, field) for field in ("status", "sale_customer", "sale_price", "sellers")}, **update_data}, "sold")
    if 'sellers' in update_data:
        update_data['sellers'] = _serialize_sellers(update_data['sellers'])
    for field, value in update_data.items():
        setattr(node, field, value)

    node.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(node)
    logger.info(f"Updated proxy node id={node_id}, fields={list(update_data.keys())}")
    return _deserialize_node(node)


def delete_node(db: Session, node_id: int) -> bool:
    """删除节点，成功返回 True，不存在返回 False。"""
    node = get_node(db, node_id)
    if not node:
        return False
    # 清理三方关联后再删除，避免外键关闭/旧库下留下悬空关系。
    from app.models.device import Device
    from app.models.op_account import OpAccount
    for device in db.query(Device).filter(Device.is_deleted == False).all():
        ids = device.node_ids or ([device.node_id] if device.node_id else [])
        if node_id in ids:
            ids = [value for value in ids if value != node_id]
            device.node_ids = ids
            device.node_id = ids[0] if ids else None
    db.query(OpAccount).filter(OpAccount.node_id == node_id).update({OpAccount.node_id: None}, synchronize_session=False)
    db.delete(node)
    db.commit()
    logger.info(f"Deleted proxy node id={node_id}")
    return True


def batch_delete_nodes(db: Session, node_ids: List[int]) -> int:
    """批量删除节点，返回实际删除数量。"""
    from app.models.device import Device
    from app.models.op_account import OpAccount
    nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(node_ids)).all()
    for device in db.query(Device).filter(Device.is_deleted == False).all():
        ids = device.node_ids or ([device.node_id] if device.node_id else [])
        new_ids = [value for value in ids if value not in set(node_ids)]
        if new_ids != ids:
            device.node_ids = new_ids
            device.node_id = new_ids[0] if new_ids else None
    db.query(OpAccount).filter(OpAccount.node_id.in_(node_ids)).update({OpAccount.node_id: None}, synchronize_session=False)
    deleted = len(nodes)
    for node in nodes:
        db.delete(node)
    db.commit()
    logger.info(f"Batch deleted {deleted} proxy nodes, requested ids={node_ids}")
    return deleted


def batch_update_status(db: Session, node_ids: List[int], status: str, sale_customer=None, sale_price=None, sellers=None) -> int:
    """批量修改状态，自动更新 updated_at，返回更新数量。"""
    values = {"status": status, "updated_at": datetime.utcnow()}
    if status == "sold":
        validate_sale_information(dict(status=status, sale_customer=sale_customer, sale_price=sale_price, sellers=sellers), "sold")
        values.update(sale_customer=sale_customer, sale_price=sale_price, sellers=_serialize_sellers(sellers))
    updated = (
        db.query(ProxyNode)
        .filter(ProxyNode.id.in_(node_ids))
        .update(
            values,
            synchronize_session=False,
        )
    )
    db.commit()
    logger.info(f"Batch updated status to '{status}' for {updated} nodes, requested ids={node_ids}")
    return updated


def get_stats(
    db: Session, filter: Optional[ProxyNodeFilter] = None,
    allowed_node_ids: Optional[set[int]] = None,
) -> ProxyNodeStats:
    """
    统计计算。支持 filter 参数（purchase_date 时间范围筛选）。
    空数据集时返回各数值为 0 的结果，不报错。
    """
    query = db.query(ProxyNode)

    # 仅支持 purchase_date 范围筛选（stats 专用）
    if filter is not None:
        if filter.expire_date_from:
            query = query.filter(ProxyNode.expire_date >= filter.expire_date_from)
        if filter.expire_date_to:
            query = query.filter(ProxyNode.expire_date <= filter.expire_date_to)
    if allowed_node_ids is not None:
        query = query.filter(ProxyNode.id.in_(allowed_node_ids))

    nodes: List[ProxyNode] = query.all()

    total = len(nodes)

    # 各状态数量
    by_status: dict = {"idle": 0, "active": 0, "sold": 0, "disabled": 0}
    for node in nodes:
        if node.status in by_status:
            by_status[node.status] += 1

    # 成本与收益
    total_purchase_cost = sum(
        (node.purchase_price for node in nodes if node.purchase_price is not None),
        Decimal("0"),
    )
    total_sale_revenue = sum(
        (node.sale_price for node in nodes if node.sale_price is not None),
        Decimal("0"),
    )
    net_profit = total_sale_revenue - total_purchase_cost

    # 按渠道分组
    channel_map: dict = {}
    for node in nodes:
        channel = node.purchase_channel or ""
        if channel not in channel_map:
            channel_map[channel] = {"count": 0, "total_cost": Decimal("0")}
        channel_map[channel]["count"] += 1
        if node.purchase_price is not None:
            channel_map[channel]["total_cost"] += Decimal(str(node.purchase_price))

    by_channel = [
        ChannelStats(channel=ch, count=v["count"], total_cost=v["total_cost"])
        for ch, v in channel_map.items()
        if ch  # 跳过空渠道
    ]

    logger.debug(f"get_stats: total={total}, by_status={by_status}")

    return ProxyNodeStats(
        total=total,
        by_status=by_status,
        total_purchase_cost=total_purchase_cost,
        total_sale_revenue=total_sale_revenue,
        net_profit=net_profit,
        by_channel=by_channel,
    )


# ---------------------------------------------------------------------------
# 代理 URI 构建（节点二维码，仅超管端点使用）
# ---------------------------------------------------------------------------

URI_PROTOCOLS = ("socks5", "http", "https")


def build_node_uri(node: ProxyNode) -> str:
    """构建代理 URI：中转信息（ip/port/protocol）齐全时用中转，否则直连。

    - 凭据 percent-encode（含 `/` 也转义）；仅当 username 与 password **同时存在**才输出 user:pass@ 段
    - IPv6 主机加方括号（含 zone 标识原样保留在括号内）；主机含空白/斜杠/@ 等非法字符时拒绝
    - 协议白名单校验，非法协议直接拒绝（不静默回退产生误导 URI）
    """
    protocol = (node.relay_protocol or node.protocol or "socks5").lower()
    if protocol not in URI_PROTOCOLS:
        raise ValueError(f"协议无效: {protocol}")

    use_relay = bool(node.relay_ip and node.relay_port and node.relay_protocol)
    # 中转协议同样必须合法，否则拒绝而非静默回退
    if use_relay:
        relay_protocol = (node.relay_protocol or "").lower()
        if relay_protocol not in URI_PROTOCOLS:
            raise ValueError(f"中转协议无效: {relay_protocol}")

    host = node.relay_ip if use_relay else node.ip
    port = node.relay_port if use_relay else node.port

    if not host:
        raise ValueError("主机地址缺失，无法构建 URI")
    if port is None:
        raise ValueError("端口缺失，无法构建 URI")
    if any(ch in host for ch in (" ", "/", "\\", "@", "#", "?")):
        raise ValueError(f"主机地址含非法字符: {host}")

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    auth = ""
    if node.username is not None and node.password is not None:
        user_part = quote(node.username, safe="")
        pass_part = quote(node.password, safe="")
        auth = f"{user_part}:{pass_part}@"

    return f"{protocol}://{auth}{host}:{port}"
