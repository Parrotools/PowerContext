import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  Brain,
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  Github,
  GraduationCap,
  Layers,
  MessageCircle,
  Play,
  Repeat,
  Search,
  ShieldCheck,
  Terminal,
} from 'lucide-react'

const REPO_URL = 'https://github.com/Parrotools/PowerContext/tree/2026-competition-ecosystem/qoder'
const README_URL = 'https://github.com/Parrotools/PowerContext/blob/2026-competition-ecosystem/qoder/README.md'
const DEV_LOG_URL = 'https://github.com/Parrotools/PowerContext/blob/2026-competition-ecosystem/qoder/docs/qoder-development-log.md'

const features = [
  {
    icon: Database,
    title: 'SeekDB 混合检索',
    desc: '文档导入后自动切片、向量化，向量检索与全文检索在一次查询中融合排序。',
  },
  {
    icon: Brain,
    title: 'PowerContext 长期记忆',
    desc: '学习状态、问答交互以 Atomic Memory 持久化，重启服务后仍能按问题召回。',
  },
  {
    icon: MessageCircle,
    title: '带记忆的智能问答',
    desc: '回答同时引用知识库片段与历史学习上下文，右侧实时展示召回的记忆原文。',
  },
  {
    icon: Repeat,
    title: '复习教练',
    desc: '按掌握度与间隔重复算法安排复习，薄弱知识点自动进入今日推荐。',
  },
]

const screenshots = [
  {
    src: '/screenshots/dashboard.png',
    title: '学习总览',
    desc: '文档数量、待复习项与知识掌握情况一屏可见。',
  },
  {
    src: '/screenshots/chat-memory.png',
    title: '问答 + 记忆召回',
    desc: 'SeekDB 返回引用来源，PowerContext 在右侧展示召回的历史记忆。',
  },
  {
    src: '/screenshots/knowledge.png',
    title: '知识库',
    desc: '导入、浏览学习资料，并直接验证混合检索结果与评分。',
  },
  {
    src: '/screenshots/review.png',
    title: '复习教练',
    desc: '标记掌握度后，复习计划与推荐资料随之更新。',
  },
]

const verification = [
  '后端健康检查、SeekDB 连接、PowerContext 配置',
  '6 篇示例文档导入与混合检索（向量 + 全文）',
  '3 个知识点写入、读回与复习推荐生成',
  '问答检索 5 条引用，并写入学习记忆',
  '同一问题二次提问召回已写入的问答记忆',
  '重启后端进程后再次召回同一记忆',
  '直接读取 PowerContext 记忆条目成功',
]

const memoryExcerpt = `{
  "citation": {
    "artifact_ref": {
      "family": "atomic-memory",
      "artifact_id": "art_a9873b5a6c8c40c69218f8a8ba67f6b8",
      "revision": 1
    }
  },
  "content": "Topic: 二叉树遍历算法 | 动态规划入门 | 二叉树基础\\nUser readme-demo asked: README-demo: What are the traversal methods for binary trees?",
  "kind": "atomic-memory"
}`

function SectionTitle({ eyebrow, title, desc }) {
  return (
    <div className="mb-8 max-w-2xl">
      <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-bold text-gray-900 sm:text-3xl">{title}</h2>
      {desc && <p className="mt-3 text-sm leading-6 text-gray-600">{desc}</p>}
    </div>
  )
}

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50 text-gray-900">
      <header className="sticky top-0 z-20 border-b border-gray-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-2 font-bold text-brand-700">
            <span className="text-xl">📚</span>
            知序
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-gray-600 md:flex">
            <a href="#problem" className="hover:text-brand-700">解决的问题</a>
            <a href="#features" className="hover:text-brand-700">核心功能</a>
            <a href="#screenshots" className="hover:text-brand-700">真实截图</a>
            <a href="#verify" className="hover:text-brand-700">验证结果</a>
            <a href="#run" className="hover:text-brand-700">本地体验</a>
            <a href={DEV_LOG_URL} target="_blank" rel="noreferrer" className="hover:text-brand-700">开发记录</a>
          </nav>
          <div className="flex items-center gap-2">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="hidden items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 sm:inline-flex"
            >
              <Github size={16} /> 代码仓库
            </a>
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              进入应用 <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="border-b border-gray-200 bg-gradient-to-b from-brand-50 via-white to-white">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[1.15fr_0.85fr] lg:py-24">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-brand-100 bg-white px-3 py-1 text-xs font-medium text-brand-700">
                <GraduationCap size={14} /> Qoder × OceanBase PowerContext 2026 · 生态应用
              </span>
              <h1 className="mt-5 text-4xl font-extrabold leading-tight tracking-tight text-gray-900 sm:text-5xl">
                知序
                <span className="mt-2 block text-2xl font-semibold text-gray-600 sm:text-3xl">
                  越用越懂你的个人学习助手
                </span>
              </h1>
              <p className="mt-5 max-w-xl text-base leading-7 text-gray-600">
                把课程资料变成可检索的知识库，把每次提问与复习沉淀为长期记忆。
                基于 SeekDB 混合检索与 PowerContext 记忆引擎，学习助手可以跨会话记住你的进度、薄弱点和历史问答。
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  to="/dashboard"
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-700"
                >
                  <Play size={16} /> 进入应用
                </Link>
                <a
                  href={README_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-5 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  <FileText size={16} /> 运行说明
                </a>
                <a
                  href={DEV_LOG_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:text-brand-800"
                >
                  开发记录 <ExternalLink size={14} />
                </a>
              </div>
              <p className="mt-4 text-xs leading-5 text-gray-500">
                本站是项目主页。应用需要按运行说明在本地启动后端（Docker）与前端后体验；
                在线页面本身不保存数据。
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 self-center">
              {[
                { value: '25/25', label: '自动验证通过' },
                { value: '6', label: '预置学习文档' },
                { value: '4', label: '核心功能页面' },
                { value: '3386 B', label: '重启后召回上下文' },
              ].map(item => (
                <div key={item.label} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                  <p className="text-2xl font-extrabold text-brand-700">{item.value}</p>
                  <p className="mt-1 text-xs text-gray-500">{item.label}</p>
                </div>
              ))}
              <div className="col-span-2 rounded-xl border border-green-200 bg-green-50 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-green-800">
                  <ShieldCheck size={16} /> 记忆闭环已验证
                </div>
                <p className="mt-1.5 text-xs leading-5 text-green-700">
                  聊天写入 → 后端重启 → 同一问题再次召回，PowerContext 返回 3386 字节历史上下文。
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="problem" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <SectionTitle
            eyebrow="问题"
            title="学习工具不缺内容，缺的是连续的记忆"
            desc="资料散落在笔记、课件和对话里，传统问答每次都从零开始，复习计划也无法反映真实掌握情况。"
          />
          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                icon: Search,
                title: '检索割裂',
                desc: '关键词搜索找不到语义相近的内容，向量检索又缺少精确匹配，资料越多越难定位。',
              },
              {
                icon: Brain,
                title: '记不住学习状态',
                desc: '问答会话关闭后上下文丢失，助手无法知道你学过什么、哪里薄弱、上次问到哪。',
              },
              {
                icon: Repeat,
                title: '复习没有依据',
                desc: '复习计划靠手工安排，缺少掌握度与时间间隔的联动，容易反复看已会的内容。',
              },
            ].map(item => (
              <div key={item.title} className="rounded-2xl border border-gray-200 bg-white p-6">
                <item.icon className="text-brand-600" size={22} />
                <h3 className="mt-4 font-semibold text-gray-900">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-gray-600">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="features" className="border-y border-gray-200 bg-white">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <SectionTitle
              eyebrow="核心功能"
              title="检索、记忆、问答、复习形成闭环"
              desc="SeekDB 负责找到资料，PowerContext 负责记住学习过程，两者在每次问答中汇合。"
            />
            <div className="grid gap-4 sm:grid-cols-2">
              {features.map(feature => (
                <div key={feature.title} className="flex gap-4 rounded-2xl border border-gray-200 p-6">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                    <feature.icon size={21} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{feature.title}</h3>
                    <p className="mt-1.5 text-sm leading-6 text-gray-600">{feature.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-8 grid gap-4 rounded-2xl bg-slate-900 p-6 text-white sm:grid-cols-3 sm:p-8">
              <div className="flex items-center gap-3">
                <Layers size={20} className="text-brand-100" />
                <div>
                  <p className="text-sm font-semibold">前端</p>
                  <p className="text-xs text-slate-300">React + Vite + Tailwind</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Database size={20} className="text-brand-100" />
                <div>
                  <p className="text-sm font-semibold">检索</p>
                  <p className="text-xs text-slate-300">SeekDB 兼容层 · 向量 + FTS5</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Brain size={20} className="text-brand-100" />
                <div>
                  <p className="text-sm font-semibold">记忆</p>
                  <p className="text-xs text-slate-300">PowerContext 1.4.1 · Atomic Memory</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="screenshots" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <SectionTitle
            eyebrow="真实截图"
            title="本地运行后的实际界面"
            desc="截图来自本项目运行实例，数据由示例文档、复习记录与真实问答产生。"
          />
          <div className="grid gap-5 sm:grid-cols-2">
            {screenshots.map(item => (
              <figure key={item.title} className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
                <img src={item.src} alt={item.title} className="aspect-[16/10] w-full object-cover object-top" />
                <figcaption className="px-5 py-4">
                  <p className="text-sm font-semibold text-gray-900">{item.title}</p>
                  <p className="mt-1 text-xs leading-5 text-gray-600">{item.desc}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section id="verify" className="border-y border-gray-200 bg-white">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[0.9fr_1.1fr]">
            <div>
              <SectionTitle
                eyebrow="验证结果"
                title="可复现的自动验收"
                desc="在项目根目录运行 python verify.py，脚本会写入记忆、重启后端并再次召回。"
              />
              <ul className="space-y-3">
                {verification.map(item => (
                  <li key={item} className="flex items-start gap-2.5 text-sm text-gray-700">
                    <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-green-600" />
                    {item}
                  </li>
                ))}
              </ul>
              <div className="mt-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm font-semibold text-green-800">
                Results: 25/25 passed, 0 failed, 0 skipped
              </div>
            </div>
            <div className="rounded-2xl border border-gray-800 bg-slate-950 p-5">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <Terminal size={14} /> PreparedContext 召回原文
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-slate-200">{memoryExcerpt}</pre>
              <p className="mt-4 text-xs leading-5 text-slate-400">
                artifact_id 与 revision 来自 PowerContext 返回的真实记忆引用；同一问题在后端重启后仍能命中。
              </p>
            </div>
          </div>
        </section>

        <section id="run" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <SectionTitle
            eyebrow="本地体验"
            title="三步启动，在线站点只做展示"
            desc="网站用于展示项目与评审入口；应用的数据能力依赖本地后端，请按以下步骤运行。"
          />
          <div className="grid gap-4 lg:grid-cols-3">
            {[
              {
                step: '01',
                title: '拉取代码',
                code: `git clone -b 2026-competition-ecosystem \\
  https://github.com/Parrotools/PowerContext.git
cd PowerContext/qoder`,
              },
              {
                step: '02',
                title: '启动后端',
                code: `docker compose up -d --build
curl http://localhost:8000/api/health`,
              },
              {
                step: '03',
                title: '启动前端',
                code: `cd frontend
npm install
npm run dev`,
              },
            ].map(item => (
              <div key={item.step} className="rounded-2xl border border-gray-200 bg-white p-5">
                <p className="text-xs font-bold text-brand-600">{item.step}</p>
                <h3 className="mt-2 font-semibold text-gray-900">{item.title}</h3>
                <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-200">{item.code}</pre>
              </div>
            ))}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <a
              href={README_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
            >
              <FileText size={16} /> 完整运行与验证说明
            </a>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-brand-700"
            >
              <Github size={16} /> 查看 qoder/ 源码
            </a>
            <a
              href={DEV_LOG_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-sm font-semibold text-gray-700 hover:text-brand-700"
            >
              <BookOpen size={16} /> Qoder 开发记录
            </a>
          </div>
          <p className="mt-4 text-xs leading-5 text-gray-500">
            本地应用地址 http://localhost:5173 。线上站点根路径是项目主页，应用页面需要本地后端提供数据。
          </p>
        </section>
      </main>

      <footer className="border-t border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-xs text-gray-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>知序 · Qoder × OceanBase PowerContext 2026 生态应用</p>
          <div className="flex items-center gap-4">
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-brand-700">GitHub</a>
            <a href={DEV_LOG_URL} target="_blank" rel="noreferrer" className="hover:text-brand-700">开发记录</a>
            <a href={README_URL} target="_blank" rel="noreferrer" className="hover:text-brand-700">运行说明</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
