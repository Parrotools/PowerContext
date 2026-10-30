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
