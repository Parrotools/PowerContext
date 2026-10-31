# 技术使用记录(records/)

本目录的全部记录由 `sddctx` 在执行命令时自动生成,是赛题要求的「技术使用记录」提交材料。
评审可先清空本目录再重跑 [docs/VALIDATION.md](../docs/VALIDATION.md) 的步骤,核对记录与操作一一对应。

| 文件/目录 | 内容 | 对应验收项 |
| --- | --- | --- |
| `doctor-report.txt` | `sddctx doctor` 体检输出(各组件就绪情况) | 能够运行 |
| `context-task-001.md` / `.json` | 任务 task-001 的开发上下文(规格条目/代码/测试/任务状态,含来源与检索审计) | 上下文正确 |
| `context-task-001.check.md` | `--check` 对照 task.json 的 13 项必要来源核对报告 | 上下文正确 |
| `db-query-log.md` | 每次对 seekdb 的写入与检索:时间、用途、SQL(MATCH…AGAINST)、参数、命中 ID、耗时 | 数据库实际参与 |
| `powercontext-log.md` | 每次对 PowerContext 的写入与读取:scope 创建/复用、看板保存、验证结果保存、resume 读取 | 状态能够复用 |
| `minimax/<task>-<时间戳>/` | MiniMax 开发记录:`devlog.md`(时间线)、`context.md`/`context.json`(提供的上下文)、`minimax-request.json`(密钥脱敏)、`minimax-response.md`/`.json`(原文)、`before/`(修改前快照)、`applied-files.json`、`code.diff.md` | MiniMax 实际参与、代码修改有效 |
| `verify/` | 目标/回归测试运行:`target-<phase>-*.log`、`regression-<phase>-*.log`(命令、退出码、git 版本)、`summary-<phase>-*.json` | 代码修改有效 |
| `spec-update-demo/` | 规格更新演示:追加条目 → 重导入 → 上下文立即包含新条目 → 恢复原状 | 上下文正确 |
| `resume-context.md` | `sddctx resume` 基于恢复状态重建的开发上下文 | 状态能够复用 |

## 当前状态说明

- 全部记录已生成:MiniMax 开发记录见 `minimax/task-001-20261031-034850/`
  (模型 MiniMax-M3.1-Flash;修改 `sample-project/src/checkout/repository.py`,
  与 `verify/` 中 before 失败→after 全绿对应)。
- 记录中的密钥一律脱敏(`sddctx.config.redact`)。
