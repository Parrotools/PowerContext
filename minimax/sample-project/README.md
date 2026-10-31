# checkout — 订单结算服务

小型订单结算业务工程,作为 SDD 上下文管理系统的验证载体。

- 金额一律使用 `Decimal`,保留两位小数(见 `specs/SPEC-001-工程约束.md`)
- 折扣规则见 `specs/SPEC-002-折扣规则.md`
- 订单查询规格见 `specs/SPEC-003-订单查询规格.md`

## 运行测试

```bash
python -m pytest
```

## 模块结构

- `src/checkout/models.py` — 订单与订单项模型
- `src/checkout/repository.py` — 订单仓储(内存实现)
- `src/checkout/pricing.py` — 折扣计算
- `src/checkout/service.py` — 订单服务入口
