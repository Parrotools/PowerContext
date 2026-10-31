# 代码差异 — task-001-20261031-034850

## src/checkout/repository.py

```diff
--- a/sample-project/src/checkout/repository.py
+++ b/sample-project/src/checkout/repository.py
@@ -27,13 +27,11 @@
         """按客户查询订单,结果按创建时间升序排列(同一时间按 order_id 升序)。
 
         SPEC-003 要求:提供 min_total 时,只返回订单总额 >= min_total 的订单
-        (含边界,min_total 与某订单总额相等时该订单必须返回)。
-
-        TODO(SPEC-003): min_total 过滤行为尚未实现,当前直接返回全部订单。
+        (含边界,min_total 与某订单总额相等时该订单必须返回)。负数阈值按 0 处理。
         """
         orders = [order for order in self._orders.values() if order.customer_id == customer_id]
         orders.sort(key=lambda order: (order.created_at, order.order_id))
         if min_total is not None:
-            # SPEC-003 未实现:此处应过滤订单总额 >= min_total 的订单。
-            pass
+            threshold = max(Decimal("0.00"), min_total)
+            orders = [order for order in orders if order.total() >= threshold]
         return orders
```
