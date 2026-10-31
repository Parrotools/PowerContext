import { useEffect, useState } from 'react'
import { CheckCircle, Clock, AlertTriangle, BookOpen } from 'lucide-react'
import { api } from '../api/client'

const MASTERY_CONFIG = {
  mastered: { label: '已掌握', icon: CheckCircle, color: 'text-green-600 bg-green-50' },
  learning: { label: '学习中', icon: Clock, color: 'text-blue-600 bg-blue-50' },
  needs_review: { label: '需复习', icon: AlertTriangle, color: 'text-orange-600 bg-orange-50' },
  unseen: { label: '未学习', icon: BookOpen, color: 'text-gray-400 bg-gray-50' },
}

export default function Review() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [markingTopic, setMarkingTopic] = useState('')
  const [markMastery, setMarkMastery] = useState('mastered')

  useEffect(() => {
    api.getReviewStatus('default')
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleMark = async () => {
    if (!markingTopic.trim()) return
    await api.markMastery({ topic: markingTopic.trim(), mastery: markMastery, user_id: 'default' })
    setMarkingTopic('')
    const updated = await api.getReviewStatus('default').catch(() => null)
    if (updated) setData(updated)
  }

  if (loading) {
    return <div className="flex h-64 items-center justify-center text-gray-400">加载中...</div>
  }

  const topics = data?.topics || []
  const recommendations = data?.recommendations || []

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">复习教练</h1>
        <p className="mt-1 text-sm text-gray-500">PowerContext 追踪学习状态，智能推荐复习计划</p>
      </header>

      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-700">学习概览</h2>
        <p className="text-sm text-gray-600">{data?.study_summary || '暂无数据'}</p>
      </div>

      <section className="rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">标记新知识点</h2>
        <div className="flex gap-2">
          <input value={markingTopic} onChange={e => setMarkingTopic(e.target.value)}
            placeholder="输入知识点名称，如：二叉树旋转" className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          <select value={markMastery} onChange={e => setMarkMastery(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none">
            {Object.entries(MASTERY_CONFIG).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          <button onClick={handleMark} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
            记录
          </button>
        </div>
      </section>

      {recommendations.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">今日推荐复习</h2>
          {recommendations.map((rec, i) => (
            <div key={i} className="rounded-xl border border-orange-100 bg-orange-50/50 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-gray-900">{rec.topic}</h3>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  rec.priority === 'high' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700'
                }`}>
                  {rec.priority === 'high' ? '高优先' : '中优先'}
                </span>
              </div>
              <p className="mt-1 text-sm text-gray-600">{rec.reason}</p>
              {rec.suggested_materials?.length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="text-xs font-medium text-gray-500">相关资料：</p>
                  {rec.suggested_materials.map((m, j) => (
                    <div key={j} className="rounded bg-white p-2 text-xs text-gray-600">
                      <span className="font-medium">{m.title}</span>
                      <span className="ml-2 text-gray-400">score: {m.score?.toFixed(3)}</span>
                      <p className="mt-0.5 line-clamp-1">{m.snippet}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-700">全部知识点 ({topics.length})</h2>
        {topics.length === 0 && (
          <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
            还没有追踪任何知识点，使用上方的表单开始记录
          </div>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          {topics.map((t, i) => {
            const cfg = MASTERY_CONFIG[t.mastery] || MASTERY_CONFIG.unseen
            const Icon = cfg.icon
            return (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
                <div className={`rounded-lg p-1.5 ${cfg.color}`}>
                  <Icon size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{t.topic}</p>
                  <p className="text-xs text-gray-500">
                    {cfg.label} · 复习 {t.review_count} 次
                    {t.last_reviewed && ` · 上次 ${new Date(t.last_reviewed).toLocaleDateString('zh-CN')}`}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
