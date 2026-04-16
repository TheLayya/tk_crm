"""
代理节点管理 API 路由层

路由前缀：/api/proxy-nodes
"""
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi import status as http_status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.schemas.proxy_node import (
    ProxyNodeBatchTestResult,
    ProxyNodeCreate,
    ProxyNodeFilter,
    ProxyNodeImportResult,
    ProxyNodeResponse,
    ProxyNodeStats,
    ProxyNodeTestResult,
    ProxyNodeUpdate,
)
from app.services import proxy_node_export_service, proxy_node_import_service
from app.services import proxy_node_service, proxy_node_test_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy-nodes", tags=["Proxy Nodes"])


# ---------------------------------------------------------------------------
# 请求体模型（仅路由层使用）
# ---------------------------------------------------------------------------

class BatchDeleteBody(BaseModel):
    node_ids: List[int]


class BatchStatusBody(BaseModel):
    node_ids: List[int]
    status: str


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
    db: Session = Depends(get_db),
):
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
        nodes, total = proxy_node_service.get_nodes(db, filter=f, skip=skip, limit=limit)
        items = [ProxyNodeResponse.model_validate(n) for n in nodes]
        return {"items": items, "total": total}
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
def create_node(data: ProxyNodeCreate, db: Session = Depends(get_db)):
    """创建单个代理节点。"""
    try:
        node = proxy_node_service.create_node(db, data)
        return node
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
):
    """获取节点统计数据，支持按到期日期范围筛选。"""
    try:
        f = ProxyNodeFilter(
            expire_date_from=expire_date_from,
            expire_date_to=expire_date_to,
        )
        return proxy_node_service.get_stats(db, filter=f)
    except Exception as e:
        logger.error(f"get_stats failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /import/template  — 下载导入模板 CSV
# ---------------------------------------------------------------------------

@router.get("/import/template")
def download_import_template():
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
async def import_nodes(file: UploadFile, db: Session = Depends(get_db)):
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
            result = proxy_node_import_service.import_from_csv(db, content)
        else:
            result = proxy_node_import_service.import_from_excel(db, content)
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

@router.get("/export")
def export_nodes(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    status: Optional[List[str]] = Query(None),
    protocol: Optional[List[str]] = Query(None),
    purchase_channel: Optional[str] = Query(None),
    sale_customer: Optional[str] = Query(None),
    expire_date_from: Optional[date] = Query(None),
    expire_date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
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
        nodes, _ = proxy_node_service.get_nodes(db, filter=f, skip=0, limit=100000)

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

@router.delete("/batch")
def batch_delete_nodes(body: BatchDeleteBody, db: Session = Depends(get_db)):
    """批量删除节点。"""
    try:
        deleted = proxy_node_service.batch_delete_nodes(db, body.node_ids)
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"batch_delete_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# PATCH /batch/status  — 批量修改状态
# ---------------------------------------------------------------------------

@router.patch("/batch/status")
def batch_update_status(body: BatchStatusBody, db: Session = Depends(get_db)):
    """批量修改节点状态。"""
    try:
        updated = proxy_node_service.batch_update_status(db, body.node_ids, body.status)
        return {"updated": updated}
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
async def batch_test_nodes(body: BatchTestBody, db: Session = Depends(get_db)):
    """批量测试节点连通性，最大并发 10。"""
    try:
        result = await proxy_node_test_service.batch_test_nodes(db, body.node_ids)
        return result
    except Exception as e:
        logger.error(f"batch_test_nodes failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /{node_id}  — 查询单个节点
# ---------------------------------------------------------------------------

@router.get("/{node_id}", response_model=ProxyNodeResponse)
def get_node(node_id: int, db: Session = Depends(get_db)):
    """按 ID 查询单个节点，不存在返回 404。"""
    node = proxy_node_service.get_node(db, node_id)
    if not node:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    return node


# ---------------------------------------------------------------------------
# PATCH /{node_id}  — 部分更新节点
# ---------------------------------------------------------------------------

@router.patch("/{node_id}", response_model=ProxyNodeResponse)
def update_node(node_id: int, data: ProxyNodeUpdate, db: Session = Depends(get_db)):
    """部分更新节点，不存在返回 404。"""
    node = proxy_node_service.update_node(db, node_id, data)
    if not node:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    return node


# ---------------------------------------------------------------------------
# DELETE /{node_id}  — 删除节点，成功返回 204
# ---------------------------------------------------------------------------

@router.delete("/{node_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_node(node_id: int, db: Session = Depends(get_db)):
    """删除节点，成功返回 204，不存在返回 404。"""
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
async def test_node(node_id: int, db: Session = Depends(get_db)):
    """测试单个节点连通性，不存在返回 404。"""
    result = await proxy_node_test_service.test_node(db, node_id)
    if result is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )
    return result
