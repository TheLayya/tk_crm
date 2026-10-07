"""Validated table queries shared by paginated lists and complete row collections."""
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, NoReturn

from fastapi import HTTPException
from sqlalchemy import Boolean, Date, DateTime, Numeric, Integer, Float, inspect, or_


def _invalid(detail: str) -> NoReturn:
    raise HTTPException(422, detail=f"表格查询参数无效：{detail}")


def model_table_fields(model: Any, names: Any = None, exclude: Any = ()) -> dict[str, Any]:
    """Build a whitelist from mapped columns; callers exclude credentials/internal fields."""
    columns = inspect(model).columns
    selected = names if names is not None else columns.keys()
    return {name: getattr(model, name) for name in selected if name not in exclude}


def field_kind(column: Any) -> str:
    kind = column.type
    if isinstance(kind, (Date, DateTime)):
        return "date"
    if isinstance(kind, Boolean):
        return "enum"
    if isinstance(kind, (Numeric, Integer, Float)):
        return "number"
    return "text"


def parse_table_filters(raw: Any, fields: Any = None) -> dict[str, dict[str, Any]]:
    if raw is None or raw == "":
        return {}
    try:
        filters = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        _invalid("筛选条件必须是 JSON 对象")
    if not isinstance(filters, dict):
        _invalid("筛选条件必须是 JSON 对象")
    for name, condition in filters.items():
        if fields is not None and name not in fields:
            _invalid(f"不支持字段 {name}")
        if not isinstance(condition, dict) or set(condition) - {"type", "value", "min", "max"}:
            _invalid(f"字段 {name} 的条件格式错误")
        kind = condition.get("type")
        if not isinstance(kind, str) or kind not in {"text", "number", "date", "enum"}:
            _invalid(f"字段 {name} 的筛选类型错误")
        column = fields[name] if fields is not None else None
        boolean = column is not None and not isinstance(column, str) and isinstance(column.type, Boolean)
        expected = column if isinstance(column, str) else field_kind(column) if column is not None else None
        if expected is not None and kind != expected and kind != "enum":
            _invalid(f"字段 {name} 不支持 {kind} 筛选")
        if kind in {"text", "enum"}:
            if "min" in condition or "max" in condition or "value" not in condition:
                _invalid(f"字段 {name} 必须提供 value")
            value = condition["value"]
            if kind == "text" and not isinstance(value, str):
                _invalid(f"字段 {name} 必须是文本")
            values = value if isinstance(value, list) else [value]
            if kind == "enum" and (not values or any(isinstance(item, (dict, list)) for item in values)):
                _invalid(f"字段 {name} 必须是枚举值或非空数组")
            if kind == "enum" and boolean and any(item is not None and not isinstance(item, bool) for item in values):
                _invalid(f"字段 {name} 必须是 true、false 或 null")
            if kind == "enum" and expected in {"number", "date"}:
                for item in values:
                    if item is not None:
                        _number(item) if expected == "number" else _date_value(item)
        else:
            if "value" in condition and ("min" in condition or "max" in condition):
                _invalid(f"字段 {name} 不能同时使用 value 和范围")
            if not any(key in condition for key in ("value", "min", "max")):
                _invalid(f"字段 {name} 缺少范围")
            convert: Callable[[Any], Any] = _number if kind == "number" else _date_value
            for key in ("value", "min", "max"):
                if key in condition:
                    convert(condition[key])
                    if kind == "date" and key in {"value", "max"} and _date_only(condition[key]):
                        _next_day(_date_value(condition[key]))
            if "min" in condition and "max" in condition and convert(condition["min"]) > convert(condition["max"]):
                _invalid(f"字段 {name} 最小值不能大于最大值")
    return filters


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _invalid("数值格式错误")
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            _invalid("数值必须有限")
        return result
    except InvalidOperation:
        _invalid("数值格式错误")


def _date_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            _invalid("日期格式错误")
    else:
        _invalid("日期格式错误")
    if result.tzinfo is not None:
        try:
            result = result.astimezone(timezone.utc).replace(tzinfo=None)
        except (OverflowError, ValueError):
            _invalid("日期超出支持范围")
    return result


def _next_day(value: datetime) -> datetime:
    try:
        return value + timedelta(days=1)
    except OverflowError:
        _invalid("日期超出支持范围")


def _date_only(value: Any) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime) or isinstance(value, str) and len(value) == 10


def _validate_sort(fields: Any, sort_by: Any, sort_order: str) -> None:
    if sort_order not in {"asc", "desc"}:
        _invalid("排序方向必须是 asc 或 desc")
    if sort_by and sort_by not in fields:
        _invalid(f"不支持排序字段 {sort_by}")


def apply_table_query(query: Any, fields: dict[str, Any], sort_by: str | None = None,
                      sort_order: str = "asc", table_filters: Any = None,
                      stable_column: Any = None, default_sort: Any = None) -> Any:
    """Filter/order SQL before count and pagination; every expression is whitelisted."""
    _validate_sort(fields, sort_by, sort_order)
    filters = parse_table_filters(table_filters, fields)
    for name, condition in filters.items():
        column, kind = fields[name], condition["type"]
        if kind == "text":
            query = query.filter(column.icontains(condition["value"], autoescape=True))
        elif kind == "enum":
            value = condition["value"]
            values = value if isinstance(value, list) else [value]
            enum_convert: Callable[[Any], Any] = _number if field_kind(column) == "number" else _date_value if field_kind(column) == "date" else lambda item: item
            values = [enum_convert(item) for item in values if item is not None]
            if isinstance(column.type, Date) and not isinstance(column.type, DateTime):
                values = [item.date() for item in values]
            expressions = [column.in_(values)] if values else []
            if None in (value if isinstance(value, list) else [value]):
                expressions.append(column.is_(None))
            query = query.filter(or_(*expressions))
        else:
            convert: Callable[[Any], Any] = _number if kind == "number" else _date_value
            for key in ("value", "min", "max"):
                if key not in condition:
                    continue
                raw, value = condition[key], convert(condition[key])
                if kind == "date" and isinstance(column.type, Date) and not isinstance(column.type, DateTime):
                    value = value.date()
                if kind == "date" and _date_only(raw) and isinstance(column.type, DateTime) and key in {"value", "max"}:
                    query = query.filter(column < _next_day(value))
                    if key == "value":
                        query = query.filter(column >= value)
                else:
                    query = query.filter(column == value if key == "value" else column >= value if key == "min" else column <= value)
    if sort_by:
        column, direction = fields[sort_by], sort_order
    elif default_sort:
        column, direction = default_sort
    else:
        column, direction = stable_column, "asc"
    if column is not None:
        # CASE/IS NULL works on SQLite and MySQL, unlike dialect-specific NULLS LAST.
        query = query.order_by(None).order_by(column.is_(None).asc(), column.desc() if direction == "desc" else column.asc())
        if stable_column is not None:
            query = query.order_by(stable_column.asc())
    return query


def _row_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind == "number":
        if isinstance(value, (list, tuple)):
            numbers = [_number(item) for item in value]
            return sum(numbers, Decimal(0)) if all(item is not None for item in numbers) else None
        return _number(value)
    if kind == "date":
        return _date_value(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    return str(value).casefold()


def apply_table_rows(rows: list[dict[str, Any]], fields: dict[str, str], sort_by: str | None = None,
                     sort_order: str = "asc", table_filters: Any = None,
                     stable_key: str = "id") -> list[dict[str, Any]]:
    """Use only on complete, already-scoped collections, then count/slice the result."""
    _validate_sort(fields, sort_by, sort_order)
    filters = parse_table_filters(table_filters, fields)
    result = []
    for row in rows:
        matches = True
        for name, condition in filters.items():
            raw, kind = row.get(name), condition["type"]
            value = _row_value(raw, fields[name])
            if kind == "text":
                matches = value is not None and condition["value"].casefold() in str(value)
            elif kind == "enum":
                selected = condition["value"] if isinstance(condition["value"], list) else [condition["value"]]
                values = raw if isinstance(raw, list) else [raw]
                matches = any(_row_value(item, fields[name]) in [_row_value(choice, fields[name]) for choice in selected] for item in values)
            elif value is None:
                matches = False
            else:
                for key in ("value", "min", "max"):
                    if key not in condition:
                        continue
                    bound = _row_value(condition[key], fields[name])
                    if kind == "date" and _date_only(condition[key]) and key in {"value", "max"}:
                        matches = value < _next_day(bound) and (key != "value" or value >= bound)
                    else:
                        matches = value == bound if key == "value" else value >= bound if key == "min" else value <= bound
                    if not matches:
                        break
            if not matches:
                break
        if matches:
            result.append(row)
    if sort_by:
        result.sort(key=lambda row: row.get(stable_key) or 0)
        present = [row for row in result if row.get(sort_by) is not None]
        absent = [row for row in result if row.get(sort_by) is None]
        present.sort(key=lambda row: _row_value(row[sort_by], fields[sort_by]), reverse=sort_order == "desc")
        result = present + absent
    return result
