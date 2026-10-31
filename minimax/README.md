# 规有所依——面向软件持续演进的 SDD 上下文管理系统

> MiniMax × OceanBase 企业赛题作品 · 2026 OceanBase 数据库大赛
>
> 本目录是参赛仓库 `powercontext` 分支 `2026-competition-ecosystem` 下的赛题资产,自包含、可独立运行。

## 一句话说明

`sddctx` 是一个面向规格驱动开发(SDD)的上下文管理 CLI:把工程资料(规格 / 代码 / 测试)导入
**seekdb** 检索,按开发任务组装出带真实来源的开发上下文,交给 **MiniMax** 完成代码修改,
用目标/回归测试验证,并把任务进展与验证结果存入 **PowerContext**,重启后可恢复继续。

```
                ┌──────────────────────────  sddctx CLI  ──────────────────────────┐
  specs/        │  import ────► seekdb(工程资料 + 原生全文索引)                    │
  sample-project│  context ───► 检索选择(规格条目/代码/测试)──► 开发上下文(带来源)│
  (业务工程)    │      ▲                         │                                 │
                │      │                         ▼                                 │
                │  task_state ◄── PowerContext(看板/验证结果/dev-run,重启可复用)   │
                │      │                                                            │
                │  dev ───────► MiniMax(OpenAI 兼容)──► 解析 FILE 块 ──► 应用补丁  │
                │  verify ────► 目标/回归测试 ──► 结果写回 PowerContext             │
                └──────────────────────────────────────────────────────────────────┘
                       records/:db-query-log / powercontext-log / minimax/* / verify/*
```

## 目录结构

```
minimax/
├── README.md               ← 本文件(一页技术说明)
├── pyproject.toml          ← sddctx 模块及依赖
├── src/sddctx/             ← 上下文模块源码
│   ├── cli.py              ← 调用入口(import/context/dev/verify/status/resume/diff/reset/doctor)
│   ├── seekdb_store.py     ← 嵌入式 seekdb 存储:工程资料表 + 原生全文索引
│   ├── importer.py         ← 资料导入(内容变化自动升版本)
│   ├── context_builder.py  ← 检索选择与上下文组装(规格条目/代码/测试/任务状态)
│   ├── task_state.py       ← PowerContext SDK:任务看板与验证结果的保存/复用
│   ├── minimax_client.py   ← MiniMax chat completions 客户端(OpenAI 兼容)
│   ├── agent.py            ← dev 流程:上下文→MiniMax→解析 FILE 块→应用补丁→留档
│   ├── runner.py           ← verify 流程:目标/回归测试、退出码、代码版本留档
│   ├── analyzer.py         ← 中英文分词(CJK 单字+二元组),供全文索引使用
│   └── assets.py           ← 工程资料收集与规格条目解析
├── specs/                  ← 工程规格(SPEC-001/002/003,markdown,条目化)
├── sample-project/         ← 业务工程:checkout 订单结算服务(可运行、带 pytest 测试)
├── examples/run-task-filter/  ← 验证样例(任务定义 + 一键脚本)
├── docs/RUNBOOK.md         ← 运行说明(依赖、配置、初始化、入口、测试命令、已知限制)
├── docs/VALIDATION.md      ← 验证样例(步骤、预期结果、规格更新演示、重置方法)
├── records/                ← 技术使用记录(MiniMax 开发记录/数据库查询/PowerContext 读写)
└── tests/                  ← sddctx 模块自测(pytest)
```

## 技术分工(必须承担的作用)

| 技术 | 承担的作用 | 实现位置 | 记录 |
| --- | --- | --- | --- |
| **seekdb**(嵌入式,pylibseekdb) | 存储工程资料(规格条目/代码/测试)与全文索引;每次上下文构建都在 seekdb 内完成 `MATCH … AGAINST` 检索与过滤,查询结果直接构成任务上下文 | `seekdb_store.py`、`importer.py`、`context_builder.py` | `records/db-query-log.md`(逐条 SQL、参数、命中) |
| **PowerContext**(v1.2.0,官方 SDK + Server) | 保存任务进展(看板:已完成/待办)与验证结果(Memory 条目);模块重启后经 `search_memory` 读取,并用于重建开发上下文 | `task_state.py`、`cli.py resume/status` | `records/powercontext-log.md`(逐次写入/读取) |
| **MiniMax**(OpenAI 兼容 API,默认 MiniMax-M3.1-Flash) | 接收完整开发上下文,生成目标文件的新内容,由模块解析并写入业务工程 | `minimax_client.py`、`agent.py` | `records/minimax/<run>/`(请求、响应、快照、差异、开发日志) |

## 上下文选择方式(可解释、确定性)

1. 任务文本经 Analyzer v1 分词(英文按词;中文拆单字 `u_x` 与相邻二元组 `b_x_y`);
2. 在 seekdb 原生 FULLTEXT 索引上按 `spec_entry` / `code` / `test` 三类分别执行
   `SELECT … WHERE MATCH(searchable_text) AGAINST(:query) ORDER BY score DESC LIMIT n`,
   相关性打分与过滤全部在数据库内完成;
3. 从任务文本抽取代码标识符(snake_case / CamelCase),对路径、符号或正文命中的资产加成;
4. 类别内按“全文得分 + 标识符加成”排序取 Top-N,零分丢弃;
5. 输出四段上下文:规格条目(带编号与来源)、相关代码、验证测试、任务状态(PowerContext)。
   每一项都标注真实来源(`路径#条目`、版本号、得分),来源均可在 seekdb 中回查。
6. 规格更新后重新执行 `sddctx import`,内容变化自动升版本,后续上下文即使用新内容
   (模块每次都实时查库,不存在固定答案)。

## 六项必做项对照

| 验收项 | 本作品实现 |
| --- | --- |
| 能够运行 | `docs/RUNBOOK.md`:三条命令完成依赖安装、数据初始化、启动模块、执行验证样例;不依赖未交付的本地状态 |
| MiniMax 实际参与 | `sddctx dev` 真实调用 MiniMax 生成补丁并应用;`records/minimax/*/devlog.md` 记录任务、上下文、请求/响应与逐文件修改,与 `code.diff.md` 对应 |
| 上下文正确 | `sddctx context` 输出规格条目/代码/测试均带真实来源;规格更新重新导入后输出立即使用新内容(见 `docs/VALIDATION.md` 第 6 步) |
| 数据库实际参与 | 工程资料存于嵌入式 seekdb(26+ 资产、原生全文索引);上下文构建的检索 SQL 逐条记录在 `records/db-query-log.md` |
| 状态能够复用 | 任务看板与验证结果写入 PowerContext Memory;`sddctx resume` 在全新进程读取并基于恢复的状态重建上下文(见 `docs/VALIDATION.md` 第 7 步) |
| 代码修改有效 | 目标测试 `tests/test_order_query_filter.py` 修改前失败(行为未实现)、修改后全部通过,回归测试同步通过;`records/verify/` 记录命令、退出码、git 版本与日志 |

## 快速开始

```bash
cd minimax
uv venv .venv --python 3.12 && uv pip install -e ".[dev]"   # 依赖安装
.venv/bin/sddctx import                                     # 数据初始化(导入工程资料)
.venv/bin/powercontext server run --env-file powercontext.env   # 启动状态服务
.venv/bin/sddctx doctor                                     # 体检:各组件就绪检查
.venv/bin/sddctx context --task "为订单查询增加最小金额筛选条件"               # 构建上下文
```

配置示例见 `env.example`(占位值,勿提交真实凭据)。

完整流程与验收步骤见 [docs/RUNBOOK.md](docs/RUNBOOK.md) 与 [docs/VALIDATION.md](docs/VALIDATION.md)。
