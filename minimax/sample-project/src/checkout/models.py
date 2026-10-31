"""订单与订单项的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class OrderItem:
    """单个商品行。金额字段必须是 Decimal,由 SPEC-001 约束。"""

    sku: str
    name: str
    unit_price: Decimal
    quantity: int

    def subtotal(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(TWO_PLACES)


@dataclass
class Order:
    """一张订单。created_at 使用 UTC 时间,用于查询排序。"""

    order_id: str
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=None))
    status: str = "created"

    def total(self) -> Decimal:
        result = Decimal("0.00")
        for item in self.items:
            result += item.subtotal()
        return result.quantize(TWO_PLACES)
