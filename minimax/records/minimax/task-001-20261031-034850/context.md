# 开发上下文 — 为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用

- 生成时间: 2026-10-31T03:48:53+00:00

## 一、适用的规格条目
- [SPEC-003-1] 订单查询接口 OrderService.customer_orders(customer_id, min_total=None) 支持可选的最小金额筛选参数 min_total(Decimal 类型)。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-1`(版本 1,score 12.305)
- [SPEC-003-6] min_total 参数必须带默认值 None,保证既有调用 customer_orders(customer_id) 的兼容性。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-6`(版本 1,score 6.655)
- [SPEC-001-4] 为既有接口增加参数时必须提供默认值,不能破坏既有调用的兼容性。
  来源: `specs/SPEC-001-工程约束.md#SPEC-001-4`(版本 1,score 5.192)
- [SPEC-003-5] 过滤只作用于当次调用,不得影响同一仓储实例上后续不带筛选的查询结果。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-5`(版本 1,score 3.669)
- [SPEC-003-2] 提供 min_total 时,只返回订单总额 >= min_total 的订单;过滤语义为大于等于(含边界),min_total 与某订单总额相等时该订单必须返回。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-2`(版本 1,score 3.113)
- [SPEC-003-3] 未提供 min_total 时,返回该客户全部订单,行为与既有版本完全一致。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-3`(版本 1,score 2.959)
- [SPEC-002-3] 折扣不改变订单原始总额,只影响应付金额的计算结果。
  来源: `specs/SPEC-002-折扣规则.md#SPEC-002-3`(版本 1,score 2.707)
- [SPEC-003-8] (演示修订)min_total 传入负数时按 0 处理,不得抛出异常。
  来源: `specs/SPEC-003-订单查询规格.md#SPEC-003-8`(版本 1,score 2.101)

### 相关规格文档(全文)
#### `specs/SPEC-003-订单查询规格.md` — SPEC-003 订单查询规格(版本 3)

```markdown
# SPEC-003 订单查询规格

- 编号: SPEC-003
- 状态: 有效
- 适用模块: checkout.service.OrderService / checkout.repository.OrderRepository

## 条目

- SPEC-003-1: 订单查询接口 OrderService.customer_orders(customer_id, min_total=None) 支持可选的最小金额筛选参数 min_total(Decimal 类型)。
- SPEC-003-2: 提供 min_total 时,只返回订单总额 >= min_total 的订单;过滤语义为大于等于(含边界),min_total 与某订单总额相等时该订单必须返回。
- SPEC-003-3: 未提供 min_total 时,返回该客户全部订单,行为与既有版本完全一致。
- SPEC-003-4: 过滤不得改变结果排序:结果仍按创建时间升序排列,同一创建时间按 order_id 升序。
- SPEC-003-5: 过滤只作用于当次调用,不得影响同一仓储实例上后续不带筛选的查询结果。
- SPEC-003-6: min_total 参数必须带默认值 None,保证既有调用 customer_orders(customer_id) 的兼容性。

```

#### `specs/SPEC-002-折扣规则.md` — SPEC-002 折扣规则规格(版本 1)

```markdown
# SPEC-002 折扣规则规格

- 编号: SPEC-002
- 状态: 有效
- 适用模块: checkout.pricing

## 条目

- SPEC-002-1: 折扣百分比必须在 [0, 50] 区间内(含边界),超出范围抛出 ValueError。
- SPEC-002-2: 折扣在订单总额(未加税)的基础上计算,结果保留两位小数。
- SPEC-002-3: 折扣不改变订单原始总额,只影响应付金额的计算结果。

```

#### `specs/SPEC-001-工程约束.md` — SPEC-001 工程约束规格(版本 1)

```markdown
# SPEC-001 工程约束规格

- 编号: SPEC-001
- 状态: 有效
- 适用模块: checkout 全部模块

## 条目

- SPEC-001-1: 所有金额字段与计算结果一律使用 Decimal,并且必须保留两位小数;禁止使用 float 表示金额。
- SPEC-001-2: 订单时间字段 created_at 使用 UTC 时间;存储与比较时不携带时区信息。
- SPEC-001-3: 查询类接口的结果默认按创建时间升序排列;同一创建时间按 order_id 升序。
- SPEC-001-4: 为既有接口增加参数时必须提供默认值,不能破坏既有调用的兼容性。

```

## 二、需要关注的代码
### `sample-project/src/checkout/service.py` — 符号: OrderService
来源: `sample-project/src/checkout/service.py`(版本 1,score 3.549)

```python
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

```

### `sample-project/src/checkout/repository.py` — 符号: OrderRepository
来源: `sample-project/src/checkout/repository.py`(版本 1,score 3.038)

```python
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

```

### `sample-project/src/checkout/pricing.py` — 符号: apply_discount
来源: `sample-project/src/checkout/pricing.py`(版本 1,score 1.232)

```python
"""折扣计算(SPEC-002 折扣规则)。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
MIN_DISCOUNT_PERCENT = Decimal("0")
MAX_DISCOUNT_PERCENT = Decimal("50")
HUNDRED = Decimal("100")


def apply_discount(total: Decimal, percent: Decimal) -> Decimal:
    """对订单总额按百分比打折,结果保留两位小数。

    SPEC-002 约束:折扣百分比必须在 [0, 50] 区间内(含边界),
    超出范围抛出 ValueError。
    """
    if percent < MIN_DISCOUNT_PERCENT or percent > MAX_DISCOUNT_PERCENT:
        raise ValueError(f"折扣百分比必须在 [{MIN_DISCOUNT_PERCENT}, {MAX_DISCOUNT_PERCENT}] 内,收到 {percent}")
    discounted = total * (HUNDRED - percent) / HUNDRED
    return discounted.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

```

### `sample-project/src/checkout/models.py` — 符号: OrderItem, Order
来源: `sample-project/src/checkout/models.py`(版本 1,score 0.762)

```python
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

```

### `sample-project/src/checkout/__init__.py`
来源: `sample-project/src/checkout/__init__.py`(版本 1,score 0.503)

```python
"""checkout 订单结算服务。"""

__all__ = ["Order", "OrderItem", "OrderRepository", "OrderService", "apply_discount"]

```

## 三、验证测试
### `sample-project/tests/test_service_orders.py` — 符号: test_customer_orders_returns_all_without_filter, test_customer_orders_accepts_min_total_keyword, test_customer_orders_unknown_customer
来源: `sample-project/tests/test_service_orders.py`(版本 1,score 5.408)

```python
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

```

### `sample-project/tests/test_order_query_filter.py` — 符号: test_min_total_returns_only_matching_orders, test_min_total_includes_boundary, test_min_total_none_returns_all, test_filter_preserves_creation_order, test_min_total_above_everything_returns_empty, test_unknown_customer_with_min_total_returns_empty, test_min_total_must_not_mutate_results_for_other_calls
来源: `sample-project/tests/test_order_query_filter.py`(版本 1,score 4.890)

```python
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
    # A-1001 总额恰好 20.00:含边界(>=)语义下必须返回;高于阈值的订单保留;
    # 其他客户的订单不得混入。该用例同时守护“不得误用严格大于”。
    orders = service.customer_orders("c-001", min_total=Decimal("20.00"))
    ids = [o.order_id for o in orders]
    assert "A-1001" in ids
    assert "A-1002" in ids and "A-1004" in ids
    assert "A-1003" not in ids


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

```

### `sample-project/tests/test_repository.py` — 符号: test_add_and_get_roundtrip, test_for_customer_only_returns_that_customer, test_for_customer_sorted_by_created_at_then_id, test_unknown_customer_returns_empty, test_totals_are_two_decimal
来源: `sample-project/tests/test_repository.py`(版本 1,score 2.341)

```python
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

```

### `sample-project/tests/conftest.py` — 符号: item, service
来源: `sample-project/tests/conftest.py`(版本 1,score 0.310)

```python
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

```

## 四、任务状态(PowerContext)
- 任务编号: pytest-task
- 目标: 测试看板写入与读取
- 已完成: ["写入看板"]
- 待办: ["读取看板"]
- 已有验证结果: []
- 最近更新: 2026-10-31T01:36:40+00:00
