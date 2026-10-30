# 验证样例(VALIDATION)

本样例完成赛题 2.1 的完整流程:在业务工程 `sample-project`(checkout 订单结算服务)上,
定义并完成一项局部修改——**为订单查询接口增加最小金额筛选条件**。
按步骤执行,每步都给出预期结果;评审可在干净环境逐步复现。

## 0. 任务定义

| 项目 | 内容 |
| --- | --- |
| 任务描述 | 为订单查询增加最小金额筛选条件:`OrderService.customer_orders(customer_id, min_total=None)`,提供 `min_total`(Decimal)时只返回订单总额 ≥ min_total 的订单(含边界),未提供时行为与既有版本一致;排序与既有调用兼容性不受影响 |
| 要改什么 | `sample-project/src/checkout/repository.py` 中 `OrderRepository.for_customer` 的过滤行为(当前 `TODO(SPEC-003)` 未实现) |
| 哪些原有行为必须保持 | 不带筛选的查询结果与排序完全不变(`tests/test_service_orders.py`、`tests/test_repository.py` 回归);折扣规则、金额精度不受影响 |
| 上下文必须包含的规格来源 | `specs/SPEC-003-订单查询规格.md` 条目 SPEC-003-1/2/3/4/5/6;`specs/SPEC-001-工程约束.md` 条目 SPEC-001-3/4 |
| 上下文必须包含的代码来源 | `sample-project/src/checkout/repository.py`(`OrderRepository.for_customer`)、`sample-project/src/checkout/service.py`(`OrderService.customer_orders`) |
| 上下文必须包含的测试来源 | `sample-project/tests/test_order_query_filter.py`(目标)、`sample-project/tests/test_service_orders.py` 与 `tests/test_repository.py`(回归) |
| 初始数据 | `tests/conftest.py` 夹具:客户 c-001 三笔订单(A-1001 总额 20.00、A-1002 99.90、A-1004 200.00),c-002 一笔(15.00) |
| 无效干扰项(不应进入规格条目) | `specs/SPEC-002-折扣规则.md`(与查询任务无关) |

## 0. 体检(可选但推荐)

```bash
.venv/bin/sddctx doctor
```

**预期**:seekdb、PowerContext Server、PowerContext scope、MiniMax 接入点/模型、业务工程测试五项为 ✔;
MiniMax API Key 未配置时为 ▲(仅影响第 4 步);结论为"可以运行验证样例"。

## 前置条件

按 [RUNBOOK.md](RUNBOOK.md) 完成:依赖安装、`sddctx import`、PowerContext Server 已启动。
MiniMax 相关步骤(第 5 步)需要 `SDDCTX_MINIMAX_API_KEY`;其余步骤无需 Key。

## 1. 导入资料(流程第 1 步)

```bash
.venv/bin/sddctx import
```

**预期**:输出 `导入完成:扫描 13 个文件,写入 27 条资产。分类: code×5, spec_entry×14, spec_file×3, test×5`;
`records/db-query-log.md` 追加了逐条写入审计(表 `sdd_assets`,seekdb 原生 FULLTEXT 索引)。

## 2. 构建上下文(流程第 2 步:选择相关资料)

```bash
.venv/bin/sddctx context --task "为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用"
```

随后用清单核对必要来源(便于评审核对):

```bash
.venv/bin/sddctx context --task "为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用" --check examples/run-task-filter/task.json
```

**预期**:13 项必要来源(8 规格 + 2 代码 + 3 测试)逐项 ✔,结论"必要来源全部包含",退出码 0。

**预期**(可逐项核对):
- 第一节列出 SPEC-003 条目与 SPEC-001 条目,每条注明来源路径与版本,相关规格文档附全文;SPEC-002 折扣条目不出现在条目中;
- 第二节代码以 `sample-project/src/checkout/repository.py`、`service.py` 靠前,内容即当前带 `TODO(SPEC-003)` 的源码;
- 第三节测试以 `test_order_query_filter.py` 靠前;
- 第四节「任务状态(PowerContext)」显示已保存的看板(首次运行为“暂无”)。

## 3. 修改前验证(流程第 4 步的前半:目标行为未实现)

```bash
.venv/bin/sddctx verify --task-id task-001 --phase before
.venv/bin/sddctx status --task-id task-001 \
  --complete "导入规格/代码/测试资料到 seekdb" "构建开发上下文并确认规格条目" "修改前运行目标测试并记录失败" \
  --pending "MiniMax 完成代码修改" "修改后运行目标测试与回归测试"
```

**预期**:
- before 判定为 `✔ 通过`(目标测试按预期失败),失败节点至少包含
  `test_min_total_returns_only_matching_orders`、`test_min_total_above_everything_returns_empty`;
  日志在 `records/verify/target-before-*.log`(记录命令、退出码 1、git 版本);
- `status` 输出已写入 PowerContext 的看板 JSON(citation 含 entry_id/entry_version_id)。

## 4. MiniMax 完成代码修改(流程第 3 步)

```bash
export SDDCTX_MINIMAX_API_KEY="你的MiniMax API Key"
.venv/bin/sddctx dev --task "为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用" --task-id task-001
```

**预期**:
- 输出 `模型 MiniMax-M2.1;修改文件: sample-project/src/checkout/repository.py;…`;
- `records/minimax/task-001-*/` 生成:`context.md`(即第 2 步上下文)、`minimax-request.json`(Key 已脱敏)、
  `minimax-response.md`(原文)、`before/`(修改前快照)、`applied-files.json`、`devlog.md`(开发记录)、`code.diff.md`;
- 业务工程 `repository.py` 的 `min_total` 过滤被实现。

## 5. 修改后验证(流程第 4 步后半)

```bash
.venv/bin/sddctx verify --task-id task-001 --phase after
.venv/bin/sddctx status --task-id task-001 --complete "MiniMax 完成代码修改" "修改后运行目标测试与回归测试"
```

**预期**:
- 目标测试:`7 passed`(命令、退出码 0、git 版本记入 `records/verify/target-after-*.log`);
- 回归测试:全量 `tests/` 20 个用例全部通过;
- after 判定 `✔ 通过 — 目标测试与回归测试全部通过`;验证结果写入 PowerContext。

## 6. 规格更新后上下文使用新内容(上下文正确验收)

```bash
# 6a. 给 SPEC-003 追加新条目(任意编辑均可,这里以演示条目为例)
cat >> specs/SPEC-003-订单查询规格.md <<'EOF'
- SPEC-003-8: (演示修订)min_total 传入负数时按 0 处理,不得抛出异常。
EOF

# 6b. 重新导入并重建上下文
.venv/bin/sddctx import
.venv/bin/sddctx context --task "为订单查询增加最小金额筛选条件 min_total" --json | \
  .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print([i['source']+f\"@v{i['version']}\" for i in d['sections']['spec_entries']])"

# 6c. 恢复规格原状并重新导入(保持样例初始状态)
git checkout -- specs/SPEC-003-订单查询规格.md
.venv/bin/sddctx import
```

**预期**:6b 输出中包含 `specs/SPEC-003-订单查询规格.md#SPEC-003-8`,且若修改已有条目文字,
其版本号自增——模块每次实时查库,规格更新重新导入后立即生效,不返回固定答案。

## 7. 状态复用:重启后读取并使用(状态能够复用验收)

```bash
# 7a. 从空状态开始(可选,演示“从空状态开始保存”):.venv/bin/sddctx reset --force 后重走第 1–3 步
# 7b. 每次调用 sddctx 都是全新进程;以下命令在“重启后”读取状态并使用:
.venv/bin/sddctx resume --task-id task-001
```

**预期**:
- 输出任务编号、目标、已完成(✔)、待办(▶)、已有验证结果(before 未通过/after 通过等,含日志路径),
  全部来自 PowerContext Memory,而非本地文件;
- 末行 `已基于恢复的状态重建开发上下文: records/resume-context.md` ——恢复的状态被用于
  后续上下文构建,`records/powercontext-log.md` 可核对每次读写。

## 8. 预期结果汇总

| 检查点 | 预期 |
| --- | --- |
| `sddctx verify --phase before` | 目标测试失败(行为未实现),记录退出码 1 与失败节点 |
| `sddctx verify --phase after` | 目标 7 passed;回归全部 passed;判定通过 |
| `records/minimax/<run>/devlog.md` | 任务、上下文指针、请求/响应留档、逐文件修改,与 `code.diff.md` 一致 |
| `records/db-query-log.md` | 每次上下文构建的检索 SQL(含 `MATCH … AGAINST`)、参数、命中 ID |
| `records/powercontext-log.md` | 每次 scope/memory 读写(看板保存、验证结果、resume 读取) |
| 规格更新重导入 | 上下文立即包含新条目/新版本 |
| `sddctx resume`(新进程) | 完整恢复看板与验证结果并重建上下文 |

## 9. 重置方法

```bash
.venv/bin/sddctx reset --force          # 清空 seekdb 数据目录与生成记录
git checkout -- sample-project specs    # 业务工程与规格恢复初始状态
# 另需重启 PowerContext Server 前: rm -rf .sddctx-data/powercontext(清空其状态)
```
