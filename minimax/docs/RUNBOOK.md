# 运行说明(RUNBOOK)

评审从干净环境开始,按本说明依次执行即可完成:依赖安装 → 数据初始化 → 启动模块 → 执行验证样例。
所有命令默认在 `minimax/` 目录内执行(下称仓库根)。

## 1. 依赖与版本

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | >= 3.11(实测 3.12) | 建议 `uv venv --python 3.12` |
| uv | 任意近期版本 | 仅用于安装;pip 亦可 |
| sddctx(本模块) | 1.0.0 | `minimax/pyproject.toml`,editable 安装 |
| pylibseekdb | >= 1.4.0,< 2 | 嵌入式 seekdb,Linux/macOS |
| powercontext[cli,server] | == 1.2.0 | PyPI 官方发行版:提供 `PowerContextClient` SDK 与 `powercontext server` |
| pyobvector / sqlalchemy / httpx / pydantic | 见 `pyproject.toml` | 随模块自动安装 |
| pytest | >= 8.0 | 运行业务工程与模块测试 |

无 Docker、无外部数据库服务:seekdb 以进程内嵌入实例运行,PowerContext Server 以本机回环进程运行。

## 2. 配置步骤(环境变量)

| 变量 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `SDDCTX_MINIMAX_API_KEY` | 无 | dev 步骤必填 | MiniMax API Key(也识别 `MINIMAX_API_KEY`) |
| `SDDCTX_MINIMAX_BASE_URL` | `https://api.minimaxi.com/v1` | 否 | 国内平台;国际平台用 `https://api.minimax.io/v1` |
| `SDDCTX_MINIMAX_MODEL` | `MiniMax-M3.1-Flash` | 否 | 平台旧型号会随下线退役,当前可用列表见 `GET /v1/models` |
| `SDDCTX_MINIMAX_TEMPERATURE` | `1.0` | 否 | MiniMax M 系列推荐 1.0 |
| `SDDCTX_POWERCONTEXT_URL` | `http://127.0.0.1:8000` | 否 | PowerContext Server 地址 |
| `SDDCTX_POWERCONTEXT_TOKEN` | 无 | 否 | Server 开启鉴权时填 |
| `SDDCTX_SEEKDB_PATH` | `minimax/.sddctx-data/seekdb` | 否 | 嵌入式 seekdb 数据目录 |
| `SDDCTX_HOME` | 自动定位 minimax/ | 否 | 规格/业务工程/记录的根目录 |

全部配置项的占位示例见 `env.example`;凭据一律走环境变量,仓库内无真实密钥;`.sddctx-data/`(seekdb 数据、PowerContext 数据、
服务日志)已被 `.gitignore` 排除,属可重置的运行时状态。

## 3. 数据初始化

```bash
# 1) 安装模块与依赖(干净环境只需一次)
uv venv .venv --python 3.12
uv pip install -e ".[dev]"

# 2) 导入工程资料到 seekdb(规格 3 份 + 业务工程代码/测试 → 全文索引)
.venv/bin/sddctx import
# 重复执行幂等;内容有变化时自动升版本
```

## 4. 启动模块

```bash
# PowerContext Server(任务状态存储;默认 SQLite,本机回环,无需鉴权)
mkdir -p .sddctx-data
.venv/bin/powercontext server run --env-file powercontext.env
# 看到 "Uvicorn running on http://127.0.0.1:8000" 即就绪;保持前台运行
```

`sddctx` 本身是 CLI,无需常驻;每次调用即模块的一次运行(也是“重启”验收的载体)。

## 5. 调用入口(输入/输出)

| 命令 | 输入 | 输出 |
| --- | --- | --- |
| `sddctx import` | `specs/` 与 `sample-project/` 下的资料 | seekdb 资产表(逐条写入 `records/db-query-log.md`) |
| `sddctx context --task "<任务描述>" [--json] [--out FILE]` | 任务自然语言描述 | markdown(或 JSON)开发上下文:规格条目/代码/测试/任务状态,全部带来源 |
| `sddctx dev --task "<任务>" --task-id t1` | 任务描述 + 上下文 | 调用 MiniMax 生成并应用补丁;产物在 `records/minimax/<run>/` |
| `sddctx verify --task-id t1 --phase before\|after [--target-tests tests/…py]` | 目标测试路径 | 运行目标+回归测试;日志存 `records/verify/`;验证结果写入 PowerContext |
| `sddctx status --task-id t1 [--complete …] [--pending …]` / `--set-board FILE` | 看板调整 | 读写 PowerContext 任务看板 |
| `sddctx resume --task-id t1` | 无 | 从 PowerContext 读取看板+验证结果,并重建开发上下文 |
| `sddctx diff --run-dir <目录>` | dev 运行目录 | 修改前后统一差异(`code.diff.md`) |
| `sddctx reset [--force]` | 无 | 清空 seekdb 数据目录与生成记录(规格/代码恢复用 git) |
| `sddctx doctor` | 无 | 体检:seekdb/资产/PowerContext/MiniMax/业务工程测试逐项就绪检查 |
| `sddctx context --task … --check examples/run-task-filter/task.json` | 任务清单 | 对照清单核对必要规格/代码/测试来源,全部命中输出 ✔ 且退出码 0 |

## 6. 测试命令

```bash
# 业务工程(修改前:目标测试失败;修改后:全部通过)
cd sample-project && ../.venv/bin/python -m pytest tests && cd ..
# PYTHONPATH 已由 sddctx verify 自动注入;手工运行也可:
#   PYTHONPATH=src python -m pytest tests

# sddctx 模块自测
.venv/bin/python -m pytest tests
```

## 7. 一键验证样例

```bash
bash examples/run-task-filter/run-demo.sh
```

脚本依次执行:重置 → 导入 → 上下文 → before 验证 → (设置 MiniMax Key 后)dev → after 验证 → resume。
逐步手工操作与每步预期输出见 [VALIDATION.md](VALIDATION.md)。

## 8. 已知限制

1. `sddctx dev` 需要有效的 MiniMax API Key;Key 未配置时其余全部功能可用。
2. seekdb 嵌入式实例仅支持 Linux/macOS(Windows 不支持 pylibseekdb);单进程访问。
3. PowerContext Server 默认 SQLite 存储(产品默认行为);未配置推理模型,自动记忆提取/生成式
   handoff 不启用——sddctx 仅使用显式 Memory 写入与检索,属于产品稳定能力。
4. 全文检索为词面匹配(Analyzer v1 + seekdb 原生索引),同义改写的召回依赖词面重叠;
   向量通道为扩展方向,当前未启用(不依赖任何 embedding API,评审环境零外部依赖)。
5. `sddctx dev` 解析 MiniMax 输出的 `=== FILE: path ===` 围栏块;模型输出格式异常时
   不会写任何文件,可在 `minimax-response.md` 排查后重试。
6. 上下文中代码文件内容超过 4000 字符时截断展示(完整内容始终以来源文件为准)。
7. MiniMax 平台会定期下线旧型号(如 M2/M2.1/M2.5/M2.7 已于 2026-10 退役,调用返回 404/2069);
   默认型号随之更新,提交前请用 `sddctx doctor` 或 `GET /v1/models` 确认当前可用。
