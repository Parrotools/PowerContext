# 知序 — 智能学习助手

> 越用越懂你的个人学习助手，基于 SeekDB 混合检索 + PowerContext 记忆引擎

**在线项目主页**：https://zhixu-2t2jbr5w1wu.qoder.zone

> 线上站点是**项目展示页**，用于浏览项目介绍、真实截图和验证结果，不包含后端服务。应用本体请按下文“启动步骤”在本机运行（Docker 后端 + 本地前端）。

**代码仓库**：<https://github.com/Parrotools/PowerContext/tree/2026-competition-ecosystem/qoder>（分支 `2026-competition-ecosystem`，项目位于 `qoder/` 子目录）
**Qoder 开发记录**：[docs/qoder-development-log.md](docs/qoder-development-log.md)

---

## 评审运行说明

### 一、环境要求

| 依赖 | 版本要求 | 用途 | 安装 |
|------|---------|------|------|
| Docker Desktop | 4.x+ | 运行后端服务 | [下载](https://docs.docker.com/get-docker/) |
| Node.js | 18+ | 运行前端（可选） | [下载](https://nodejs.org/) |
| Git | 任意 | 拉取代码 | [下载](https://git-scm.com/) |

> Docker Desktop 安装后请确保已启动。Windows 用户建议使用 PowerShell 或 Git Bash 执行以下命令。

---

### 二、启动步骤

#### 第 1 步：拉取代码

```bash
git clone -b 2026-competition-ecosystem https://github.com/Parrotools/PowerContext.git
cd PowerContext/qoder
```

> 本仓库是 PowerContext 的参赛项目合集，知序项目位于 `qoder/` 子目录。下文的 `docker compose`、`verify.py`、`npm` 命令都请在 `PowerContext/qoder` 目录内执行。

#### 第 2 步：启动后端（Docker 一键启动）

```bash
docker compose up -d --build
```

首次构建约 2-3 分钟（需下载 Python 镜像和安装依赖）。看到以下输出表示启动成功：

```
[+] Running 3/3
 ✔ Container zhixu-powercontext  Healthy
 ✔ Container zhixu-backend       Started
```

#### 第 3 步：确认服务就绪

```bash
# 快速检查（或使用 python verify.py 一键验证全部功能）
curl http://localhost:8000/api/health
```

**预期返回**：

```json
{
  "status": "ok",
  "service": "zhixu-learning-assistant",
  "seekdb": "connected (sqlite-vec)",
  "powercontext": "http://powercontext:8010",
  "llm": "not configured (demo mode)"
}
```

> `seekdb: "connected (sqlite-vec)"` 表示知识库检索引擎就绪。
> `llm: "not configured (demo mode)"` 是正常的——未配置 LLM API Key 时，问答功能以 demo 模式运行，返回结构化占位回答，但检索和记忆功能完全正常。

#### 第 4 步：启动前端（二选一）

**方式 A：本地运行前端（评审请使用此方式）**

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。根路径 `/` 是项目主页，点击“进入应用”进入 `/dashboard`、`/knowledge`、`/chat`、`/review` 等应用页面。

**方式 B：在线项目主页（仅展示）**

线上站点 https://zhixu-2t2jbr5w1wu.qoder.zone 是静态项目展示页，提供项目介绍、真实截图、验证结果和运行说明，不包含后端与数据库。要实际使用应用，请按方式 A 在本机启动后端和前端。站点对未知路径会回退到项目主页，因此直接访问应用直达链接时请从主页入口进入。

> 若需要在 Qoder Sites 页面内连接本机后端，请先按第 2 步启动 Docker 后端；浏览器会发起 Private Network Access 预检，后端已支持该预检。

---

### 三、验证样例

提供两种验证方式：**自动验证脚本**（推荐）和**手动 curl 命令**。

#### 方式 A：自动验证（推荐）

```bash
python verify.py
```

脚本自动执行全部检查并输出结果（以下为 2026-10-31 实测输出，节选）：

```
[1/6] Health Check
  [PASS] Backend reachable              status=200
  [PASS] SeekDB connected               connected (sqlite-vec)
  [PASS] PowerContext configured        http://127.0.0.1:8010

[2/6] Knowledge Base - Document List
  [PASS] List documents API
  [PASS] Sample data seeded             found 6 documents

[3/6] Knowledge Base - Hybrid Search
  [PASS] Search returns results         found 5 results
  [PASS] Result has score               top score: 0.1948

[4/6] Review Coach - Memory Write (PowerContext)
  [PASS] Mark 3 topics                  wrote 3 learning state memories to PowerContext
  [PASS] Topics tracked                 tracking 3 topics

[5/6] Chat - SeekDB Retrieval + PowerContext Memory
  [PASS] Chat returns sources           retrieved 5 sources from SeekDB
  [PASS] Memory written and recalled    recalled 3380 bytes of prepared context
  [PASS] Recalled memory matches question
  [PASS] Backend restarted
  [PASS] Backend healthy after restart  GET /api/health -> 200
  [PASS] Memory survived restart        recalled 3386 bytes after restart

[6/6] PowerContext - Direct Memory Verification
  [PASS] PowerContext reachable         health status: 200
  [PASS] Memory entries exist           found 3 memory entries via backend API

============================================================
  Results: 25/25 passed, 0 failed, 0 skipped
  ALL CHECKS PASSED
============================================================
```

第 5 节会写入一条带本次运行随机标记的问答，立即追问一次确认能召回，然后**重启后端**再追问一次，确认标记仍存在。脚本默认在检测到 Docker 后执行 `docker compose restart backend`；非 Docker 环境可指定自己的重启命令：

```bash
python verify.py --restart-cmd "your-backend-restart-command"
# 或设置环境变量 ZHIXU_RESTART_CMD
```

若无法重启（既没有 Docker 也没有传入命令），该项会输出 `[SKIP]`，不会被计为通过。

#### 方式 B：手动验证

---

#### 样例 1：知识库已预置示例文档

启动时自动导入了 6 篇学习文档。

```bash
curl http://localhost:8000/api/knowledge/documents
```

**预期返回**（6 篇文档，格式如下）：

```json
[
  {"id": 6, "title": "Python 基础语法", "course": "编程基础", "tags": ["Python", "编程", "基础"], "chunk_count": 3, ...},
  {"id": 5, "title": "动态规划入门", "course": "算法", "tags": ["动态规划", "DP", "算法"], "chunk_count": 3, ...},
  {"id": 4, "title": "图的广度优先搜索（BFS）", "course": "算法", ...},
  {"id": 3, "title": "图的基本概念与存储", "course": "数据结构", ...},
  {"id": 2, "title": "二叉树遍历算法", "course": "数据结构", ...},
  {"id": 1, "title": "二叉树基础", "course": "数据结构", ...}
]
```

**验证点**：文档存储于 SeekDB 兼容层（SQLite + sqlite-vec），启动时自动建表和导入。

---

#### 样例 2：混合检索（SeekDB 向量检索 + 全文检索）

搜索「二叉树遍历」：

```bash
curl "http://localhost:8000/api/knowledge/search?q=binary+tree+traversal"
```

**预期返回**（按相关度排序，包含评分）：

```json
{
  "query": "binary tree traversal",
  "results": [
    {
      "chunk_id": 5,
      "document_id": 2,
      "title": "二叉树遍历算法",
      "snippet": "二叉树遍历是访问树中所有节点的基本操作...",
      "course": "数据结构",
      "tags": ["二叉树", "遍历", "DFS", "BFS"],
      "score": 0.52
    },
    {
      "chunk_id": 2,
      "document_id": 1,
      "title": "二叉树基础",
      "snippet": "二叉树是一种重要的数据结构...",
      "score": 0.38
    }
  ],
  "total": 2
}
```

**验证点**：
- **向量检索**：sqlite-vec 扩展计算 cosine distance，语义匹配「二叉树遍历」相关片段
- **全文检索**：FTS5 虚拟表匹配关键词
- **混合排序**：最终分数 = 向量分数 × 60% + 全文分数 × 40%

也可以用中文搜索：

```bash
curl "http://localhost:8000/api/knowledge/search?q=%E5%9B%BE%E7%9A%84%E9%81%8D%E5%8E%86"
```

---

#### 样例 3：复习教练记忆追踪（PowerContext）

**3a. 标记知识点掌握状态**

标记「二叉树遍历」为「学习中」：

```bash
curl -X POST http://localhost:8000/api/review/mastery -H "Content-Type: application/json" -d "{\"user_id\":\"demo\",\"topic\":\"二叉树遍历\",\"mastery\":\"learning\",\"note\":\"需要多练习递归实现\"}"
```

标记「图BFS」为「已掌握」：

```bash
curl -X POST http://localhost:8000/api/review/mastery -H "Content-Type: application/json" -d "{\"user_id\":\"demo\",\"topic\":\"图BFS\",\"mastery\":\"mastered\",\"note\":\"已理解队列实现\"}"
```

标记「动态规划」为「需复习」：

```bash
curl -X POST http://localhost:8000/api/review/mastery -H "Content-Type: application/json" -d "{\"user_id\":\"demo\",\"topic\":\"动态规划\",\"mastery\":\"needs_review\",\"note\":\"状态转移方程容易出错\"}"
```

每次成功返回：

```json
{"ok": true, "topic": "二叉树遍历", "mastery": "learning", "updated": true}
```

**3b. 查看复习状态**

```bash
curl http://localhost:8000/api/review/status/demo
```

**预期返回**：

```json
{
  "user_id": "demo",
  "topics": [
    {"topic": "二叉树遍历", "mastery": "learning", "review_count": 1, ...},
    {"topic": "图BFS", "mastery": "mastered", "review_count": 1, ...},
    {"topic": "动态规划", "mastery": "needs_review", "review_count": 1, ...}
  ],
  "recommendations": [
    {"topic": "动态规划", "priority": "high", "reason": "薄弱知识点，需要重点攻克", ...},
    {"topic": "二叉树遍历", "priority": "medium", ...}
  ],
  "study_summary": "共追踪 3 个知识点，已掌握 1 个，当前有 2 个需要复习。"
}
```

**验证点**：
- PowerContext `memory/remember` API 写入学习状态记忆
- PowerContext `memory/entries/list` API 读取全部记忆条目
- 间隔重复算法根据 mastery 级别计算下次复习时间
- 推荐列表结合 SeekDB 检索推荐相关学习资料

---

#### 样例 4：智能问答（SeekDB 检索 + PowerContext 记忆融合）

```bash
curl -X POST http://localhost:8000/api/chat/message -H "Content-Type: application/json" -d "{\"message\":\"二叉树有哪些遍历方式？\",\"user_id\":\"demo\"}"
```

**预期返回**：

```json
{
  "answer": "[LLM_API_KEY not configured — returning empty response]",
  "sources": [
    {
      "chunk_id": 5,
      "document_id": 2,
      "title": "二叉树遍历算法",
      "snippet": "二叉树遍历是访问树中所有节点的基本操作，分为深度优先和广度优先...",
      "score": 0.52
    },
    ...
  ],
  "memory_context": null,
  "session_id": "default"
}
```

**验证点**：
- `sources` 字段包含 SeekDB 混合检索返回的相关知识库片段
- `answer` 在未配置 LLM API Key 时为 demo 占位符；配置后返回 LLM 基于上下文的真实回答
- 后端自动将本次对话通过 PowerContext `sources/content` API 保存为记忆源，同时写入一条可召回的 Atomic Memory

再发送一次同样的问题（或带相同关键词的问题），本次对话就会通过 `memory_context` 被召回：

```bash
curl -X POST http://localhost:8000/api/chat/message -H "Content-Type: application/json" -d "{\"message\":\"二叉树有哪些遍历方式？\",\"user_id\":\"demo\"}"
```

**真实记忆读写输出**（2026-10-31 实测，一次独立运行）：第一次提问写入记忆，第二次提问返回 3410 字节的 PreparedContext，节选如下（`content` 为真实召回文本，含当次随机标记）：

```json
{
  "memory_context": "PowerContext prepared untrusted historical context...\nBEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n{\"trust\":\"untrusted_history\",\"items\":[{\"citation\":{\"artifact_ref\":{\"family\":\"atomic-memory\",\"artifact_id\":\"art_a9873b5a6c8c40c69218f8a8ba67f6b8\",\"revision\":1}},\"content\":\"Topic: 二叉树遍历算法 | 动态规划入门 | 二叉树基础\\nUser readme-demo asked: README-demo: What are the traversal methods for binary trees?\\nAssistant answered: [LLM_API_KEY not configured — returning empty response]\",\"truncated\":false,\"kind\":\"atomic-memory\"}]}\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1",
  "session_id": "default",
  "sources": [{"title": "二叉树遍历算法"}, {"title": "动态规划入门"}, {"title": "二叉树基础"}]
}
```

在 `verify.py` 的同项实测中，重启后端后再次提问，`memory_context` 仍返回 3386 字节且包含本次问答的随机标记——这条链路由第 5 节自动验证（见“方式 A”的输出）。

> **可选：配置 LLM 获得真实回答**
>
> 编辑 `qoder/.env`，填入 API Key：
> ```
> LLM_API_KEY=sk-your-key-here
> ```
> 重启：`docker compose up -d --build`

---

#### 样例 5：PowerContext 记忆原始记录验证

后端首次启动时会自动创建（或复用）记忆作用域（scope），scope_id 会写入后端数据卷并在重启后继续使用：

```bash
docker compose logs backend | grep "scope ready"
# 输出示例：PowerContext scope ready: scp_xxxxxxxxxxxxxxxx

# 也可以直接从数据卷读取
docker compose exec backend cat /app/data/zhixu_pc_scope_id
```

用该 scope_id 直接查询 PowerContext 服务，确认记忆已持久化：

```bash
curl -X POST http://localhost:8010/v1/memory/entries/list \
  -H "Content-Type: application/json" \
  -d "{\"scope_id\":\"scp_xxxxxxxxxxxxxxxx\",\"include_inactive\":true}"
```

**实测返回**（节选，scope `scp_0fsg8sskmxe1n8dkc6dy4t41sg`）：

```json
{
  "scope_id": "scp_0fsg8sskmxe1n8dkc6dy4t41sg",
  "entries": [
    {
      "artifact": {"family": "atomic-memory", "artifact_id": "art_26fb2f82d4cc4d30b02a11cc3ed0253c", "revision": 1},
      "kind": "chat_interaction",
      "state": "active",
      "text": "Topic: Python 基础语法 | 二叉树基础 | Python 基础语法\nUser verify-test asked: verify-1793419155: What are the traversal methods for binary trees?\nAssistant answer..."
    },
    {
      "artifact": {"family": "atomic-memory", "artifact_id": "art_2d8ac80969ed4e678de810f8b52b96f2", "revision": 1},
      "kind": "chat_interaction",
      "state": "active",
      "text": "Topic: 图的基本概念与存储 | 图的广度优先搜索（BFS） | 动态规划入门\nUser verify-test asked: verify-1793419207: What are the traversal methods for binary trees?..."
    }
  ]
}
```

**验证点**：
- scope_id 持久化在 backend 数据卷 `/app/data/zhixu_pc_scope_id`，重启后复用同一 scope，避免“重启即失忆”；
- PowerContext 作为独立服务运行，记忆数据持久化在其 SQLite 数据库中（Docker 卷 `powercontext-data`）；
- 同一知识点重复标记掌握度时，旧版本通过 `/v1/atomic-memory/lifecycle` 归档，`review_count` 随之递增。

---

### 四、前端界面验证

启动前端后（http://localhost:5173），可在浏览器中验证：

| 页面 | 路径 | 操作 | 预期 |
|------|------|------|------|
| 项目主页 | `/` | 浏览介绍、真实截图、验证结果 | 展示项目定位、核心功能和运行入口 |
| 学习总览 | `/dashboard` | 查看统计卡片 | 显示知识库文档数、追踪知识点数 |
| 知识库 | `/knowledge` | 搜索「二叉树」 | 返回相关文档片段及评分 |
| 知识库 | `/knowledge` | 导入新文档 | 填写标题和内容后提交，文档列表更新 |
| 智能问答 | `/chat` | 发送消息 | 返回回答 + 右侧显示引用的知识库来源 |
| 复习教练 | `/review` | 标记知识点掌握状态 | 状态保存成功，复习推荐列表更新 |

---

### 五、停止与重置

```bash
# 停止所有服务（保留数据）
docker compose down

# 停止并清除所有数据（恢复到初始状态）
docker compose down -v

# 查看服务日志
docker compose logs -f

# 查看单个服务日志
docker compose logs -f backend
docker compose logs -f powercontext
```

---

### 六、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `docker compose up` 报错 port already in use | 8000 或 8010 端口被占用 | 停止占用端口的程序，或修改 `docker-compose.yml` 中的端口映射 |
| 健康检查一直 unhealthy | PowerContext 启动较慢 | 等待 30 秒后重试，或查看日志 `docker compose logs powercontext` |
| curl 返回 `Connection refused` | 服务未就绪 | 等待 `docker compose ps` 显示两个服务均为 `Up (healthy)` |
| 前端页面空白 | 后端未启动或 API 地址不对 | 确认后端 `http://localhost:8000/api/health` 可访问 |
| Windows curl 中文乱码 | CMD 编码问题 | 使用 PowerShell 或 Git Bash 执行命令 |

---

## 项目简介

知序是一个面向学习场景的智能助手，核心特点：

- **知识库管理**：导入文档自动切片、向量化，支持语义 + 关键词混合检索（SeekDB）
- **智能问答**：检索知识库 + 召回学习记忆，生成个性化回答（SeekDB + PowerContext）
- **复习教练**：追踪知识点掌握状态，基于间隔重复推荐复习计划（PowerContext）
- **学习总览**：展示学习进度、薄弱点、复习提醒（PowerContext）

### 技术架构

```
┌─────────────────────────────────────────────────────┐
│  Frontend (React + Vite + Tailwind CSS)             │
│  部署于 Qoder Sites（公网可访问）                      │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼──────────────────────────────┐
│  Backend (Python FastAPI, Docker 容器)               │
├─────────────────────┬───────────────────────────────┤
│  SeekDB 兼容层       │  PowerContext 记忆引擎         │
│  SQLite + sqlite-vec │  独立 Docker 容器              │
│  ─────────────────   │  ────────────────────         │
│  文档存储 + 自动切片   │  学习状态记忆 (Atomic Memory)  │
│  向量嵌入 (384 维)    │  间隔重复调度                  │
│  混合检索 (vec+FTS)  │  上下文召回 (PreparedContext)  │
│  端口: 内置于 backend │  端口: 8010                   │
└─────────────────────┴───────────────────────────────┘
```

---

## 技术说明

### SeekDB 兼容层

项目使用 SQLite + sqlite-vec + FTS5 实现与 SeekDB 相同能力的混合检索：

| 能力 | 实现方式 | 对应 SeekDB 功能 |
|------|---------|----------------|
| 向量检索 | sqlite-vec `vec0` 虚拟表 + cosine distance | `AI_EMBED()` + `cosine_distance()` |
| 全文检索 | FTS5 虚拟表 + BM25 排序 | `MATCH...AGAINST` |
| 混合排序 | 向量 60% + 全文 40% 加权融合 | 单次 SQL 多路召回 |
| 结构化过滤 | SQL WHERE 条件（课程、标签） | 同 |

> 接口层完全兼容 SeekDB，生产环境可无缝切换为真实 SeekDB 实例。

### PowerContext 记忆引擎

PowerContext 以独立 Docker 容器运行（v1.4.1），提供以下能力：

| API | 用途 | 调用场景 |
|-----|------|---------|
| `POST /v1/scopes` | 创建记忆作用域 | 首次启动自动创建 scope |
| `POST /v1/memory/remember` | 写入记忆条目 | 标记知识点掌握状态 |
| `POST /v1/memory/entries/list` | 列出全部记忆 | 获取用户学习状态 |
| `POST /v1/memory/search` | 语义搜索记忆 | 查找相关学习历史 |
| `POST /v1/atomic-memory/lifecycle` | 软删除/版本管理 | 知识点状态更新时归档旧版本 |
| `POST /v1/sources/content` | 保存交互源内容 | 记录每次问答交互 |
| `POST /v1/context/prepare` | 组装有界上下文 | 问答前召回用户画像 |

---

## 项目结构

```
qoder/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口 + 生命周期管理
│   │   ├── config.py                  # 环境变量配置
│   │   ├── models/schemas.py          # Pydantic 数据模型
│   │   ├── routers/
│   │   │   ├── knowledge.py           # 知识库 CRUD + 混合检索 API
│   │   │   ├── chat.py                # 智能问答 API
│   │   │   └── review.py              # 复习教练 API
│   │   └── services/
│   │       ├── seekdb_service.py      # SeekDB 兼容层（SQLite + sqlite-vec + FTS5）
│   │       ├── powercontext_service.py # PowerContext 记忆引擎集成
│   │       └── llm_service.py         # LLM 调用 + Prompt 构建
│   ├── seed_sample.py                 # 示例数据初始化脚本
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/screenshots/            # 真实运行截图（主页展示）
│   ├── src/
│   │   ├── App.jsx                    # 路由配置（项目主页 + 4 个应用页面）
│   │   ├── api/client.js              # API 客户端
│   │   ├── components/                # 通用组件（Layout, Sidebar）
│   │   └── pages/                     # Home, Dashboard, Knowledge, Chat, Review
│   ├── vite.config.js
│   └── package.json
├── docs/
│   └── qoder-development-log.md       # Qoder 开发记录（时间线 / 需求 / 提交 / 测试）
├── docker-compose.yml                 # 一键部署配置（2 个服务）
├── Dockerfile.powercontext            # PowerContext 容器构建
├── start.sh / start.bat               # 一键启动脚本
├── .env                               # Docker 环境变量
├── .env.example                       # 环境变量模板
└── README.md                          # 本文档
```

## 许可证

MIT
