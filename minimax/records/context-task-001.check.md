# 上下文必要来源核对
- 任务: 为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用
- 清单: examples/run-task-filter/task.json

  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-1(条目命中)
  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-2(条目命中)
  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-3(条目命中)
  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-4(所在规格文档已纳入上下文)
  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-5(条目命中)
  ✔ 规格 specs/SPEC-003-订单查询规格.md#SPEC-003-6(条目命中)
  ✔ 规格 specs/SPEC-001-工程约束.md#SPEC-001-3(所在规格文档已纳入上下文)
  ✔ 规格 specs/SPEC-001-工程约束.md#SPEC-001-4(条目命中)
  ✔ 代码 sample-project/src/checkout/repository.py
  ✔ 代码 sample-project/src/checkout/service.py
  ✔ 测试 sample-project/tests/test_order_query_filter.py
  ✔ 测试 sample-project/tests/test_service_orders.py
  ✔ 测试 sample-project/tests/test_repository.py

结论:必要来源全部包含 ✔
