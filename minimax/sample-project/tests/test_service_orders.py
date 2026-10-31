"""订单服务 customer_orders 接口的既有行为回归测试(不带筛选参数)。"""

from decimal import Decimal

from checkout.service import OrderService


def test_customer_orders_returns_all_without_filter(service):
    orders = service.customer_orders("c-001")
    assert [o.order_id for o in orders] == ["A-1001", "A-1002", "A-1004"]


def test_customer_orders_accepts_min_total_keyword(service):
    # 参数已存在于接口签名(SPEC-003 的 API 形态),调用不应报错。
    orders = service.customer_orders("c-001", min_total=Decimal("0"))
    assert len(orders) == 3


def test_customer_orders_unknown_customer(service):
    assert service.customer_orders("nobody") == []
