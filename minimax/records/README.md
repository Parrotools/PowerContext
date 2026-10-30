# 技术使用记录(records/)

本目录的全部记录由 `sddctx` 在执行命令时自动生成,是赛题要求的「技术使用记录」提交材料。
评审可先清空本目录再重跑 [docs/VALIDATION.md](../docs/VALIDATION.md) 的步骤,核对记录与操作一一对应。

| 文件/目录 | 内容 | 对应验收项 |
| --- | --- | --- |
| `db-query-log.md` | 每次对 seekdb 的写入与检索:时间、用途、SQL(MATCH…AGAINST)、参数、命中 ID | 数据库实际参与 |
| `powercontext-log.md` | 每次对 PowerContext 的写入与读取:scope 创建/复用、看板保存、验证结果保存、resume 读取 | 状态能够复用 |
| `minimax/<task>-<时间戳>/` | MiniMax 开发记录:`devlog.md`(时间线)、`context.md`/`context.json`(提供的上下文)、`minimax-request.json`(密钥脱敏)、`minimax-response.md`/`.json`(原文)、`before/`(修改前快照)、`applied-files.json`、`code.diff.md` | MiniMax 实际参与、代码修改有效 |
| `verify/` | 目标/回归测试运行:`target-<phase>-*.log`、`regression-<phase>-*.log`(命令、退出码、git 版本)、`summary-<phase>-*.json` | 代码修改有效 |
| `resume-context.md` | `sddctx resume` 基于恢复状态重建的开发上下文 | 状态能够复用 |

## 当前状态说明

- MiniMax 开发记录在执行 `sddctx dev`(需要 `SDDCTX_MINIMAX_API_KEY`)后生成;
  生成前本目录已包含其余全部记录样例。
- 记录中的密钥一律脱敏(`sddctx.config.redact`)。
