from typing import cast
"""
代理节点管理 API 路由层

路由前缀：/api/proxy-nodes
"""
import logging
import json
from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi import status as http_status
from sqlalchemy.orm import Session
from sqlalchemy import Integer, String, and_, case, cast as sql_cast, func, or_, select
from pydantic import BaseModel

from app.core.database import get_db
from app.services.account_summary_service import enrich_monitor_summaries
from app.models.device import Device, DeviceLog
from app.models.op_account import EmailAccount, OpAccount
from app.schemas.proxy_node import (
    ProxyNodeBatchTestResult,
    ProxyNodeCreate,
    ProxyNodeFilter,
    ProxyNodeImportResult,
    ProxyNodeResponse,
    ProxyNodeStats,
    ProxyNodeTestResult,
    ProxyNodeUpdate,
    ProxyNodeRelationUpdate,
)
from app.services import proxy_node_export_service, proxy_node_import_service
from app.services import proxy_node_service, proxy_node_test_service
from app.services.auth_service import get_current_user_from_header, require_permission
from app.services.asset_scope_service import get_scope_user_ids, get_scope_usernames, get_visible_node_ids, scoped_op_accounts
from app.models.team import User, OperationLog
from app.models.proxy_node import ProxyNode
from app.services.table_query_service import apply_table_query, model_table_fields
import threading

_relation_lock = threading.RLock()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy-nodes", tags=["Proxy Nodes"])


def _allowed_node_ids(db: Session, user: User) -> Optional[set[int]]:
    return get_visible_node_ids(db, user)


def _require_node_scope(db: Session, node: ProxyNode, user: User) -> None:
    allowed = _allowed_node_ids(db, user)
    if allowed is not None and node.id not in allowed:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _require_node_delete_scope(db: Session, node_ids: set[int], user: User) -> None:
    owner_ids = get_scope_user_ids(db, user)
    if owner_ids is None:
        return
    visible_account_ids = {
        account_id for (account_id,) in scoped_op_accounts(db, user).with_entities(OpAccount.id).filter(
            OpAccount.node_id.in_(node_ids)
        ).all()
    }
    linked_accounts = db.query(OpAccount).filter(OpAccount.node_id.in_(node_ids)).all()
    if any(account.id not in visible_account_ids for account in linked_accounts):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Node is linked to another member's account")
    names = cast(set[str], get_scope_usernames(db, user))
    linked_emails = db.query(EmailAccount).filter(EmailAccount.node_id.in_(node_ids)).all()
    if any(not ({email.registrant, email.operator} & names) for email in linked_emails):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Node is linked to another member's email")
    for device in db.query(Device).filter(Device.is_deleted == False).all():
        ids = device.node_ids or ([device.node_id] if device.node_id else [])
        if node_ids.intersection(ids) and device.owner_id not in owner_ids:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Node is linked to another member's device")


# ---------------------------------------------------------------------------
# 请求体模型（仅路由层使用）
# ---------------------------------------------------------------------------

class BatchDeleteBody(BaseModel):
    node_ids: List[int]


class BatchStatusBody(BaseModel):
    node_ids: List[int]
    status: str
    sale_customer: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sellers: Optional[List[str]] = None


class BatchTestBody(BaseModel):
    node_ids: List[int]


# ---------------------------------------------------------------------------
# GET /  — 查询节点列表（分页 + 筛选）
# ---------------------------------------------------------------------------

@router.get("", response_model=dict)
def list_nodes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[List[str]] = Query(None),
    protocol: Optional[List[str]] = Query(None),
    purchase_channel: Optional[str] = Query(None),
    sale_customer: Optional[str] = Query(None),
    expire_date_from: Optional[date] = Query(None),
    expire_date_to: Optional[date] = Query(None),
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    table_filters: str | None = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("proxy_node:view")),
) -> dict[str, object]:
    """查询节点列表，支持分页和多条件筛选。"""
    try:
        f = ProxyNodeFilter(
            status=status,
            protocol=protocol,
            purchase_channel=purchase_channel,
            sale_customer=sale_customer,
            expire_date_from=expire_date_from,
            expire_date_to=expire_date_to,
        )
        visible_ids = _allowed_node_ids(db, _current_user)
        allowed_owner_ids = get_scope_user_ids(db, _current_user)
        linked_ids = func.json_each(Device.node_ids).table_valued("value").alias("linked_node")
        linked_devices_query = db.query(Device).filter(Device.is_deleted.is_(False), or_(
            and_(func.coalesce(func.json_array_length(Device.node_ids), 0) == 0,
                 Device.node_id == ProxyNode.id),
            select(linked_ids.c.value).where(sql_cast(linked_ids.c.value, Integer) == ProxyNode.id)
                .correlate(Device, ProxyNode).exists(),
        ))
        if allowed_owner_ids is not None:
            linked_devices_query = linked_devices_query.filter(Device.owner_id.in_(allowed_owner_ids))
        linked_accounts_query = scoped_op_accounts(db, _current_user).filter(OpAccount.node_id == ProxyNode.id)
        extra_fields = {
            "device_name": linked_devices_query.with_entities(Device.name).order_by(Device.id).limit(1)
                .correlate(ProxyNode).scalar_subquery(),
            "devices": linked_devices_query.with_entities(sql_cast(func.group_concat(Device.name, " "), String))
                .correlate(ProxyNode).scalar_subquery(),
            "account_count": linked_accounts_query.with_entities(func.count(OpAccount.id))
                .correlate(ProxyNode).scalar_subquery(),
            "accounts": linked_accounts_query.with_entities(sql_cast(func.group_concat(
                OpAccount.account + " " + func.coalesce(OpAccount.nickname, ""), " "), String))
                .correlate(ProxyNode).scalar_subquery(),
        }
        nodes, total = proxy_node_service.get_nodes(
            db, filter=f, skip=skip, limit=limit, allowed_node_ids=visible_ids,
            sort_by=sort_by, sort_order=sort_order, table_filters=table_filters, extra_fields=extra_fields,
        )
        all_devices = db.query(Device).filter(Device.is_deleted == False).order_by(Device.id).all()
        for n in nodes:
            linked_devices = [d for d in all_devices if n.id in ((d.node_ids or []) or ([d.node_id] if d.node_id else []))]
            if allowed_owner_ids is not None:
                linked_devices = [d for d in linked_devices if d.owner_id in allowed_owner_ids]
            device = linked_devices[0] if linked_devices else None
            accounts = scoped_op_accounts(db, _current_user).filter(OpAccount.node_id == n.id).all()
            setattr(n, "device_id", device.id if device else None)
            setattr(n, "device_name", device.name if device else None)
            setattr(n, "account_count", len(accounts))
            setattr(n, "account_ids", [a.id for a in accounts])
            setattr(n, "devices", [{"id": d.id, "name": d.name} for d in linked_devices])
            enrich_monitor_summaries(db, accounts, _current_user)
            setattr(n, "accounts", [{
                "id": a.id,
                "username": a.account,
                "nickname": a.nickname,
                "avatar_url": a.avatar_url,
                "follower_count": a.follower_count,
                "following_count": a.following_count,
                "like_count": a.like_count,
                "video_count": a.video_count,
                "followers_change": getattr(a, "followers_change", None),
                "yesterday_video_count": getattr(a, "yesterday_video_count", None),
                "yesterday_video_plays": getattr(a, "yesterday_video_plays", None),
                "device_id": a.device_id if allowed_owner_ids is None or any(d.id == a.device_id for d in linked_devices) else None,
            } for a in accounts])
        items = [ProxyNodeResponse.model_validate(n) for n in nodes]
        return {"items": items, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"list_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /  — 创建节点，返回 201
# ---------------------------------------------------------------------------

@router.post("", response_model=ProxyNodeResponse, status_code=http_status.HTTP_201_CREATED)
def create_node(data: ProxyNodeCreate, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> ProxyNode:
    """创建单个代理节点。"""
    try:
        node = proxy_node_service.create_node(db, data, actor=_current_user.username)
        return node
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"create_node failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /stats  — 获取统计数据（必须在 /{node_id} 之前注册）
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=ProxyNodeStats)
def get_stats(
    expire_date_from: Optional[date] = Query(None),
    expire_date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("proxy_node:view")),
) -> ProxyNodeStats:
    """获取节点统计数据，支持按到期日期范围筛选。"""
    try:
        f = ProxyNodeFilter(
            expire_date_from=expire_date_from,
            expire_date_to=expire_date_to,
        )
        allowed_ids = _allowed_node_ids(db, _current_user)
        return proxy_node_service.get_stats(db, filter=f, allowed_node_ids=allowed_ids)
    except Exception as e:
        logger.error(f"get_stats failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /import/template  — 下载导入模板 CSV
# ---------------------------------------------------------------------------

@router.get("/import/template", response_model=None)
def download_import_template() -> Response:
    """下载节点导入模板 CSV 文件。"""
    try:
        content = proxy_node_import_service.generate_template_csv()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="proxy_nodes_template.csv"'
            },
        )
    except Exception as e:
        logger.error(f"download_import_template failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /import  — 批量导入（UploadFile）
# ---------------------------------------------------------------------------

@router.post("/import", response_model=ProxyNodeImportResult)
async def import_nodes(file: UploadFile, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> ProxyNodeImportResult:
    """批量导入节点，支持 CSV 和 Excel (.xlsx) 格式。"""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("csv", "xlsx"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Use .csv or .xlsx",
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"import_nodes: failed to read file: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {e}",
        )

    try:
        if ext == "csv":
            result = proxy_node_import_service.import_from_csv(db, content, actor=_current_user.username)
        else:
            result = proxy_node_import_service.import_from_excel(db, content, actor=_current_user.username)
        return result
    except Exception as e:
        logger.error(f"import_nodes: parse error: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse file: {e}",
        )


# ---------------------------------------------------------------------------
# GET /export  — 导出节点数据（CSV/Excel）
# ---------------------------------------------------------------------------

@router.get("/export", response_model=None)
def export_nodes(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    status: Optional[List[str]] = Query(None),
    protocol: Optional[List[str]] = Query(None),
    purchase_channel: Optional[str] = Query(None),
    sale_customer: Optional[str] = Query(None),
    expire_date_from: Optional[date] = Query(None),
    expire_date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("proxy_node:view")),
) -> Response:
    """导出节点数据，支持 CSV 和 Excel 格式，支持筛选条件。"""
    try:
        f = ProxyNodeFilter(
            status=status,
            protocol=protocol,
            purchase_channel=purchase_channel,
            sale_customer=sale_customer,
            expire_date_from=expire_date_from,
            expire_date_to=expire_date_to,
        )
        # 不分页，导出全部匹配节点
        visible_ids = _allowed_node_ids(db, _current_user)
        nodes, _ = proxy_node_service.get_nodes(
            db, filter=f, skip=0, limit=100000, allowed_node_ids=visible_ids
        )

        if format == "xlsx":
            file_content = proxy_node_export_service.export_to_excel(nodes)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = "proxy_nodes.xlsx"
        else:
            file_content = proxy_node_export_service.export_to_csv(nodes)
            media_type = "text/csv; charset=utf-8"
            filename = "proxy_nodes.csv"

        return Response(
            content=file_content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except Exception as e:
        logger.error(f"export_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# DELETE /batch  — 批量删除
# ---------------------------------------------------------------------------

@router.delete("/batch", response_model=None)
def batch_delete_nodes(body: BatchDeleteBody, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> dict[str, object]:
    """批量删除节点。"""
    try:
        if _allowed_node_ids(db, _current_user) is not None:
            visible = _allowed_node_ids(db, _current_user) or set()
            if set(body.node_ids) - visible:
                raise HTTPException(status_code=403, detail="无权删除部分代理节点")
        _require_node_delete_scope(db, set(body.node_ids), _current_user)
        deleted = proxy_node_service.batch_delete_nodes(db, body.node_ids)
        return {"deleted": deleted}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"batch_delete_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# PATCH /batch/status  — 批量修改状态
# ---------------------------------------------------------------------------

@router.patch("/batch/status", response_model=None)
def batch_update_status(body: BatchStatusBody, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> dict[str, object]:
    """批量修改节点状态。"""
    try:
        nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(body.node_ids)).all()
        if _allowed_node_ids(db, _current_user) is not None:
            visible = _allowed_node_ids(db, _current_user) or set()
            nodes = [n for n in nodes if n.id in visible]
        if len(nodes) != len(set(body.node_ids)):
            raise HTTPException(status_code=403, detail="无权操作部分代理节点")
        occupied = [n.id for n in nodes if n.status == "active" and body.status in {"idle", "disabled", "sold"}]
        if occupied:
            raise HTTPException(status_code=409, detail=f"节点正在使用中，先解除关联: {occupied}")
        updated = proxy_node_service.batch_update_status(db, [n.id for n in nodes], body.status, body.sale_customer, body.sale_price, body.sellers)
        return {"updated": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"batch_update_status failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /batch/test  — 批量测试节点连通性（必须在 /{node_id} 之前注册）
# ---------------------------------------------------------------------------

@router.post("/batch/test", response_model=ProxyNodeBatchTestResult)
async def batch_test_nodes(
    body: BatchTestBody,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_permission("proxy_node:manage")),
) -> ProxyNodeBatchTestResult:
    """批量测试节点连通性，最大并发 10。"""
    try:
        nodes = db.query(ProxyNode).filter(ProxyNode.id.in_(body.node_ids)).all()
        if len(nodes) != len(set(body.node_ids)):
            raise HTTPException(status_code=404, detail="部分代理节点不存在")
        allowed = _allowed_node_ids(db, _current_user)
        if allowed is not None and set(body.node_ids) - allowed:
            raise HTTPException(status_code=403, detail="无权测试部分代理节点")
        result = await proxy_node_test_service.batch_test_nodes(db, [n.id for n in nodes])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"batch_test_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /{node_id}/uri  — 获取节点代理 URI（仅超管，供二维码使用；须在 /{node_id} 之前注册）
# ---------------------------------------------------------------------------

@router.get("/{node_id}/uri", response_model=dict)
def get_node_uri(
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_header),
) -> dict[str, object]:
    """构建节点代理 URI（凭据编码）。仅超级管理员可用；仅空闲/使用中节点可生成。"""
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可查看节点 URI",
        )
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    if node.status not in ("idle", "active"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="该节点状态不可生成二维码（仅空闲/使用中节点可生成）",
        )
    try:
        uri = proxy_node_service.build_node_uri(node)
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return {"uri": uri}


# ---------------------------------------------------------------------------
# GET /{node_id}  — 查询单个节点
# ---------------------------------------------------------------------------

@router.get("/{node_id}", response_model=ProxyNodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:view"))) -> ProxyNode:
    """按 ID 查询单个节点，不存在返回 404。"""
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    _require_node_scope(db, node, _current_user)
    return node


# ---------------------------------------------------------------------------
# PATCH /{node_id}  — 部分更新节点
# ---------------------------------------------------------------------------

@router.patch("/{node_id}", response_model=ProxyNodeResponse)
def update_node(node_id: int, data: ProxyNodeUpdate, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> ProxyNode | None:
    """Update proxy node; return 404 when missing."""
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
    _require_node_scope(db, node, _current_user)
    return proxy_node_service.update_node(db, node_id, data)

@router.get("/{resource_id}/association-history", response_model=dict)
def get_association_history(resource_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("proxy_node:view"))) -> dict[str, object]:
    node = proxy_node_service.get_node(db, resource_id)
    if not node:
        raise HTTPException(status_code=404, detail="Not found")
    _require_node_scope(db, node, current_user)
    from app.services.relation_history_service import relation_overview
    return relation_overview(db, "node", resource_id, current_user)


@router.get("/{node_id}/logs", response_model=dict)
def get_node_logs(
    node_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: str | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
    table_filters: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("proxy_node:view")),
) -> dict[str, object]:
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if node is None:
        raise HTTPException(status_code=404, detail="代理节点不存在")
    if _allowed_node_ids(db, current_user) is not None and node_id not in (_allowed_node_ids(db, current_user) or set()):
        raise HTTPException(status_code=403, detail="Forbidden")
    paths = [f"{method} /api/proxy-nodes/{node_id}{suffix}" for method, suffix in (
        ("UPDATE", ""), ("UPDATE", "/relation"), ("DELETE", ""), ("VIEW_SECRET", "/uri"),
    )]
    query = db.query(OperationLog).filter(
        OperationLog.module.in_(["节点管理", "节点关联"]), OperationLog.summary.in_(paths),
    )
    fields = model_table_fields(OperationLog)
    fields["summary"] = case(
        (OperationLog.summary.endswith("/relation"), "调整关联"),
        (OperationLog.action == "UPDATE", "修改节点资料"),
        (OperationLog.action == "DELETE", "删除节点"),
        (OperationLog.action == "VIEW_SECRET", "查看节点连接凭据"), else_=OperationLog.action,
    )
    query = apply_table_query(query, fields, sort_by, sort_order, table_filters,
                              stable_column=OperationLog.id, default_sort=(OperationLog.created_at, "desc"))
    return {
        "total": query.count(),
        "items": [{"id": log.id, "username": log.username, "action": log.action,
                   "result": log.result, "summary": "调整关联" if cast(str, log.summary).endswith("/relation") else
                   {"UPDATE": "修改节点资料", "DELETE": "删除节点", "VIEW_SECRET": "查看节点连接凭据"}.get(log.action, log.action),
                   "created_at": log.created_at}
                  for log in query.offset(skip).limit(limit).all()],
    }


@router.put("/{node_id}/relation", response_model=dict)
def update_node_relation(node_id: int, data: ProxyNodeRelationUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("proxy_node:manage"))) -> dict[str, object]:
    with _relation_lock:
        return _update_node_relation_locked(node_id, data, db, current_user)

def _update_node_relation_locked(node_id: int, data: ProxyNodeRelationUpdate, db: Session, current_user: User) -> dict[str, object]:
    # 直接读取 ORM，避免服务层为响应反序列化 sellers 后把 list 写回 Text 列导致提交失败。
    node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="代理节点不存在")
    _require_node_scope(db, node, current_user)
    allowed_owner_ids = get_scope_user_ids(db, current_user)
    visible_account_ids = {
        account_id for (account_id,) in scoped_op_accounts(db, current_user).with_entities(OpAccount.id).all()
    }
    selected_account = None
    if "account_id" in data.model_fields_set and data.account_id is not None:
        selected_account = db.query(OpAccount).filter(OpAccount.id == data.account_id).first()
        if not selected_account:
            raise HTTPException(status_code=404, detail="运营账号不存在")
        if selected_account.id not in visible_account_ids:
            raise HTTPException(status_code=403, detail="无权关联该运营账号")
    relation_changes: list[tuple[Device, list[int], list[int]]] = []
    if "device_id" not in data.model_fields_set:
        pass
    elif data.device_id is None:
        foreign_accounts = [] if allowed_owner_ids is None else [
            account for account in db.query(OpAccount).filter(OpAccount.device_id.isnot(None)).all()
            if account.id not in visible_account_ids
        ]
        candidates = [
            d for d in db.query(Device).filter(Device.is_deleted == False).all()
            if (allowed_owner_ids is None or d.owner_id in allowed_owner_ids)
            and node_id in (d.node_ids or ([d.node_id] if d.node_id else []))
        ]
        if any(account.device_id == d.id for d in candidates for account in foreign_accounts):
            raise HTTPException(status_code=403, detail="无权调整其他成员账号的节点关联")
        for d in candidates:
            ids = d.node_ids or ([d.node_id] if d.node_id else [])
            if node_id in ids:
                old_ids = list(ids)
                ids = [x for x in ids if x != node_id]
                d.node_ids = ids
                d.node_id = ids[0] if ids else None
                relation_changes.append((d, old_ids, ids))
    else:
        selected_device = db.query(Device).filter(Device.id == data.device_id, Device.is_deleted == False).first()
        if not selected_device:
            raise HTTPException(status_code=404, detail="终端不存在或已删除")
        d = selected_device
        if allowed_owner_ids is not None and d.owner_id not in allowed_owner_ids:
            raise HTTPException(status_code=403, detail="无权关联该终端")
        if node.status not in ("idle", "active"):
            raise HTTPException(status_code=409, detail="代理节点当前状态不可绑定")

        ids = d.node_ids or ([d.node_id] if d.node_id else [])
        old_ids = list(ids)
        d.node_ids = list(dict.fromkeys(ids + [node_id]))
        d.node_id = d.node_ids[0]
        relation_changes.append((d, old_ids, d.node_ids))
    if "account_id" not in data.model_fields_set:
        pass
    elif data.account_id is None:
        accounts = db.query(OpAccount).filter(OpAccount.node_id == node_id).all()
        accounts = [a for a in accounts if a.id in visible_account_ids]
        if len(accounts) > 1:
            raise HTTPException(status_code=409, detail="该节点绑定多个账号，请从账号列表逐个解除")
        for account in accounts:
            if account.device_id:
                device = db.query(Device).filter(Device.id == account.device_id, Device.is_deleted == False).first()
                if device and node_id in (device.node_ids or ([device.node_id] if device.node_id else [])):
                    raise HTTPException(status_code=409, detail="账号节点由终端管理，请先解除终端的节点关联")
            account.node_id = None
            from app.services.op_account_service import _write_audit_log, record_relation_snapshot
            _write_audit_log(db, account.id, "update", "node_id", str(node_id), None, current_user.username)
            record_relation_snapshot(db, account, current_user.username)
    else:
        account = cast(OpAccount, selected_account)
        if node.status not in ("idle", "active"):
            raise HTTPException(status_code=409, detail="代理节点当前状态不可绑定")
        from app.services.op_account_service import normalize_account_relation
        normalize_account_relation(db, {"node_id": node_id}, account)
        old_node_id = account.node_id
        account.node_id = node_id
        from app.services.op_account_service import _write_audit_log, record_relation_snapshot
        if old_node_id != node_id:
            _write_audit_log(db, account.id, "update", "node_id", str(old_node_id) if old_node_id else None, str(node_id), current_user.username)
            record_relation_snapshot(db, account, current_user.username)
    for device, old_ids, new_ids in relation_changes:
        from app.services.op_account_service import sync_device_account_nodes
        sync_device_account_nodes(db, device, current_user.username)
        db.add(DeviceLog(device_id=device.id, user_id=current_user.id, username=current_user.username,
                         action="UPDATE", changes=json.dumps({"relations": {"old_node_ids": old_ids, "new_node_ids": new_ids,
                                                                       "source": "proxy_node"}}, ensure_ascii=False)))
    db.commit()
    return {"ok": True, "node_id": node_id, "device_id": data.device_id if "device_id" in data.model_fields_set else None, "account_id": data.account_id if "account_id" in data.model_fields_set else None}


# ---------------------------------------------------------------------------
# DELETE /{node_id}  — 删除节点，成功返回 204
# ---------------------------------------------------------------------------

@router.delete("/{node_id}", status_code=http_status.HTTP_204_NO_CONTENT, response_model=None)
def delete_node(node_id: int, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> Response:
    """删除节点，成功返回 204，不存在返回 404。"""
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
    _require_node_scope(db, node, _current_user)
    _require_node_delete_scope(db, {node_id}, _current_user)
    success = proxy_node_service.delete_node(db, node_id)
    if not success:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /{node_id}/test  — 测试单个节点连通性
# ---------------------------------------------------------------------------

@router.post("/{node_id}/test", response_model=ProxyNodeTestResult)
async def test_node(node_id: int, db: Session = Depends(get_db), _current_user: User = Depends(require_permission("proxy_node:manage"))) -> ProxyNodeTestResult:
    """测试单个节点连通性，不存在返回 404。"""
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Node {node_id} not found")
    _require_node_scope(db, node, _current_user)
    result = await proxy_node_test_service.test_node(db, node_id)
    if result is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    return result
