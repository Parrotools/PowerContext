import { useEffect, useState } from 'react'
import { Upload, Search, Trash2, FileText } from 'lucide-react'
import { api } from '../api/client'

export default function Knowledge() {
  const [documents, setDocuments] = useState([])
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const [form, setForm] = useState({ title: '', content: '', course: '', tags: '', source_type: 'markdown' })
  const [loading, setLoading] = useState(false)

  const loadDocs = async () => {
    const docs = await api.listDocuments().catch(() => [])
    setDocuments(docs)
  }

  useEffect(() => { loadDocs() }, [])

  const handleImport = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await api.createDocument({
        ...form,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
      })
      setForm({ title: '', content: '', course: '', tags: '', source_type: 'markdown' })
      setShowImport(false)
      await loadDocs()
    } catch (err) {
      alert('导入失败: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const res = await api.search(query)
      setSearchResults(res)
    } catch (err) {
      alert('搜索失败: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('确定删除此文档？')) return
    await api.deleteDocument(id).catch(() => {})
    await loadDocs()
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">知识库</h1>
          <p className="mt-1 text-sm text-gray-500">管理学习资料，SeekDB 混合检索驱动</p>
        </div>
        <button onClick={() => setShowImport(!showImport)} className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
          <Upload size={16} /> 导入文档
        </button>
      </header>

      {showImport && (
        <form onSubmit={handleImport} className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <input required placeholder="文档标题" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
            <input placeholder="所属课程" value={form.course} onChange={e => setForm({ ...form, course: e.target.value })}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          </div>
          <textarea required placeholder="文档内容（支持 Markdown）" rows={8} value={form.content}
            onChange={e => setForm({ ...form, content: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          <input placeholder="标签（逗号分隔）" value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none" />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowImport(false)} className="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100">取消</button>
            <button type="submit" disabled={loading} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
              {loading ? '导入中...' : '导入'}
            </button>
          </div>
        </form>
      )}

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="搜索知识库 — 支持自然语言语义检索" className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none" />
        </div>
        <button onClick={handleSearch} disabled={loading} className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200">搜索</button>
      </div>

      {searchResults && (
        <section className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-700">
            搜索结果 <span className="text-gray-400">({searchResults.total} 条)</span>
          </h2>
          {searchResults.results.map((r, i) => (
            <div key={i} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-900">{r.title}</span>
                <span className="text-xs text-brand-600 font-mono">score: {r.score.toFixed(3)}</span>
              </div>
              <p className="mt-1 text-xs text-gray-600 line-clamp-3">{r.snippet}</p>
              <div className="mt-2 flex gap-2">
                {r.course && <span className="rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-700">{r.course}</span>}
                {(r.tags || []).map((t, j) => <span key={j} className="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-600">{t}</span>)}
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-700">全部文档 ({documents.length})</h2>
        {documents.length === 0 && (
          <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400">
            暂无文档，点击「导入文档」开始构建知识库
          </div>
        )}
        {documents.map(doc => (
          <div key={doc.id} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
            <div className="flex items-center gap-3">
              <FileText size={18} className="text-gray-400" />
              <div>
                <p className="text-sm font-medium text-gray-900">{doc.title}</p>
                <p className="text-xs text-gray-500">
                  {doc.course || '未分类'} · {doc.chunk_count} 个片段 · {doc.source_type}
                </p>
              </div>
            </div>
            <button onClick={() => handleDelete(doc.id)} className="text-gray-400 hover:text-red-500">
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </section>
    </div>
  )
}
