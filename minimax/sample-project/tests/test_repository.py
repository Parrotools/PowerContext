"""订单仓储的既有行为回归测试(不含 SPEC-003 的 min_total 过滤)。"""

from decimal import Decimal

from checkout.repository import OrderRepository


def test_add_and_get_roundtrip(service):
    repo = OrderRepository()
    order = service.place_order(order_id="R-1", customer_id="c-100", items=[])
    assert repo.get("R-1") is None  # service 用的是自己的仓储实例
    repo.add(order)
    assert repo.get("R-1") is order


def test_for_customer_only_returns_that_customer(service):
    orders = service._repository.for_customer("c-001")
    assert [o.order_id for o in orders] == ["A-1001", "A-1002", "A-1004"]


def test_for_customer_sorted_by_created_at_then_id(service):
    orders = service._repository.for_customer("c-001")
    assert [(o.order_id, o.created_at) for o in orders] == sorted(
        [(o.order_id, o.created_at) for o in orders], key=lambda t: (t[1], t[0])
    )


def test_unknown_customer_returns_empty(service):
    assert service._repository.for_customer("nobody") == []


def test_totals_are_two_decimal(service):
    orders = {o.order_id: o for o in service._repository.for_customer("c-001")}
    assert orders["A-1001"].total() == Decimal("20.00")
    assert orders["A-1002"].total() == Decimal("99.90")
