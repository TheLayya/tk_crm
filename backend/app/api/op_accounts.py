"""
运营账号管理 API 端点
"""
import logging
import threading
import httpx
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from app.services.account_summary_service import enrich_monitor_summaries
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.device import Device
from app.models.proxy_node import ProxyNode
from app.models.video import OpAccountVideo
from app.schemas.op_account import (
    AuditLogResponse,
    BatchStatusUpdate,
    CollectTaskResponse,
    OpAccountCreate,
    OpAccountResponse,
    OpAccountUpdate,
    OpImportResult,
    BatchAssignOperator,
    GmailCheckRequest,
)
from app.services import op_account_service, video_service
from app.services.gmail_checker_service import MAX_BATCH_SIZE, apply_check_results, check_gmail_accounts

from app.services.auth_service import require_permission, get_current_user_from_header, get_user_data_scope, get_dept_member_usernames

logger = logging.getLogger(__name__)

router = APIRouter(tags=["op-accounts"])
gmail_check_lock = threading.Lock()


@router.get("/stats", response_model=dict)
def get_stats(
    exclude_gmail: bool = Query(False),
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:view")),
):
    """获取运营账号统计数据。"""
    return op_account_service.get_op_account_stats(db, exclude_gmail=exclude_gmail)


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
    exclude_gmail: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:view")),
):
    # 数据范围过滤
    data_scope = get_user_data_scope(db, current_user)
    scope_username = current_user.username if data_scope == "self" else None
    scope_usernames = get_dept_member_usernames(db, current_user) if data_scope == "dept" else None

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
        scope_usernames=scope_usernames,
        exclude_gmail=exclude_gmail,
    )
    enrich_monitor_summaries(db, items, current_user)
    for item in items:
        device = db.query(Device).filter(Device.id == item.device_id, Device.is_deleted == False).first() if item.device_id else None
        node = db.query(ProxyNode).filter(ProxyNode.id == item.node_id).first() if item.node_id else None
        item.device_name = device.name if device else None
        item.node_ip = f"{node.ip}:{node.port}" if node else None
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
        account = op_account_service.create_op_account(db, data, actor=current_user.username)
        # 创建后触发采集
        if account.platform == "tiktok":
            op_account_service.trigger_collect(db, [account.id], background_tasks)
        return OpAccountResponse.model_validate(account)
    except Exception as e:
        logger.error(f"Failed to create op_account: {e}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# 注意：以下固定路径路由必须在 /{id} 之前定义，避免路径冲突


@router.get("/import/template")
def download_import_template(_=Depends(require_permission("op_account:import"))):
    data = op_account_service.create_import_template()
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="op_accounts_import_template_zh.xlsx"'},
    )


@router.post("/batch-status", response_model=dict)
def batch_update_status(data: BatchStatusUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user_from_header), _=Depends(require_permission("op_account:edit"))):
    scope = get_user_data_scope(db, current_user)
    if scope != "all":
        allowed = set(get_dept_member_usernames(db, current_user)) if scope == "dept" else {current_user.username}
        accounts = db.query(op_account_service.OpAccount).filter(op_account_service.OpAccount.id.in_(data.ids)).all()
        if len(accounts) != len(set(data.ids)):
            raise HTTPException(status_code=404, detail="部分运营账号不存在")
        if any(not ({a.registrant, a.operator} & allowed) for a in accounts):
            raise HTTPException(status_code=403, detail="无权批量操作部分运营账号")
    count = op_account_service.batch_update_status(
        db,
        ids=data.ids,
        status=data.status,
        sale_customer=data.sale_customer,
        sale_price=data.sale_price,
        sale_date=data.sale_date,
        sellers=data.sellers,
        actor=current_user.username,
    )
    return {"updated": count}


@router.post("/batch-assign", response_model=dict)
def batch_assign_operator(
    data: BatchAssignOperator,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:edit")),
    _members=Depends(require_permission("team:member:view")),
):
    count = op_account_service.batch_assign_operator(db, data.ids, data.operator, current_user)
    return {"updated": count}


@router.post("/import", response_model=OpImportResult)
async def import_from_csv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:import")),
):
    raw = await file.read()
    filename = (file.filename or "").lower()
    try:
        if filename.endswith(".xlsx"):
            result = op_account_service.import_from_excel(
                db,
                file_content=raw,
                actor=current_user.username,
                force_actor=not current_user.is_super_admin,
            )
        elif filename.endswith(".txt"):
            result = op_account_service.import_gmail_text(db, raw.decode("utf-8-sig"), actor=current_user.username)
        elif filename.endswith(".csv"):
            content = raw.decode("utf-8-sig", errors="replace")
            result = op_account_service.import_from_csv(
                db,
                csv_content=content,
                actor=current_user.username,
                force_actor=not current_user.is_super_admin,
            )
        else:
            raise HTTPException(status_code=422, detail="仅支持 CSV、XLSX 或 Gmail 冒号分隔 TXT 文件")
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=f"导入文件格式错误：{exc}") from exc
    account_ids = [
        row.get("_id") for row in result.rows
        if row.get("_result") == "success" and row.get("_id")
    ]
    if account_ids:
        tiktok_ids = [item.id for item in db.query(op_account_service.OpAccount).filter(op_account_service.OpAccount.id.in_(account_ids), op_account_service.OpAccount.platform == "tiktok").all()]
        if tiktok_ids:
            result.task_id = op_account_service.trigger_collect(db, tiktok_ids, background_tasks)
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
    localized: bool = Query(False, description="是否使用中文表头"),
    db: Session = Depends(get_db),
    _=Depends(require_permission("op_account:export")),
):
    if format not in {"csv", "xlsx"}:
        raise HTTPException(status_code=422, detail="导出格式仅支持 CSV 或 XLSX")
    filters = {
        "platform": platform,
        "status": status,
        "keyword": keyword,
        "tags": tags,
        "purchase_channel": purchase_channel,
        "sale_customer": sale_customer,
    }
    data = op_account_service.export_op_accounts(db, filters=filters, format=format, localized=localized)

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


@router.post("/gmail-check", response_model=dict)
def check_gmail_status(
    body: GmailCheckRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_from_header),
    _=Depends(require_permission("op_account:collect")),
):
    account_ids = list(dict.fromkeys(body.account_ids))
    if not account_ids or len(account_ids) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=422, detail=f"请选择 1-{MAX_BATCH_SIZE} 个 Gmail 账号")
    accounts = db.query(op_account_service.OpAccount).filter(
        op_account_service.OpAccount.id.in_(account_ids),
        op_account_service.OpAccount.platform == "gmail",
    ).all()
    if len(accounts) != len(account_ids):
        raise HTTPException(status_code=422, detail="只能检测已选择的 Gmail 账号")
    scope = get_user_data_scope(db, current_user)
    allowed = set(get_dept_member_usernames(db, current_user)) if scope == "dept" else {current_user.username}
    if scope != "all" and any(not ({account.registrant, account.operator} & allowed) for account in accounts):
        raise HTTPException(status_code=403, detail="无权检测部分运营账号")
    if not gmail_check_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="已有 Gmail 检测进行中，请稍后重试")
    try:
        results = check_gmail_accounts([account.account for account in accounts])
        apply_check_results(accounts, results)
        for account in accounts:
            db.add(op_account_service.OpAuditLog(
                op_account_id=account.id, action="gmail_check", field_name="gmail_check_status",
                new_value=account.gmail_check_status, operator=current_user.username,
            ))
        db.commit()
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Gmail 检测服务不可用或返回异常，未覆盖原检测结果，请稍后重试") from exc
    finally:
        gmail_check_lock.release()
    return {"checked": len(accounts), "results": [
        {"id": account.id, "email": account.account, "status": account.gmail_check_status,
         "raw_status": account.gmail_check_raw_status, "checked_at": account.gmail_checked_at}
        for account in accounts
    ]}


@router.put("/{id}", response_model=OpAccountResponse)
def update_op_account(id: int, data: OpAccountUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user_from_header), _=Depends(require_permission("op_account:edit"))):
    account = op_account_service.get_op_account(db, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    scope = get_user_data_scope(db, current_user)
    allowed = {account.registrant, account.operator}
    if (scope == "self" and current_user.username not in allowed) or (scope == "dept" and not allowed.intersection(get_dept_member_usernames(db, current_user))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该运营账号")
    account = op_account_service.update_op_account(db, id, data, actor=current_user.username)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return OpAccountResponse.model_validate(account)


@router.get("/{id}/videos")
def get_op_account_videos(
    id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("op_account:view")),
):
    account = op_account_service.get_op_account(db, id)
    if not account:
        raise HTTPException(status_code=404, detail="运营账号不存在")
    scope = get_user_data_scope(db, current_user)
    allowed = {account.registrant, account.operator}
    if ((scope == "self" and current_user.username not in allowed)
            or (scope == "dept" and not allowed.intersection(get_dept_member_usernames(db, current_user)))):
        raise HTTPException(status_code=403, detail="无权查看该运营账号")
    return {
        "items": video_service.get_videos(db, id, skip, limit, model=OpAccountVideo),
        "total": db.query(OpAccountVideo).filter(OpAccountVideo.account_id == id).count(),
        "skip": skip,
        "limit": limit,
    }


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_op_account(id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user_from_header), _=Depends(require_permission("op_account:delete"))):
    account = op_account_service.get_op_account(db, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    scope = get_user_data_scope(db, current_user)
    allowed = {account.registrant, account.operator}
    if (scope == "self" and current_user.username not in allowed) or (scope == "dept" and not allowed.intersection(get_dept_member_usernames(db, current_user))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该运营账号")
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


@router.get("/{resource_id}/association-history", response_model=dict)
def get_association_history(resource_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("op_account:view"))):
    from app.services.relation_history_service import relation_overview
    return relation_overview(db, "account", resource_id, current_user)


@router.get("/{id}/logs", response_model=List[AuditLogResponse])
def get_audit_logs(id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("op_account:view"))):
    account = op_account_service.get_op_account(db, id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    from app.services.relation_history_service import relation_overview, readable_account_log
    relation_overview(db, "account", id, current_user)
    logs = op_account_service.get_audit_logs(db, account_id=id)
    return [AuditLogResponse.model_validate(log).model_copy(update=readable_account_log(db, log))
            for log in logs if log.field_name != "relation_snapshot"]
