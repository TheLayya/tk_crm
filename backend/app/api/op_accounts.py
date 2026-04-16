"""
运营账号管理 API 端点
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.op_account import (
    AuditLogResponse,
    BatchStatusUpdate,
    CollectTaskResponse,
    OpAccountCreate,
    OpAccountResponse,
    OpAccountUpdate,
    OpImportResult,
)
from app.services import op_account_service
from app.services.auth_service import require_permission, get_current_user_from_header, get_user_data_scope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["op-accounts"])


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:view")),
):
    """获取运营账号统计数据。"""
    return op_account_service.get_op_account_stats(db)


@router.get("", response_model=dict)
def list_op_accounts(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    purchase_channel: Optional[str] = Query(None),
    sale_customer: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:view")),
):
    # 数据范围过滤
    data_scope = get_user_data_scope(db, current_user)
    scope_username = current_user.username if data_scope == "self" else None

    items, total = op_account_service.list_op_accounts(
        db,
        platform=platform,
        status=status,
        keyword=keyword,
        tags=tags,
        purchase_channel=purchase_channel,
        sale_customer=sale_customer,
        skip=skip,
        limit=limit,
        scope_username=scope_username,
    )
    return {
        "items": [OpAccountResponse.model_validate(item).model_dump() for item in items],
        "total": total,
    }


@router.post("", response_model=OpAccountResponse, status_code=status.HTTP_201_CREATED)
def create_op_account(
    data: OpAccountCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:create")),
):
    try:
        # 如果未填 registrant，自动设为当前用户，确保数据范围过滤能匹配到自己
        if not data.registrant:
            data = data.model_copy(update={"registrant": current_user.username})
        account = op_account_service.create_op_account(db, data)
        # 创建后触发采集
        op_account_service.trigger_collect(db, [account.id], background_tasks)
        return OpAccountResponse.model_validate(account)
    except Exception as e:
        logger.error(f"Failed to create op_account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# 注意：以下固定路径路由必须在 /{id} 之前定义，避免路径冲突

@router.post("/batch-status", response_model=dict)
def batch_update_status(data: BatchStatusUpdate, db: Session = Depends(get_db), _=Depends(require_permission("op_account:edit"))):
    count = op_account_service.batch_update_status(
        db,
        ids=data.ids,
        status=data.status,
        sale_customer=data.sale_customer,
        sale_price=data.sale_price,
        sale_date=data.sale_date,
        sellers=data.sellers,
    )
    return {"updated": count}


@router.post("/import", response_model=OpImportResult)
async def import_from_csv(
    file: UploadFile,
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:import")),
):
    raw = await file.read()
    content = raw.decode("utf-8-sig")
    result = op_account_service.import_from_csv(db, csv_content=content)
    return result


@router.get("/export")
def export_op_accounts(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    purchase_channel: Optional[str] = Query(None),
    sale_customer: Optional[str] = Query(None),
    format: str = Query("csv"),
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:export")),
):
    filters = {
        "platform": platform,
        "status": status,
        "keyword": keyword,
        "tags": tags,
        "purchase_channel": purchase_channel,
        "sale_customer": sale_customer,
    }
    data = op_account_service.export_op_accounts(db, filters=filters, format=format)

    if format == "xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "op_accounts.xlsx"
    else:
        media_type = "text/csv; charset=utf-8-sig"
        filename = "op_accounts.csv"

    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/collect", response_model=dict)
def trigger_collect(
    body: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:collect")),
):
    account_ids = body.get("account_ids", [])
    task_id = op_account_service.trigger_collect(db, account_ids=account_ids, background_tasks=background_tasks)
    return {"task_id": task_id}


@router.get("/tasks/{task_id}", response_model=CollectTaskResponse)
def get_collect_task(task_id: str, db: Session = Depends(get_db), _=Depends(require_permission("op_account:view"))):
    task = op_account_service.get_collect_task(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return CollectTaskResponse(
        task_id=task.id,
        status=task.status,
        total=task.total,
        completed=task.completed,
        success=task.success,
        failed=task.failed,
    )


@router.put("/{id}", response_model=OpAccountResponse)
def update_op_account(id: int, data: OpAccountUpdate, db: Session = Depends(get_db), _=Depends(require_permission("op_account:edit"))):
    account = op_account_service.update_op_account(db, id, data)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return OpAccountResponse.model_validate(account)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_op_account(id: int, db: Session = Depends(get_db), _=Depends(require_permission("op_account:delete"))):
    ok = op_account_service.delete_op_account(db, id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return None


@router.get("/avatar-proxy")
async def proxy_avatar(url: str = Query(...), _=Depends(require_permission("op_account:view"))):
    """代理转发 TikTok 头像图片，绕过防盗链"""
    import httpx
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "Referer": "https://www.tiktok.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
        from fastapi.responses import Response
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch avatar")


@router.get("/{id}/logs", response_model=List[AuditLogResponse])
def get_audit_logs(id: int, db: Session = Depends(get_db), _=Depends(require_permission("op_account:view"))):
    account = op_account_service.get_op_account(db, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    logs = op_account_service.get_audit_logs(db, account_id=id)
    return [AuditLogResponse.model_validate(log) for log in logs]
