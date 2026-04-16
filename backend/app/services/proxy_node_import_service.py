"""
代理节点批量导入服务层

支持 CSV 和 Excel (.xlsx) 格式的批量导入，以及模板文件生成。
"""
import csv
import io
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

import openpyxl
from sqlalchemy.orm import Session

from app.schemas.proxy_node import ProxyNodeCreate, ProxyNodeImportResult
from app.services.proxy_node_service import create_node

logger = logging.getLogger(__name__)

# 支持的列名（全部小写）
SUPPORTED_COLUMNS = [
    "ip", "port", "username", "password", "protocol",
    "relay_ip", "relay_port", "relay_protocol",
    "purchase_date", "purchase_price", "purchase_channel",
    "expire_date", "sale_customer", "sale_price",
    "status", "usage", "remark",
]

# 枚举合法值
VALID_PROTOCOL = {"socks5", "http", "https"}
VALID_STATUS = {"active", "expired", "sold", "disabled"}
VALID_USAGE = {"self", "rented", "idle"}

# 模板示例数据
_TEMPLATE_EXAMPLE = {
    "ip": "1.2.3.4",
    "port": "1080",
    "username": "user",
    "password": "pass",
    "protocol": "socks5",
    "relay_ip": "",
    "relay_port": "",
    "relay_protocol": "",
    "purchase_date": "2026-01-01",
    "purchase_price": "10.00",
    "purchase_channel": "供应商A",
    "expire_date": "2026-12-31",
    "sale_customer": "",
    "sale_price": "",
    "status": "active",
    "usage": "idle",
    "remark": "示例节点",
}


def _parse_date(value: str) -> Optional[date]:
    """将 YYYY-MM-DD 格式字符串转换为 date 对象，空字符串返回 None。"""
    if not value or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _parse_decimal(value: str) -> Optional[Decimal]:
    """将字符串转换为 Decimal，空字符串返回 None。"""
    if not value or not value.strip():
        return None
    return Decimal(value.strip())


def _parse_int(value: str) -> Optional[int]:
    """将字符串转换为整数，空字符串返回 None。"""
    if not value or not value.strip():
        return None
    return int(value.strip())


def _validate_row(
    row_dict: dict, line_num: int
) -> Tuple[Optional[ProxyNodeCreate], Optional[str]]:
    """
    验证单行数据，返回 (ProxyNodeCreate, None) 或 (None, error_str)。

    列名识别不区分大小写（统一转小写处理）。
    """
    # 统一转小写键名
    row = {k.lower().strip(): (str(v).strip() if v is not None else "") for k, v in row_dict.items()}

    # --- 必填字段验证 ---
    ip = row.get("ip", "")
    if not ip:
        return None, f"第 {line_num} 行: ip 不能为空"

    port_str = row.get("port", "")
    if not port_str:
        return None, f"第 {line_num} 行: port 不能为空"

    try:
        port = int(port_str)
    except ValueError:
        return None, f"第 {line_num} 行: port 必须是 1-65535 之间的整数"

    if not (1 <= port <= 65535):
        return None, f"第 {line_num} 行: port 必须是 1-65535 之间的整数"

    # --- 枚举字段验证 ---
    protocol_str = row.get("protocol", "")
    if protocol_str and protocol_str not in VALID_PROTOCOL:
        return None, (
            f"第 {line_num} 行: protocol 值 '{protocol_str}' 不合法，"
            f"允许值为 socks5/http/https"
        )

    relay_protocol_str = row.get("relay_protocol", "")
    if relay_protocol_str and relay_protocol_str not in VALID_PROTOCOL:
        return None, (
            f"第 {line_num} 行: relay_protocol 值 '{relay_protocol_str}' 不合法，"
            f"允许值为 socks5/http/https"
        )

    status_str = row.get("status", "")
    if status_str and status_str not in VALID_STATUS:
        return None, (
            f"第 {line_num} 行: status 值 '{status_str}' 不合法，"
            f"允许值为 active/expired/sold/disabled"
        )

    usage_str = row.get("usage", "")
    if usage_str and usage_str not in VALID_USAGE:
        return None, (
            f"第 {line_num} 行: usage 值 '{usage_str}' 不合法，"
            f"允许值为 self/rented/idle"
        )

    # --- relay_port 验证 ---
    relay_port_str = row.get("relay_port", "")
    relay_port: Optional[int] = None
    if relay_port_str:
        try:
            relay_port = int(relay_port_str)
        except ValueError:
            return None, f"第 {line_num} 行: relay_port 必须是 1-65535 之间的整数"
        if not (1 <= relay_port <= 65535):
            return None, f"第 {line_num} 行: relay_port 必须是 1-65535 之间的整数"

    # --- 日期字段解析 ---
    try:
        purchase_date = _parse_date(row.get("purchase_date", ""))
    except ValueError:
        return None, f"第 {line_num} 行: purchase_date 格式不正确，应为 YYYY-MM-DD"

    try:
        expire_date = _parse_date(row.get("expire_date", ""))
    except ValueError:
        return None, f"第 {line_num} 行: expire_date 格式不正确，应为 YYYY-MM-DD"

    # --- 数值字段解析 ---
    try:
        purchase_price = _parse_decimal(row.get("purchase_price", ""))
    except InvalidOperation:
        return None, f"第 {line_num} 行: purchase_price 格式不正确，应为数字"

    try:
        sale_price = _parse_decimal(row.get("sale_price", ""))
    except InvalidOperation:
        return None, f"第 {line_num} 行: sale_price 格式不正确，应为数字"

    # --- 构建 ProxyNodeCreate ---
    create_data = ProxyNodeCreate(
        ip=ip,
        port=port,
        username=row.get("username") or None,
        password=row.get("password") or None,
        protocol=protocol_str if protocol_str else "socks5",
        relay_ip=row.get("relay_ip") or None,
        relay_port=relay_port,
        relay_protocol=relay_protocol_str if relay_protocol_str else None,
        purchase_date=purchase_date,
        purchase_price=purchase_price,
        purchase_channel=row.get("purchase_channel") or None,
        expire_date=expire_date,
        sale_customer=row.get("sale_customer") or None,
        sale_price=sale_price,
        status=status_str if status_str else "active",
        usage=usage_str if usage_str else "idle",
        remark=row.get("remark") or None,
    )

    return create_data, None


def import_from_csv(db: Session, file_content: bytes) -> ProxyNodeImportResult:
    """
    解析 UTF-8 编码的 CSV（兼容 UTF-8 with BOM），逐行处理并导入节点。

    单行失败不中止整批处理。
    """
    # 兼容 UTF-8 with BOM
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    success_count = 0
    fail_count = 0
    errors = []

    # CSV 第一行为列名，数据从第二行开始（line_num 从 2 计）
    for line_num, row in enumerate(reader, start=2):
        node_data, error = _validate_row(dict(row), line_num)
        if error:
            fail_count += 1
            errors.append(error)
            logger.debug(f"import_from_csv: 跳过第 {line_num} 行，原因：{error}")
            continue

        try:
            create_node(db, node_data)
            success_count += 1
        except Exception as e:
            fail_count += 1
            err_msg = f"第 {line_num} 行: 数据库写入失败 - {str(e)}"
            errors.append(err_msg)
            logger.warning(f"import_from_csv: {err_msg}")

    logger.info(
        f"import_from_csv 完成：success={success_count}, fail={fail_count}"
    )
    return ProxyNodeImportResult(
        success_count=success_count,
        fail_count=fail_count,
        errors=errors,
    )


def import_from_excel(db: Session, file_content: bytes) -> ProxyNodeImportResult:
    """
    使用 openpyxl 解析 .xlsx 文件，第一行为列名，从第二行开始处理数据。

    单行失败不中止整批处理。
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        logger.info("import_from_excel: 文件为空")
        return ProxyNodeImportResult(success_count=0, fail_count=0, errors=[])

    # 第一行为列名
    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]

    success_count = 0
    fail_count = 0
    errors = []

    # 数据从第二行开始，line_num 从 2 计
    for line_num, row_values in enumerate(rows[1:], start=2):
        # 将行数据与列名对应，构建字典
        row_dict = {}
        for col_name, cell_value in zip(header, row_values):
            row_dict[col_name] = str(cell_value).strip() if cell_value is not None else ""

        node_data, error = _validate_row(row_dict, line_num)
        if error:
            fail_count += 1
            errors.append(error)
            logger.debug(f"import_from_excel: 跳过第 {line_num} 行，原因：{error}")
            continue

        try:
            create_node(db, node_data)
            success_count += 1
        except Exception as e:
            fail_count += 1
            err_msg = f"第 {line_num} 行: 数据库写入失败 - {str(e)}"
            errors.append(err_msg)
            logger.warning(f"import_from_excel: {err_msg}")

    wb.close()
    logger.info(
        f"import_from_excel 完成：success={success_count}, fail={fail_count}"
    )
    return ProxyNodeImportResult(
        success_count=success_count,
        fail_count=fail_count,
        errors=errors,
    )


def generate_template_csv() -> bytes:
    """
    生成包含所有列名和一行示例数据的模板 CSV。

    使用 UTF-8 with BOM 编码，兼容 Excel 直接打开。
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SUPPORTED_COLUMNS)
    writer.writeheader()
    writer.writerow(_TEMPLATE_EXAMPLE)

    # UTF-8 with BOM
    return output.getvalue().encode("utf-8-sig")
