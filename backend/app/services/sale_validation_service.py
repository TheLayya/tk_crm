import json
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException


def validate_sale_information(values: dict[str, Any], sold_status: str, require_date: bool = False) -> None:
    if values.get("status") != sold_status:
        return
    customer = values.get("sale_customer")
    if not customer or not customer.strip():
        raise HTTPException(status_code=422, detail="已出售必须填写出售客户")
    price = values.get("sale_price")
    try:
        price = Decimal(str(price))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="请填写有效的出售金额") from None
    if not price.is_finite() or price < 0:
        raise HTTPException(status_code=422, detail="出售金额必须是非负数字")
    sellers = values.get("sellers")
    if isinstance(sellers, str):
        try:
            sellers = json.loads(sellers)
        except ValueError:
            sellers = None
    if not isinstance(sellers, list) or not sellers or any(not isinstance(seller, str) or not seller.strip() for seller in sellers):
        raise HTTPException(status_code=422, detail="已出售必须选择出售人")
    if require_date and not values.get("sale_date"):
        raise HTTPException(status_code=422, detail="已出售必须填写出售日期")
