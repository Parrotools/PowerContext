"""SPEC-003 目标功能测试:订单查询的最小金额筛选(min_total)。

这一组测试在目标行为实现前必须失败(过滤未实现),实现后必须全部通过;
同时是修改后回归测试的一部分。
"""

from decimal import Decimal

from checkout.service import OrderService


def test_min_total_returns_only_matching_orders(service):
    orders = service.customer_orders("c-001", min_total=Decimal("50.00"))
    assert [o.order_id for o in orders] == ["A-1002", "A-1004"]


def test_min_total_includes_boundary(service):
    # A-1001 总额恰好 20.00:含边界时必须返回,且总额 99.90/200.00 的订单必须被过滤掉。
    orders = service.customer_orders("c-001", min_total=Decimal("20.00"))
    assert [o.order_id for o in orders] == ["A-1001"]


def test_min_total_none_returns_all(service):
    orders = service.customer_orders("c-001", min_total=None)
    assert [o.order_id for o in orders] == ["A-1001", "A-1002", "A-1004"]


def test_filter_preserves_creation_order(service):
    orders = service.customer_orders("c-001", min_total=Decimal("10.00"))
    created = [o.created_at for o in orders]
    assert created == sorted(created)


def test_min_total_above_everything_returns_empty(service):
    assert service.customer_orders("c-001", min_total=Decimal("999.00")) == []


def test_unknown_customer_with_min_total_returns_empty(service):
    assert service.customer_orders("nobody", min_total=Decimal("1.00")) == []


def test_min_total_must_not_mutate_results_for_other_calls(service):
    service.customer_orders("c-001", min_total=Decimal("100.00"))
    # 过滤不得影响后续不带筛选的查询。
    assert [o.order_id for o in service.customer_orders("c-001")] == ["A-1001", "A-1002", "A-1004"]
