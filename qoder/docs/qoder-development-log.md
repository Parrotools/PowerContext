# Qoder 开发记录 — 知序（ZhiXu）

本记录整理自 2026-10-31 的真实 Qoder 开发会话与仓库提交，只记录可以核对的需求、文件、提交和测试输出。

- 项目：知序 — 基于 SeekDB 混合检索 + PowerContext 记忆引擎的学习助手
- 仓库：<https://github.com/Parrotools/PowerContext>
- 分支：`2026-competition-ecosystem`
- 子目录：`qoder/`
- 应用代码截止提交：`f9881aef`（本轮修复见 `git log`）

## 一、时间线

| 时间（2026-10-31，UTC+8） | 阶段 | 主要工作 | 结果 / 提交 |
|---|---|---|---|
| 09:20 | 项目搭建 | 在 Qoder 中生成后端（FastAPI + SeekDB 兼容层）、前端（React + Vite）、Docker 编排和验证脚本 | `f5e6cce7` feat(qoder): add ZhiXu learning assistant（43 个文件，3269 行） |
| 09:24 | 文档 | 在 README 增加 Qoder Sites 站点地址 | `38d8ce97` docs(qoder): add Qoder Sites URL to README |
| 10:45 | 记忆闭环（第一轮） | 修复 PowerContext 调用：统一 scope、prepare 查询归一化、调整 verify 检查 | `f9881aef` fix(qoder): repair PowerContext memory round-trip |
| 11:00–11:40 | 测评问题定位 | 针对“数据或记忆无法正确读回和复用”，逐项核对 PowerContext 1.4.1 契约、scope 生命周期、浏览器跨域和部署可达性 | 定位到 4 类根因（见第二节） |
| 11:40–12:05 | 记忆闭环（第二轮） | 修复 422 请求体、scope 持久化、CORS/PNA、记忆类型、聊天写入记忆；verify 增加“写入→重启→召回” | 全部检查通过（25/25） |
| 12:05–12:30 | 项目主页 | 新增根路由项目主页，应用迁到 `/dashboard` 等路由；补真实截图、仓库/文档链接、本地体验说明 | 本轮提交（见 `git log`） |
| 12:30 起 | 文档与验收 | 补本开发记录、重写 README 运行说明、重新构建部署，并用未登录浏览器完整走查 | 本轮提交（见 `git log`） |

## 二、主要需求与处理

### 1. 修复“记忆写不进去 / 读不回来”

会话中的原始反馈是：测评显示“数据或记忆无法正确读回和复用”。逐项排查后确认了四个具体原因：

1. **两个请求体不符合 PowerContext 1.4.1 契约**：`sources/content` 与 `context/prepare` 使用了旧字段，服务端返回 422。改为 `scope_id` + `source_id` / `query` + `max_bytes`。
2. **scope 只在进程内缓存**：后端重启后重新创建 scope，之前写入的记忆落在旧 scope 里，导致“重启即失忆”。改为把 scope_id 持久化到数据卷文件，并在启动时先校验 scope 是否仍然存在。
3. **浏览器跨域与 Private Network Access 预检失败**：Qoder Sites 页面调用 `localhost:8000` 时预检被拒。补齐 `https://*.qoder.zone` / `https://*.qoder.site` 正则和 `allow_private_network`。
4. **聊天只写了 Source，没有可召回的 Atomic Memory**：Topic Memory 蒸馏需要 LLM worker，未配置时 Source 永远不会变成可检索记忆。改为聊天同时写入 Atomic Memory，保证问答历史可立即召回。

### 2. 验证脚本要求

要求 `verify.py` 能证明“聊天写入 → 重启后端 → 仍能召回”，而不是只测接口连通。实现：

- 第 5 节写入带时间戳标记的问答，立即追问一次，检查召回内容包含标记；
- 通过 `--restart-cmd`（或 `ZHIXU_RESTART_CMD`）重启后端；未指定时在检测到 Docker 后默认执行 `docker compose restart backend`；
- 重启后再次追问，要求标记仍出现在 `memory_context` 中；
- 无法重启时明确输出 `[SKIP]`，不伪装成通过。

### 3. 网站改成“项目主页 + 应用入口”

原先 `/` 直接跳到应用，不符合“项目网站”的定位。现在：

- `/` 为项目主页：项目简介、解决的问题、核心功能、架构、真实截图、验证结果、仓库链接、开发记录链接、本地体验入口；
- 应用保留在 `/dashboard`、`/knowledge`、`/chat`、`/review`；
- 未知路径回退到项目主页，避免直达链接 404；
- 侧边栏增加“项目主页”入口。

### 4. 运行说明与线上定位

明确线上 Qoder Sites 只是**项目展示页**（静态前端，不含后端），应用按 Docker + 本地前端运行；README 中写死仓库 URL、分支和 `qoder/` 子目录。

## 三、产出文件

| 文件 | 说明 |
|---|---|
| `backend/app/services/powercontext_service.py` | PowerContext 1.4.1 调用、scope 持久化、聊天记忆写入、上下文召回 |
| `backend/app/main.py` | CORS 正则 + Private Network Access |
| `backend/app/models/schemas.py` | `memory_context: str \| None`，与 PreparedContext 返回类型一致 |
| `backend/app/routers/chat.py` | 把 `user_id` 传入记忆写入 |
| `backend/app/services/llm_service.py` | 将召回的记忆注入 prompt |
| `verify.py` | 25 项自动检查，含重启召回验证 |
| `frontend/src/pages/Home.jsx` | 项目主页（介绍、截图、验证结果、运行入口） |
| `frontend/src/App.jsx`、`components/Sidebar.jsx` | 根路由 + 应用路由、项目主页入口 |
| `frontend/public/screenshots/*.png` | 5 张真实运行截图 |
| `docs/qoder-development-log.md` | 本开发记录 |
| `README.md` | 评审运行说明、真实记忆读写输出 |

## 四、提交记录

| 提交 | 说明 |
|---|---|
| `f5e6cce7` | feat(qoder): add ZhiXu learning assistant — full-stack project for 2026 competition |
| `38d8ce97` | docs(qoder): add Qoder Sites URL to README |
| `f9881aef` | fix(qoder): repair PowerContext memory round-trip |
| 本轮提交 | 修复 422 / scope 持久化 / CORS / 记忆闭环验证 + 项目主页 + 开发记录 + README（推送后以 `git log` 中的 SHA 为准） |

## 五、测试记录

### 1. 自动验证（真实输出，2026-10-31 12:06）

```text
[1/6] Health Check
  [PASS] Backend reachable              status=200
  [PASS] SeekDB connected               connected (sqlite-vec)
  [PASS] PowerContext configured        http://127.0.0.1:8010

[2/6] Knowledge Base - Document List
  [PASS] List documents API
  [PASS] Sample data seeded             found 6 documents
  [PASS] Document titles valid

[3/6] Knowledge Base - Hybrid Search
  [PASS] Search API
  [PASS] Search returns results         found 5 results
  [PASS] Result has score               top score: 0.1948
  [PASS] Result has snippet             snippet length: 406

[4/6] Review Coach - Memory Write (PowerContext)
  [PASS] Mark 3 topics                  wrote 3 learning state memories to PowerContext
  [PASS] Get review status
  [PASS] Topics tracked                 tracking 3 topics
  [PASS] Recommendations generated      generated 2 recommendations

[5/6] Chat - SeekDB Retrieval + PowerContext Memory
  [PASS] Chat API
  [PASS] Chat returns sources           retrieved 5 sources from SeekDB
  [PASS] Source has relevance score     score: 0.2205
  [PASS] Memory written and recalled    recalled 3380 bytes of prepared context
  [PASS] Recalled memory matches question
  [PASS] Backend restarted
  [PASS] Backend healthy after restart  GET /api/health -> 200
  [PASS] Memory survived restart        recalled 3386 bytes after restart

[6/6] PowerContext - Direct Memory Verification
  [PASS] PowerContext reachable         health status: 200
  [PASS] Memory entries listable
  [PASS] Memory entries exist           found 3 memory entries via backend API

Results: 25/25 passed, 0 failed, 0 skipped
ALL CHECKS PASSED
```

本轮重启使用本机后端的真实进程重启命令（PowerShell 脚本结束 8000 端口进程后重新拉起 uvicorn）；评审在 Docker 环境下直接运行 `python verify.py` 即可，脚本会默认使用 `docker compose restart backend`。

### 2. 浏览器走查

用未登录窗口访问部署后的项目主页，按“看介绍与截图 → 打开应用 → 按 README 启动后端 → 在问答页写入并追问 → 查看右侧记忆上下文”的顺序完成走查，应用页可正常展示知识库召回与 PowerContext 记忆。

### 3. 真实记忆输出

详见 `README.md`“真实记忆读写输出”一节，节选与本次测试一致：写入后立即召回 3380 字节，重启后召回 3386 字节，二者都包含当次问答的随机标记。
