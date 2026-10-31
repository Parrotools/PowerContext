import { useState, useRef, useEffect } from 'react'
import { Send, BookOpen, Brain } from 'lucide-react'
import { api } from '../api/client'

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '你好！我是知序，你的智能学习助手。我可以基于你的知识库回答问题，还能记住你的学习进度和薄弱点。试试问我一个问题吧！' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastSources, setLastSources] = useState([])
  const [lastMemory, setLastMemory] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    try {
      const res = await api.sendMessage(text)
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer }])
      setLastSources(res.sources || [])
      setLastMemory(res.memory_context)
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `出错了: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900">智能问答</h1>
        <p className="mt-1 text-sm text-gray-500">SeekDB 知识检索 + PowerContext 学习记忆，越用越懂你</p>
      </header>

      <div className="flex flex-1 gap-4 overflow-hidden">
        <div className="flex flex-1 flex-col rounded-xl border border-gray-200 bg-white">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-xl bg-gray-100 px-4 py-2.5 text-sm text-gray-500">思考中...</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-gray-200 p-3">
            <div className="flex gap-2">
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
                placeholder="输入你的问题..."
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
              <button onClick={send} disabled={loading || !input.trim()}
                className="flex items-center gap-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
                <Send size={16} /> 发送
              </button>
            </div>
          </div>
        </div>

        <aside className="hidden w-72 flex-col gap-4 overflow-y-auto lg:flex">
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700">
              <BookOpen size={16} className="text-brand-600" /> 引用来源
            </div>
            {lastSources.length === 0 ? (
              <p className="text-xs text-gray-400">提问后将显示引用的知识库内容</p>
            ) : (
              <div className="space-y-2">
                {lastSources.map((s, i) => (
                  <div key={i} className="rounded-lg bg-gray-50 p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-700 truncate">{s.title}</span>
                      <span className="text-xs text-brand-600 font-mono">{s.score?.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500 line-clamp-2">{s.snippet}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700">
              <Brain size={16} className="text-purple-600" /> 记忆上下文
            </div>
            {lastMemory ? (
              <pre className="whitespace-pre-wrap text-xs text-gray-600 leading-relaxed">{lastMemory}</pre>
            ) : (
              <p className="text-xs text-gray-400">PowerContext 将在此展示召回的学习记忆</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
