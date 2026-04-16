import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.proxy_node import ProxyNode
from app.schemas.proxy_node import (
    ChannelStats,
    ProxyNodeCreate,
    ProxyNodeFilter,
    ProxyNodeStats,
    ProxyNodeUpdate,
)

logger = logging.getLogger(__name__)


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

    logger.debug(f"get_nodes: total={total}, skip={skip}, limit={limit}, returned={len(nodes)}")
    return nodes, total


def get_node(db: Session, node_id: int) -> Optional[ProxyNode]:
    """按 ID 查询节点，不存在返回 None。"""
    return db.query(ProxyNode).filter(ProxyNode.id == node_id).first()


def create_node(db: Session, data: ProxyNodeCreate) -> ProxyNode:
    """创建节点，默认值已在 Schema 中定义。"""
    node = ProxyNode(**data.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    logger.info(f"Created proxy node id={node.id} ip={node.ip}:{node.port}")
    return node


def update_node(
    db: Session, node_id: int, data: ProxyNodeUpdate
) -> Optional[ProxyNode]:
    """部分更新节点，自动刷新 updated_at；节点不存在返回 None。"""
    node = get_node(db, node_id)
    if not node:
        return None

    update_data = data.get_update_data()
    for field, value in update_data.items():
        setattr(node, field, value)

    node.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(node)
    logger.info(f"Updated proxy node id={node_id}, fields={list(update_data.keys())}")
    return node


def delete_node(db: Session, node_id: int) -> bool:
    """删除节点，成功返回 True，不存在返回 False。"""
    node = get_node(db, node_id)
    if not node:
        return False

    db.delete(node)
    db.commit()
    logger.info(f"Deleted proxy node id={node_id}")
    return True


def batch_delete_nodes(db: Session, node_ids: List[int]) -> int:
    """批量删除节点，返回实际删除数量。"""
    deleted = (
        db.query(ProxyNode)
        .filter(ProxyNode.id.in_(node_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info(f"Batch deleted {deleted} proxy nodes, requested ids={node_ids}")
    return deleted


def batch_update_status(db: Session, node_ids: List[int], status: str) -> int:
    """批量修改状态，自动更新 updated_at，返回更新数量。"""
    updated = (
        db.query(ProxyNode)
        .filter(ProxyNode.id.in_(node_ids))
        .update(
            {"status": status, "updated_at": datetime.utcnow()},
            synchronize_session=False,
        )
    )
    db.commit()
    logger.info(f"Batch updated status to '{status}' for {updated} nodes, requested ids={node_ids}")
    return updated


def get_stats(
    db: Session, filter: Optional[ProxyNodeFilter] = None
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
