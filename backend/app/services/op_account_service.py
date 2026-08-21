import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.op_account import OpAccount, OpAuditLog, OpCollectTask
from app.schemas.op_account import (
    OpAccountCreate,
    OpAccountUpdate,
    OpImportResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sellers JSON helpers
# ---------------------------------------------------------------------------

def _serialize_sellers(sellers: Optional[List[str]]) -> Optional[str]:
    """将 Python 列表序列化为 JSON 字符串存入数据库。None 存为 NULL。"""
    if sellers is None:
        return None
    return json.dumps(sellers, ensure_ascii=False)


def _deserialize_sellers(value: Optional[str]) -> List[str]:
    """将数据库中的 JSON 字符串反序列化为 Python 列表。NULL 或空值返回空列表。"""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def _write_audit_log(
    db: Session,
    account_id: int,
    action: str,
    field_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    operator: Optional[str] = None,
) -> None:
    log = OpAuditLog(
        op_account_id=account_id,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        operator=operator,
    )
    db.add(log)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_op_account(db: Session, data: OpAccountCreate) -> OpAccount:
    # Prevent duplicate operation accounts even when no project is selected
    existing = db.query(OpAccount).filter(
        OpAccount.platform == data.platform,
        OpAccount.account == data.account,
    ).first()
    if existing:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="该平台账号已存在")
    data_dict = data.model_dump()
    # 序列化 sellers 列表为 JSON 字符串
    data_dict['sellers'] = _serialize_sellers(data_dict.get('sellers'))
    account = OpAccount(**data_dict)
    db.add(account)
    db.commit()
    db.refresh(account)
    _write_audit_log(db, account.id, "create", field_name=None, old_value=None, new_value="created")
    db.commit()
    # 反序列化 sellers 供返回
    return account


def get_op_account(db: Session, id: int) -> Optional[OpAccount]:
    account = db.query(OpAccount).filter(OpAccount.id == id).first()
    return account


def update_op_account(db: Session, id: int, data: OpAccountUpdate) -> Optional[OpAccount]:
    account = db.query(OpAccount).filter(OpAccount.id == id).first()
    if not account:
        return None
    update_data = data.model_dump(exclude_unset=True)
    # 序列化 sellers
    if 'sellers' in update_data:
        update_data['sellers'] = _serialize_sellers(update_data['sellers'])
    for field, new_val in update_data.items():
        old_val = getattr(account, field, None)
        if old_val != new_val:
            _write_audit_log(
                db, account.id, "update",
                field_name=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
            )
            setattr(account, field, new_val)
    db.commit()
    db.refresh(account)
    return account


def delete_op_account(db: Session, id: int) -> bool:
    account = get_op_account(db, id)
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


def list_op_accounts(
    db: Session,
    project_id: Optional[int] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    tags: Optional[str] = None,
    purchase_channel: Optional[str] = None,
    sale_customer: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    scope_username: Optional[str] = None,
) -> tuple:
    query = db.query(OpAccount)
    if project_id is not None:
        query = query.filter(OpAccount.project_id == project_id)
    if platform:
        query = query.filter(OpAccount.platform == platform)
    if status:
        query = query.filter(OpAccount.status == status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            OpAccount.account.ilike(like) | OpAccount.nickname.ilike(like)
        )
    if tags:
        query = query.filter(OpAccount.tags.ilike(f"%{tags}%"))
    if purchase_channel:
        query = query.filter(OpAccount.purchase_channel == purchase_channel)
    if sale_customer:
        query = query.filter(OpAccount.sale_customer == sale_customer)
    # 数据范围：只看自己相关的（注册人或使用人）
    if scope_username:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                OpAccount.registrant == scope_username,
                OpAccount.operator == scope_username,
            )
        )
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    # 反序列化每条记录的 sellers
    for item in items:
        item.sellers = _deserialize_sellers(item.sellers)
    return items, total


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_op_account_stats(db: Session) -> dict:
    """
    统计运营账号的汇总数据：总数、各状态数量、总采购成本、总出售收入、净收益。
    """
    from decimal import Decimal
    from sqlalchemy import func

    total = db.query(OpAccount).count()

    # 各状态数量
    status_rows = (
        db.query(OpAccount.status, func.count(OpAccount.id))
        .group_by(OpAccount.status)
        .all()
    )
    by_status = {"正常": 0, "自用": 0, "封禁": 0, "已售": 0}
    for status_val, cnt in status_rows:
        if status_val in by_status:
            by_status[status_val] = cnt

    # 各平台数量
    platform_rows = (
        db.query(OpAccount.platform, func.count(OpAccount.id))
        .group_by(OpAccount.platform)
        .all()
    )
    by_platform = {}
    for platform_val, cnt in platform_rows:
        by_platform[platform_val] = cnt

    # 成本与收益
    purchase_sum = db.query(func.sum(OpAccount.purchase_price)).scalar() or Decimal("0")
    sale_sum = db.query(func.sum(OpAccount.sale_price)).scalar() or Decimal("0")
    net_profit = Decimal(str(sale_sum)) - Decimal(str(purchase_sum))

    return {
        "total": total,
        "by_status": by_status,
        "by_platform": by_platform,
        "total_purchase_cost": float(purchase_sum),
        "total_sale_revenue": float(sale_sum),
        "net_profit": float(net_profit),
    }


# ---------------------------------------------------------------------------
# Batch status update
# ---------------------------------------------------------------------------

def batch_update_status(
    db: Session,
    ids: list,
    status: str,
    sale_customer: Optional[str] = None,
    sale_price=None,
    sale_date=None,
    sellers: Optional[List[str]] = None,
) -> int:
    count = 0
    for account_id in ids:
        account = db.query(OpAccount).filter(OpAccount.id == account_id).first()
        if not account:
            continue
        old_status = account.status
        account.status = status
        _write_audit_log(db, account.id, "update", field_name="status",
                         old_value=str(old_status), new_value=str(status))
        if status == "已售":
            if sale_customer is not None:
                account.sale_customer = sale_customer
                _write_audit_log(db, account.id, "update", field_name="sale_customer",
                                 old_value=None, new_value=str(sale_customer))
            if sale_price is not None:
                account.sale_price = sale_price
                _write_audit_log(db, account.id, "update", field_name="sale_price",
                                 old_value=None, new_value=str(sale_price))
            if sale_date is not None:
                account.sale_date = sale_date
                _write_audit_log(db, account.id, "update", field_name="sale_date",
                                 old_value=None, new_value=str(sale_date))
            if sellers is not None:
                account.sellers = _serialize_sellers(sellers)
                _write_audit_log(db, account.id, "update", field_name="sellers",
                                 old_value=None, new_value=str(sellers))
        count += 1
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORT_COLUMNS = [
    "account", "platform", "password", "totp_secret", "email", "email_password",
    "email_login_url", "phone", "phone_manage_url", "country", "source", "tags",
    "remark", "status", "registrant", "operator", "tiktok_mid_video",
    "tiktok_showcase", "tiktok_phone_live", "tiktok_partner_live",
    "purchase_channel", "purchase_price", "purchase_date",
    "sale_customer", "sale_price", "sale_date", "platform_user_id",
    "platform_sec_uid", "nickname", "follower_count", "following_count",
    "like_count", "video_count", "last_collected_at", "collect_status",
]


def export_op_accounts(db: Session, filters: dict, format: str = "csv") -> bytes:
    items, _ = list_op_accounts(db, **filters, skip=0, limit=999999)

    if format == "xlsx":
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl is required for xlsx export")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(_EXPORT_COLUMNS)
        for acc in items:
            ws.append([str(getattr(acc, col, "") or "") for col in _EXPORT_COLUMNS])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # Default: CSV with UTF-8 BOM
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for acc in items:
        writer.writerow([str(getattr(acc, col, "") or "") for col in _EXPORT_COLUMNS])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

def import_from_csv(db: Session, csv_content: str) -> OpImportResult:
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = []
    total = success = duplicates = failed = 0

    for row in reader:
        total += 1
        account_val = (row.get("account") or "").strip()
        platform_val = (row.get("platform") or "").strip()

        if not account_val or not platform_val:
            rows.append({**row, "_result": "failed", "_reason": "missing account or platform"})
            failed += 1
            continue

        existing = (
            db.query(OpAccount)
            .filter(
                OpAccount.platform == platform_val,
                OpAccount.account == account_val,
            )
            .first()
        )
        if existing:
            rows.append({**row, "_result": "duplicate"})
            duplicates += 1
            continue

        try:
            create_data = OpAccountCreate(
                platform=platform_val,
                account=account_val,
                password=row.get("password") or None,
                totp_secret=row.get("totp_secret") or None,
                email=row.get("email") or None,
                email_password=row.get("email_password") or None,
                email_login_url=row.get("email_login_url") or None,
                phone=row.get("phone") or None,
                phone_manage_url=row.get("phone_manage_url") or None,
                country=row.get("country") or None,
                source=row.get("source") or None,
                tags=row.get("tags") or None,
                remark=row.get("remark") or None,
                status=row.get("status") or "正常",
                registrant=row.get("registrant") or None,
                operator=row.get("operator") or None,
                purchase_channel=row.get("purchase_channel") or None,
                purchase_price=row.get("purchase_price") or None,
                purchase_date=row.get("purchase_date") or None,
                sale_customer=row.get("sale_customer") or None,
                sale_price=row.get("sale_price") or None,
                sale_date=row.get("sale_date") or None,
            )
            acc = create_op_account(db, create_data)
            rows.append({**row, "_result": "success", "_id": acc.id})
            success += 1
        except Exception as e:
            db.rollback()
            rows.append({**row, "_result": "failed", "_reason": str(e)})
            failed += 1

    return OpImportResult(total=total, success=success, duplicates=duplicates, failed=failed, rows=rows)


# ---------------------------------------------------------------------------
# Collect task scheduling
# ---------------------------------------------------------------------------

def trigger_collect(db: Session, account_ids: list, background_tasks: BackgroundTasks) -> str:
    task_id = str(uuid.uuid4())
    task = OpCollectTask(
        id=task_id,
        status="running",
        total=len(account_ids),
        completed=0,
        success=0,
        failed=0,
    )
    db.add(task)
    db.commit()
    background_tasks.add_task(run_collect_task, task_id, account_ids)
    return task_id


def get_collect_task(db: Session, task_id: str) -> Optional[OpCollectTask]:
    return db.query(OpCollectTask).filter(OpCollectTask.id == task_id).first()


# ---------------------------------------------------------------------------
# Background collect runner
# ---------------------------------------------------------------------------

def run_collect_task(task_id: str, account_ids: list) -> None:
    """Synchronous background task executed by FastAPI BackgroundTasks."""
    from app.services.op_collector_service import collect_account, select_proxy

    db: Session = SessionLocal()
    try:
        proxy = select_proxy(db)
        for account_id in account_ids:
            account = db.query(OpAccount).filter(OpAccount.id == account_id).first()
            if not account:
                _increment_task(db, task_id, success=False)
                continue
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ok = loop.run_until_complete(collect_account(db, account, proxy))
                finally:
                    loop.close()
                _increment_task(db, task_id, success=ok)
            except Exception as e:
                logger.error(f"run_collect_task: error collecting account {account_id}: {e}")
                _increment_task(db, task_id, success=False)

        task = db.query(OpCollectTask).filter(OpCollectTask.id == task_id).first()
        if task:
            task.status = "completed"
            db.commit()
    except Exception as e:
        logger.error(f"run_collect_task fatal error: {e}")
        try:
            task = db.query(OpCollectTask).filter(OpCollectTask.id == task_id).first()
            if task:
                task.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _increment_task(db: Session, task_id: str, success: bool) -> None:
    task = db.query(OpCollectTask).filter(OpCollectTask.id == task_id).first()
    if task:
        task.completed += 1
        if success:
            task.success += 1
        else:
            task.failed += 1
        db.commit()


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

def get_audit_logs(db: Session, account_id: int) -> list:
    return (
        db.query(OpAuditLog)
        .filter(OpAuditLog.op_account_id == account_id)
        .order_by(OpAuditLog.created_at.desc())
        .all()
    )
