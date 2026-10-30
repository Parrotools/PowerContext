"""共享测试夹具:构造一批可复用的订单数据。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from checkout.models import OrderItem
from checkout.service import OrderService


def item(sku: str, unit_price: str, quantity: int = 1) -> OrderItem:
    return OrderItem(sku=sku, name=f"商品-{sku}", unit_price=Decimal(unit_price), quantity=quantity)


@pytest.fixture()
def service() -> OrderService:
    svc = OrderService()
    svc.place_order(
        order_id="A-1001",
        customer_id="c-001",
        items=[item("SKU-1", "10.00", 2)],
        created_at=datetime(2026, 1, 1, 9, 0, 0),
    )  # total = 20.00
    svc.place_order(
        order_id="A-1002",
        customer_id="c-001",
        items=[item("SKU-2", "99.90", 1)],
        created_at=datetime(2026, 1, 2, 10, 0, 0),
    )  # total = 99.90
    svc.place_order(
        order_id="A-1003",
        customer_id="c-002",
        items=[item("SKU-3", "5.00", 3)],
        created_at=datetime(2026, 1, 3, 11, 0, 0),
    )  # total = 15.00
    svc.place_order(
        order_id="A-1004",
        customer_id="c-001",
        items=[item("SKU-4", "200.00", 1)],
        created_at=datetime(2026, 1, 2, 10, 0, 0),
    )  # total = 200.00,与 A-1002 同一时间
    return svc
