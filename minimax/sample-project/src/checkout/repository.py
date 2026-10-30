"""订单仓储。内存实现,提供订单查询接口(订单查询/查询接口/customer_orders 的底层实现)。"""

from __future__ import annotations

from decimal import Decimal

from checkout.models import Order


class OrderRepository:
    """按客户查询订单、保存订单的内存仓储。"""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def add(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def for_customer(
        self,
        customer_id: str,
        min_total: Decimal | None = None,
    ) -> list[Order]:
        """按客户查询订单,结果按创建时间升序排列(同一时间按 order_id 升序)。

        SPEC-003 要求:提供 min_total 时,只返回订单总额 >= min_total 的订单
        (含边界,min_total 与某订单总额相等时该订单必须返回)。

        TODO(SPEC-003): min_total 过滤行为尚未实现,当前直接返回全部订单。
        """
        orders = [order for order in self._orders.values() if order.customer_id == customer_id]
        orders.sort(key=lambda order: (order.created_at, order.order_id))
        if min_total is not None:
            # SPEC-003 未实现:此处应过滤订单总额 >= min_total 的订单。
            pass
        return orders
