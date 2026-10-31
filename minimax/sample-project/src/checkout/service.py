"""订单服务:下单与订单查询的业务入口。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from checkout.models import Order, OrderItem
from checkout.repository import OrderRepository


class OrderService:
    """订单服务入口,供调用方使用。"""

    def __init__(self, repository: OrderRepository | None = None) -> None:
        self._repository = repository if repository is not None else OrderRepository()

    def place_order(
        self,
        order_id: str,
        customer_id: str,
        items: list[OrderItem],
        created_at: datetime | None = None,
    ) -> Order:
        """创建并保存一张订单。"""
        if created_at is None:
            created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        order = Order(
            order_id=order_id,
            customer_id=customer_id,
            items=list(items),
            created_at=created_at,
        )
        self._repository.add(order)
        return order

    def customer_orders(
        self,
        customer_id: str,
        min_total: Decimal | None = None,
    ) -> list[Order]:
        """订单查询接口:返回该客户的订单,按创建时间升序。

        SPEC-003:提供 min_total(Decimal)时,只返回订单总额 >= min_total
        的订单(含边界);未提供时返回全部订单。
        """
        return self._repository.for_customer(customer_id, min_total=min_total)
