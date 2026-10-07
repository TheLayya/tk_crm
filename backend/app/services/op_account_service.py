import csv
import io
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, List, Optional, cast

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from app.services.table_query_service import apply_table_query, model_table_fields
from sqlalchemy.orm.attributes import set_committed_value

from app.core.database import SessionLocal
from app.models.op_account import OpAccount, OpAuditLog, OpCollectTask
from app.models.device import Device
from app.models.team import User
from app.services.sale_validation_service import validate_sale_information
from app.services.asset_scope_service import require_op_account_scope, scoped_op_accounts
from app.schemas.op_account import (
    OpAccountCreate,
    OpAccountUpdate,
    OpImportResult,
)

logger = logging.getLogger(__name__)
_set_committed_value = cast(Callable[[object, str, object], None], set_committed_value)


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
    old_value: str | int | None = None,
    new_value: str | int | None = None,
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
    if field_name == "status" and new_value == "封禁" and old_value != new_value:
        account = db.get(OpAccount, account_id)
        if account:
            record_relation_snapshot(db, account, operator, "ban_snapshot")


def record_relation_snapshot(db: Session, account: OpAccount, operator: str | None = None, field_name: str = "relation_snapshot") -> None:
    from app.services.relation_history_service import account_relation_snapshot

    _write_audit_log(db, account.id, "snapshot", field_name, None,
                     json.dumps(account_relation_snapshot(db, account), ensure_ascii=False), operator)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def normalize_account_relation(db: Session, values: dict[str, Any], account: Optional[OpAccount] = None) -> None:
    """账号节点随终端绑定，账号操作不修改终端节点。"""
    from fastapi import HTTPException
    from app.models.device import Device
    from app.models.proxy_node import ProxyNode

    device_id = values.get('device_id', account.device_id if account else None)
    node_id = values.get('node_id', account.node_id if account else None)
    if device_id is not None:
        device = db.query(Device).filter(Device.id == device_id, Device.is_deleted == False).first()
        if not device:
            raise HTTPException(404, "终端不存在或已删除")
        if device.device_type != "phone":
            raise HTTPException(409, "运营账号只能绑定手机终端")
        # 一个手机终端允许绑定多个运营账号；保留同一账号自身的关联校验即可。
        ids = device.node_ids or ([device.node_id] if device.node_id else [])
        primary = ids[0] if ids else None
        if values.get('node_id') is not None and values['node_id'] != primary:
            raise HTTPException(409, "账号节点由终端管理，请在终端中修改节点")
        values['node_id'] = primary
    else:
        # 解除终端时不保留原本继承的节点。
        if account and account.device_id and 'node_id' not in values:
            node_id = None
            values['node_id'] = None
        if node_id is not None:
            node = db.query(ProxyNode).filter(ProxyNode.id == node_id).first()
            if not node:
                raise HTTPException(404, "代理节点不存在")
            if node.status not in ("idle", "active"):
                raise HTTPException(409, "代理节点当前状态不可绑定")


def sync_device_account_nodes(db: Session, device: Device, operator: str | None = None) -> None:
    """终端关系变更后同步账号的节点摘要。"""
    ids = device.node_ids or ([device.node_id] if device.node_id else [])
    primary = ids[0] if ids else None
    for account in db.query(OpAccount).filter(OpAccount.device_id == device.id).all():
        if account.device_id != device.id:
            continue
        if account.node_id != primary:
            _write_audit_log(db, account.id, "update", "node_id", str(account.node_id) if account.node_id else None, str(primary) if primary else None, operator)
            account.node_id = primary
        record_relation_snapshot(db, account, operator)


def create_op_account(db: Session, data: OpAccountCreate, actor: str | None = None) -> OpAccount:
    # Prevent duplicate operation accounts even when no project is selected
    existing = db.query(OpAccount).filter(
        OpAccount.platform == data.platform,
        OpAccount.account == data.account,
    ).first()
    if existing:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="该平台账号已存在")
    data_dict = data.model_dump()
    validate_sale_information(data_dict, "已售", require_date=True)
    normalize_account_relation(db, data_dict)
    # 序列化 sellers 列表为 JSON 字符串
    data_dict['sellers'] = _serialize_sellers(data_dict.get('sellers'))
    account = OpAccount(**data_dict)
    db.add(account)
    db.commit()
    db.refresh(account)
    _write_audit_log(db, account.id, "create", field_name=None, old_value=None, new_value="created", operator=actor)
    for field in ("device_id", "node_id"):
        if getattr(account, field) is not None:
            _write_audit_log(db, account.id, "update", field, None, str(getattr(account, field)), actor)
    record_relation_snapshot(db, account, actor)
    if account.status == "封禁":
        record_relation_snapshot(db, account, actor, "ban_snapshot")
    db.commit()
    # 反序列化 sellers 供返回
    return account


def get_op_account(db: Session, id: int) -> Optional[OpAccount]:
    account = db.query(OpAccount).filter(OpAccount.id == id).first()
    return account


def update_op_account(db: Session, id: int, data: OpAccountUpdate, actor: str | None = None) -> Optional[OpAccount]:
    account = db.query(OpAccount).filter(OpAccount.id == id).first()
    if not account:
        return None
    update_data = data.model_dump(exclude_unset=True)
    identity_changed = any(
        field in update_data and update_data[field] != getattr(account, field)
        for field in ("account", "platform")
    )
    validate_sale_information({**{field: getattr(account, field) for field in ("status", "sale_customer", "sale_price", "sale_date", "sellers")}, **update_data}, "已售", require_date=True)
    if {'device_id', 'node_id'} & update_data.keys():
        normalize_account_relation(db, update_data, account)
    if 'sellers' in update_data:
        update_data['sellers'] = _serialize_sellers(update_data['sellers'])
    for field, new_val in sorted(update_data.items(), key=lambda item: item[0] == "status"):
        old_val = getattr(account, field, None)
        if old_val != new_val:
            _write_audit_log(
                db, account.id, "update",
                field_name=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                operator=actor,
            )
            setattr(account, field, new_val)
    if identity_changed:
        # A SEC_UID belongs to the collected identity, not the row's new name.
        account.platform_user_id = None
        account.platform_sec_uid = None
        account.follower_count = None
        account.previous_follower_count = None
        account.last_collected_at = None
        account.video_collected_at = None
        account.last_attempt_at = None
        account.next_attempt_at = None
        account.collect_retry_count = 0
        account.collect_status = "pending"
        account.collect_error = None
    if {'device_id', 'node_id'} & update_data.keys():
        record_relation_snapshot(db, account, actor)
    db.commit()
    db.refresh(account)
    return account


def delete_op_account(db: Session, id: int) -> bool:
    account = get_op_account(db, id)
    if not account:
        return False
    from app.models.op_account import EmailAccountRelation
    if db.query(EmailAccountRelation).filter_by(op_account_id=id).first():
        raise HTTPException(status_code=409, detail="该账号已有邮箱关联历史，请保留账号以便追溯")
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
    limit: Optional[int] = 50,
    current_user: Optional[User] = None,
    exclude_gmail: bool = False,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    table_filters: object = None,
) -> tuple[list[OpAccount], int]:
    query = scoped_op_accounts(db, current_user) if current_user is not None else db.query(OpAccount)
    if exclude_gmail:
        query = query.filter(OpAccount.platform != "gmail")
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
    fields = model_table_fields(OpAccount, exclude=("password", "totp_secret", "email_password", "project_id", "previous_follower_count"))
    query = apply_table_query(query, fields, sort_by, sort_order, table_filters,
                              stable_column=OpAccount.id, default_sort=(OpAccount.id, "asc"))
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    # 反序列化每条记录的 sellers
    for item in items:
        _set_committed_value(item, "sellers", _deserialize_sellers(item.sellers))
    return items, total


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_op_account_stats(db: Session, exclude_gmail: bool = False, current_user: Optional[User] = None) -> dict[str, Any]:
    """
    统计运营账号的汇总数据：总数、各状态数量、总采购成本、总出售收入、净收益。
    """
    from decimal import Decimal
    from sqlalchemy import func

    query = scoped_op_accounts(db, current_user) if current_user is not None else db.query(OpAccount)
    if exclude_gmail:
        query = query.filter(OpAccount.platform != "gmail")
    total = query.count()

    # 各状态数量
    status_rows = (
        query.with_entities(OpAccount.status, func.count(OpAccount.id))
        .group_by(OpAccount.status)
        .all()
    )
    by_status = {"正常": 0, "自用": 0, "封禁": 0, "已售": 0}
    for status_val, cnt in status_rows:
        if status_val in by_status:
            by_status[status_val] = cnt

    # 各平台数量
    platform_rows = (
        query.with_entities(OpAccount.platform, func.count(OpAccount.id))
        .group_by(OpAccount.platform)
        .all()
    )
    by_platform = {}
    for platform_val, cnt in platform_rows:
        by_platform[platform_val] = cnt

    # 成本与收益
    purchase_sum = query.with_entities(func.sum(OpAccount.purchase_price)).scalar() or Decimal("0")
    sale_sum = query.with_entities(func.sum(OpAccount.sale_price)).scalar() or Decimal("0")
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
    ids: list[int],
    status: str,
    sale_customer: Optional[str] = None,
    sale_price: Decimal | None = None,
    sale_date: date | None = None,
    sellers: Optional[List[str]] = None,
    actor: str | None = None,
) -> int:
    validate_sale_information(dict(status=status, sale_customer=sale_customer, sale_price=sale_price, sale_date=sale_date, sellers=sellers), "已售", require_date=True)
    count = 0
    for account_id in ids:
        account = db.query(OpAccount).filter(OpAccount.id == account_id).first()
        if not account:
            continue
        old_status = account.status
        account.status = status
        _write_audit_log(db, account.id, "update", field_name="status",
                         old_value=str(old_status), new_value=str(status), operator=actor)
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


def batch_assign_operator(db: Session, ids: list[int], operator: str, current_user: User) -> int:
    member = db.query(User).filter(User.username == operator, User.is_active == True).first()
    if not member:
        raise HTTPException(status_code=422, detail="请选择存在且已启用的成员")
    account_ids = set(ids)
    accounts = db.query(OpAccount).filter(OpAccount.id.in_(account_ids)).all()
    if not account_ids or len(accounts) != len(account_ids):
        raise HTTPException(status_code=404, detail="部分运营账号不存在，请刷新后重试")
    require_op_account_scope(db, [account.id for account in accounts], current_user)

    count = 0
    for account in accounts:
        if account.operator == member.username:
            continue
        old_operator = account.operator
        account.operator = member.username
        _write_audit_log(db, account.id, "update", field_name="operator",
                         old_value=old_operator, new_value=member.username,
                         operator=current_user.username)
        count += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return count


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORT_COLUMNS = [
    "account", "platform", "password", "totp_secret", "recovery_email", "account_created_at", "account_created_year", "email", "email_password",
    "email_login_url", "phone", "phone_manage_url", "country", "source", "tags",
    "remark", "status", "registrant", "operator", "tiktok_mid_video",
    "tiktok_showcase", "tiktok_phone_live", "tiktok_partner_live",
    "purchase_channel", "purchase_price", "purchase_date",
    "sale_customer", "sale_price", "sale_date", "platform_user_id",
    "platform_sec_uid", "nickname", "follower_count", "following_count",
    "like_count", "video_count", "last_collected_at", "collect_status",
    "gmail_check_status", "gmail_check_raw_status", "gmail_checked_at",
]

# 对外文件使用中文表头；导入同时兼容这些中文表头和历史英文表头。
_COLUMN_LABELS = {
    "account": "账号", "platform": "平台", "password": "密码", "totp_secret": "双重验证码密钥",
    "recovery_email": "辅助邮箱", "account_created_at": "注册时间", "account_created_year": "注册年份", "email": "绑定邮箱", "email_password": "邮箱密码", "email_login_url": "邮箱登录地址",
    "phone": "绑定手机", "phone_manage_url": "手机管理链接", "country": "国家/地区",
    "source": "账号来源", "tags": "标签", "remark": "备注", "status": "状态",
    "registrant": "注册人", "operator": "使用人", "tiktok_mid_video": "中视频",
    "tiktok_showcase": "橱窗", "tiktok_phone_live": "手机直播", "tiktok_partner_live": "伴侣直播",
    "purchase_channel": "采购渠道", "purchase_price": "采购金额", "purchase_date": "采购日期",
    "sale_customer": "出售客户", "sale_price": "出售金额", "sale_date": "出售日期",
    "platform_user_id": "平台用户ID", "platform_sec_uid": "平台SEC_UID", "nickname": "昵称",
    "follower_count": "粉丝数", "following_count": "关注数", "like_count": "点赞数",
    "video_count": "视频数", "last_collected_at": "最后采集时间", "collect_status": "采集状态",
    "gmail_check_status": "Gmail检测结果", "gmail_check_raw_status": "Gmail原始结果", "gmail_checked_at": "Gmail最后检测时间",
}
_IMPORT_ALIASES = {label: key for key, label in _COLUMN_LABELS.items()}
_IMPORT_ALIASES.update({key: key for key in _EXPORT_COLUMNS})

_IMPORT_COLUMNS = [
    "account", "platform", "password", "totp_secret", "recovery_email", "account_created_at", "account_created_year", "email", "email_password", "email_login_url",
    "phone", "phone_manage_url", "country", "source", "tags", "remark", "status", "registrant", "operator",
    "tiktok_mid_video", "tiktok_showcase", "tiktok_phone_live", "tiktok_partner_live",
    "purchase_channel", "purchase_price", "purchase_date", "sale_customer", "sale_price", "sale_date",
]


def create_import_template() -> bytes:
    """生成面向中文用户的 Excel 导入示例模板。"""
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise RuntimeError("生成 Excel 模板需要安装 openpyxl") from exc

    from openpyxl.utils.cell import get_column_letter
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "运营账号导入"
    headers = [_COLUMN_LABELS[column] for column in _IMPORT_COLUMNS]
    sample = {
        "account": "demo_account", "platform": "TikTok", "country": "美国", "source": "示例",
        "remark": "这是示例行，导入前请删除或替换", "status": "正常", "tiktok_mid_video": "否",
        "tiktok_showcase": "否", "tiktok_phone_live": "否", "tiktok_partner_live": "否",
    }
    sheet.append(headers)
    sheet.append([sample.get(column, "") for column in _IMPORT_COLUMNS])
    sheet.freeze_panes = "A2"
    header_fill = PatternFill("solid", fgColor="409EFF")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for index, header in enumerate(headers, 1):
        sheet.column_dimensions[get_column_letter(index)].width = max(12, min(24, len(header) * 2 + 4))

    notes = workbook.create_sheet("填写说明")
    notes.append(["字段", "是否必填", "填写说明"])
    notes.append(["账号", "是", "平台账号名，例如 demo_account"])
    notes.append(["平台", "是", "TikTok、YouTube、Instagram、Facebook 或 Gmail"])
    notes.append(["状态", "否", "正常、自用、封禁或已售；不填默认为正常"])
    notes.append(["中视频/橱窗/手机直播/伴侣直播", "否", "填写“是”或“否”"])
    notes.append(["采购日期/出售日期", "否", "格式：YYYY-MM-DD，例如 2026-09-14"])
    notes.append(["其他字段", "否", "没有内容时保持空白；不要修改第一行字段名"])
    notes.freeze_panes = "A2"
    notes.column_dimensions["A"].width = 34
    notes.column_dimensions["B"].width = 12
    notes.column_dimensions["C"].width = 64
    for cell in notes[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_op_accounts(db: Session, filters: dict[str, Any], format: str = "csv", localized: bool = False, current_user: Optional[User] = None) -> bytes:
    items, _ = list_op_accounts(db, **filters, skip=0, limit=999999, current_user=current_user)
    columns = [_COLUMN_LABELS.get(col, col) for col in _EXPORT_COLUMNS] if localized else _EXPORT_COLUMNS

    if format == "xlsx":
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl is required for xlsx export")
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(columns)
        for acc in items:
            ws.append([str(getattr(acc, col, "") or "") for col in _EXPORT_COLUMNS])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # Default: CSV with UTF-8 BOM
    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow(columns)
    for acc in items:
        writer.writerow([str(getattr(acc, col, "") or "") for col in _EXPORT_COLUMNS])
    return ("\ufeff" + text_buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------

def _parse_import_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "有"}


def _optional_import_value(value: str) -> Optional[str]:
    value = (value or "").strip()
    return None if value.lower() in {"", "null", "none", "nil", "无", "空", "-"} else value


def parse_email_import_line(line: str, import_format: str = "auto", delimiter: str = "auto") -> dict[str, Any]:
    pattern = {"----": r"----", "|": r"\|", ":": r":"}.get(delimiter, r"----|\||:")
    separator = re.search(pattern, line)
    if not separator:
        raise ValueError("未找到邮箱字段分隔符")
    delimiter = separator.group()
    if delimiter == "----":
        values = line.split(delimiter)
    else:
        values = next(csv.reader([line], delimiter=delimiter, strict=True))
    if import_format == "credentials_3" and len(values) != 3:
        raise ValueError("当前格式需要三项：邮箱、密码、2FA")
    if import_format == "credentials_4" and len(values) != 4:
        raise ValueError("当前格式需要四项：邮箱、密码、辅助邮箱、2FA")
    if import_format == "full_6" and (len(values) < 6 or (delimiter != ":" and len(values) != 6)):
        raise ValueError("当前格式需要六项：邮箱、密码、辅助邮箱、2FA、注册时间、国家")
    if len(values) == 3:
        account, password, totp_secret = values
        recovery_email = ""
        registered = country = ""
    elif len(values) == 4:
        account, password, recovery_email, totp_secret = values
        registered = country = ""
    else:
        if len(values) < 6 or (delimiter != ":" and len(values) != 6):
            raise ValueError("需要三、四或六个邮箱字段")
        account, password, recovery_email, totp_secret = values[:4]
        registered = ":".join(values[4:-1]).strip()
        country = values[-1].strip()
    account = account.strip().lower()
    if not re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", account):
        raise ValueError("邮箱地址无效")
    registered_value: datetime | str | None = registered
    registered_year = None
    if registered:
        if re.fullmatch(r"\d{4}", registered):
            registered_year = int(registered)
            if not 1 <= registered_year <= 9999:
                raise ValueError("注册年份无效")
            registered_value = None
        else:
            registered_value = datetime.fromisoformat(registered)
    return dict(account=account, password=password or None,
                recovery_email=_optional_import_value(recovery_email), totp_secret=totp_secret.strip() or None,
                account_created_at=registered_value or None, account_created_year=registered_year, country=country or None)


def import_gmail_text(db: Session, content: str, actor: str | None = None) -> OpImportResult:
    rows = []
    success = duplicates = failed = 0
    for line_number, line in enumerate(content.lstrip("\ufeff").splitlines(), 1):
        if not line.strip():
            continue
        result = {"platform": "gmail", "line": line_number}
        try:
            values = parse_email_import_line(line)
            account = values["account"]
            result["account"] = account
            if not re.fullmatch(r"[a-z0-9._%+\-]+@gmail\.com", account):
                raise ValueError("邮箱必须是完整 Gmail 地址")
            if db.query(OpAccount).filter_by(platform="gmail", account=account).first():
                result["_result"] = "duplicate"
                duplicates += 1
            else:
                account = create_op_account(db, OpAccountCreate(
                    platform="gmail", **values, registrant=actor,
                ), actor=actor)
                result.update(_result="success", _id=account.id)
                success += 1
        except (ValueError, csv.Error):
            db.rollback()
            result.update(_result="failed", _reason="无法识别此行：支持 |、----、: 分隔三、四或六字段；注册时间可只填年份。请检查字段数量、邮箱或时间是否有效。")
            failed += 1
        except Exception:
            db.rollback()
            result.update(_result="failed", _reason="保存失败，请检查是否重复或稍后重试")
            failed += 1
        rows.append(result)
    if not rows:
        raise ValueError("请输入至少一行 Gmail 账号")
    return OpImportResult(total=len(rows), success=success, duplicates=duplicates, failed=failed, rows=rows)


def import_from_csv(
    db: Session,
    csv_content: str,
    actor: Optional[str] = None,
    force_actor: bool = False,
) -> OpImportResult:
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = []
    total = success = duplicates = failed = 0

    for row in reader:
        total += 1
        # 将中文表头转换为内部字段名，保留未知列以便在结果中提示。
        row = {_IMPORT_ALIASES.get(str(key).strip(), str(key).strip()): value for key, value in row.items()}
        account_val = (row.get("account") or "").strip()
        platform_val = (row.get("platform") or "").strip()
        platform_val = {"TikTok": "tiktok", "YouTube": "youtube", "Instagram": "instagram", "Facebook": "facebook", "Google": "gmail", "Gmail": "gmail", "谷歌邮箱": "gmail"}.get(platform_val, platform_val.lower())

        if not account_val or not platform_val:
            rows.append({**row, "_result": "failed", "_reason": "缺少账号或平台"})
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
                platform=cast(Any, platform_val),
                account=account_val,
                password=row.get("password") or None,
                totp_secret=row.get("totp_secret") or None,
                recovery_email=row.get("recovery_email") or None,
                account_created_at=cast(Any, row.get("account_created_at") or None),
                account_created_year=cast(Any, row.get("account_created_year") or None),
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
                registrant=actor if force_actor else (row.get("registrant") or actor),
                operator=row.get("operator") or None,
                purchase_channel=row.get("purchase_channel") or None,
                purchase_price=cast(Any, row.get("purchase_price") or None),
                purchase_date=cast(Any, row.get("purchase_date") or None),
                sale_customer=row.get("sale_customer") or None,
                sale_price=cast(Any, row.get("sale_price") or None),
                sale_date=cast(Any, row.get("sale_date") or None),
                tiktok_mid_video=_parse_import_bool(row.get("tiktok_mid_video")),
                tiktok_showcase=_parse_import_bool(row.get("tiktok_showcase")),
                tiktok_phone_live=_parse_import_bool(row.get("tiktok_phone_live")),
                tiktok_partner_live=_parse_import_bool(row.get("tiktok_partner_live")),
            )
            acc = create_op_account(db, create_data, actor=actor)
            rows.append({**row, "_result": "success", "_id": acc.id})
            success += 1
        except Exception as e:
            db.rollback()
            rows.append({**row, "_result": "failed", "_reason": str(e)})
            failed += 1

    return OpImportResult(total=total, success=success, duplicates=duplicates, failed=failed, rows=rows)


def import_from_excel(
    db: Session,
    file_content: bytes,
    actor: Optional[str] = None,
    force_actor: bool = False,
) -> OpImportResult:
    """Import the same columns produced by export_op_accounts from an Excel file."""
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for Excel import") from exc

    workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        assert sheet is not None
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not rows:
        raise ValueError("Excel file appears to be empty")

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    headers = [_IMPORT_ALIASES.get(header, header) for header in headers]
    if "account" not in headers or "platform" not in headers:
        raise ValueError("Excel 文件必须包含“账号（account）”和“平台（platform）”列")
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=headers)
    writer.writeheader()
    for values in rows[1:]:
        writer.writerow({header: (values[index] if index < len(values) and values[index] is not None else "")
                         for index, header in enumerate(headers)})
    return import_from_csv(
        db,
        csv_content=csv_buffer.getvalue(),
        actor=actor,
        force_actor=force_actor,
    )


# ---------------------------------------------------------------------------
# Collect task scheduling
# ---------------------------------------------------------------------------

async def run_scheduled_collections(db_factory: Callable[[], Session]) -> None:
    """定时采集到期的运营账号；间隔使用系统 MonitorSettings.default_interval。"""
    from app.models.monitor import MonitorSettings
    from app.services.op_collector_service import collect_account, select_proxy

    db: Session = db_factory()
    try:
        settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
        interval = settings.default_interval if settings else 14400
        now = datetime.utcnow()
        accounts = (
            db.query(OpAccount)
            .filter(OpAccount.platform == "tiktok", OpAccount.status.notin_(["已售", "封禁"]))
            .all()
        )
        due_accounts = []
        for account in accounts:
            last_attempt = (account.last_attempt_at or account.updated_at) if account.collect_status == "failed" else account.last_collected_at
            if account.next_attempt_at is not None:
                due = now >= account.next_attempt_at
            else:
                due = (last_attempt is None or now >= last_attempt + timedelta(seconds=interval)
                       or (account.video_collected_at is None and account.collect_status != "failed"))
            if due:
                due_accounts.append(account)
        if not due_accounts:
            return

        logger.info("Scheduled op-account collection: %d accounts due", len(due_accounts))
        for account in due_accounts:
            account_id = account.id
            try:
                await collect_account(db, account, select_proxy(db), scheduled=True)
            except Exception:
                db.rollback()
                logger.exception("Scheduled collection failed for op account %s", account_id)
    finally:
        db.close()


def register_scheduler_job(scheduler: Any, db_factory: Callable[[], Session]) -> None:
    """每分钟触发一次，到期账号才真正执行采集。"""
    async def _job() -> None:
        await run_scheduled_collections(db_factory)

    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=1,
        id="scheduled_op_account_collections",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Registered scheduled op-account collection job (every minute)")


def trigger_collect(db: Session, account_ids: list[int], background_tasks: BackgroundTasks, actor: str | None = None) -> str:
    account_ids = list(dict.fromkeys(account_ids))
    task_id = str(uuid.uuid4())
    task = OpCollectTask(
        id=task_id,
        status="running",
        total=len(account_ids),
        completed=0,
        success=0,
        failed=0,
        created_by=actor,
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

def run_collect_task(task_id: str, account_ids: list[int]) -> None:
    """Synchronous background task executed by FastAPI BackgroundTasks."""
    from app.services.op_collector_service import collect_account, select_proxy

    db: Session = SessionLocal()
    try:
        task = db.get(OpCollectTask, task_id)
        if task is None or task.status != "running":
            return
        for account_id in dict.fromkeys(account_ids):
            account = db.query(OpAccount).filter(OpAccount.id == account_id).first()
            if not account:
                _increment_task(db, task_id, success=False)
                continue
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ok = loop.run_until_complete(collect_account(db, account, select_proxy(db)))
                finally:
                    loop.close()
                _increment_task(db, task_id, success=ok)
            except Exception as e:
                db.rollback()
                logger.error(f"run_collect_task: error collecting account {account_id}: {e}")
                _increment_task(db, task_id, success=False)

        task = db.query(OpCollectTask).filter(OpCollectTask.id == task_id).first()
        if task:
            task.status = "completed"
            db.commit()
    except Exception as e:
        logger.error(f"run_collect_task fatal error: {e}")
        try:
            db.rollback()
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
    if task and task.status == "running" and task.completed < task.total:
        task.completed += 1
        if success:
            task.success += 1
        else:
            task.failed += 1
        db.commit()


def recover_interrupted_collections(db: Session, started_at: datetime | None = None) -> None:
    """Call once before starting this single-worker process's scheduler."""
    from app.models.monitor import MonitorSettings
    from app.services.op_collector_service import schedule_collection_result

    now = started_at or datetime.utcnow()
    settings = db.query(MonitorSettings).filter(MonitorSettings.id == 1).first()
    interval = settings.default_interval if settings else 14400
    for task in db.query(OpCollectTask).filter(OpCollectTask.status == "running", OpCollectTask.created_at <= now).all():
        task.failed += max(0, task.total - task.completed)
        task.completed = task.total
        task.status = "failed"
    for account in db.query(OpAccount).filter(
        OpAccount.collect_status == "pending", OpAccount.last_attempt_at.isnot(None),
        OpAccount.last_attempt_at <= now,
    ).all():
        account.collect_status = "failed"
        account.collect_error = "COLLECTION_INTERRUPTED: 上次采集因服务重启中断，将自动重试"
        schedule_collection_result(account, interval, now, False)
    db.commit()


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

def get_audit_logs(db: Session, account_id: int) -> list[OpAuditLog]:
    return (
        db.query(OpAuditLog)
        .filter(OpAuditLog.op_account_id == account_id)
        .order_by(OpAuditLog.created_at.desc())
        .all()
    )
