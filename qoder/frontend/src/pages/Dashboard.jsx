import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, MessageCircle, Repeat, TrendingUp } from 'lucide-react'
import { api } from '../api/client'

const STAT_CARDS = [
  { key: 'docs', icon: BookOpen, label: '知识库文档', color: 'text-blue-600 bg-blue-50', to: '/knowledge' },
  { key: 'chats', icon: MessageCircle, label: '近期问答', color: 'text-green-600 bg-green-50', to: '/chat' },
  { key: 'review', icon: Repeat, label: '待复习', color: 'text-orange-600 bg-orange-50', to: '/review' },
  { key: 'mastered', icon: TrendingUp, label: '已掌握', color: 'text-purple-600 bg-purple-50', to: '/review' },
]

export default function Dashboard() {
  const [stats, setStats] = useState({ docs: 0, chats: 0, review: 0, mastered: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const [docs, history, review] = await Promise.all([
          api.listDocuments().catch(() => []),
          api.getHistory('default').catch(() => ({ history: [] })),
          api.getReviewStatus('default').catch(() => null),
        ])
        setStats({
          docs: docs.length,
          chats: history?.history?.length ?? 0,
          review: review?.recommendations?.length ?? 0,
          mastered: review?.topics?.filter(t => t.mastery === 'mastered').length ?? 0,
        })
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">学习总览</h1>
        <p className="mt-1 text-sm text-gray-500">欢迎回来，继续今天的学习吧</p>
      </header>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {STAT_CARDS.map(({ key, icon: Icon, label, color, to }) => (
          <Link key={key} to={to} className="rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md">
            <div className={`inline-flex rounded-lg p-2 ${color}`}>
              <Icon size={20} />
            </div>
            <p className="mt-3 text-2xl font-bold text-gray-900">{loading ? '—' : stats[key]}</p>
            <p className="text-sm text-gray-500">{label}</p>
          </Link>
        ))}
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">快速开始</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <QuickAction
            title="导入笔记"
            desc="将课程笔记、论文、课件导入知识库，自动切片和向量化"
            to="/knowledge"
            action="去导入"
          />
          <QuickAction
            title="提问学习"
            desc="基于知识库的智能问答，助手记得你的学习进度和薄弱点"
            to="/chat"
            action="去提问"
          />
          <QuickAction
            title="复习巩固"
            desc="根据艾宾浩斯遗忘曲线，智能推荐今日复习内容"
            to="/review"
            action="去复习"
          />
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">技术架构</h2>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <TechItem name="SeekDB" desc="混合检索引擎 — 向量 + 全文 + 结构化，单次 SQL 完成多模态检索" />
          <TechItem name="PowerContext" desc="记忆引擎 — 学习状态追踪、薄弱点识别、跨会话上下文召回" />
          <TechItem name="Qoder" desc="开发平台 — 需求拆解、编码、调试全流程由 Qoder 完成" />
          <TechItem name="Qoder Sites" desc="部署平台 — 项目网站托管与发布" />
        </div>
      </section>
    </div>
  )
}

function QuickAction({ title, desc, to, action }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <p className="mt-1 text-xs text-gray-500">{desc}</p>
      <Link to={to} className="mt-3 inline-block text-sm font-medium text-brand-600 hover:text-brand-700">
        {action} →
      </Link>
    </div>
  )
}

function TechItem({ name, desc }) {
  return (
    <div className="rounded-lg bg-gray-50 p-3">
      <span className="font-semibold text-brand-700">{name}</span>
      <span className="mx-2 text-gray-300">—</span>
      <span className="text-gray-600">{desc}</span>
    </div>
  )
}
