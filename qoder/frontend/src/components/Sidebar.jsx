import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BookOpen, MessageCircle, Repeat } from 'lucide-react'

const links = [
  { to: '/dashboard', icon: LayoutDashboard, label: '学习总览' },
  { to: '/knowledge', icon: BookOpen, label: '知识库' },
  { to: '/chat', icon: MessageCircle, label: '智能问答' },
  { to: '/review', icon: Repeat, label: '复习教练' },
]

export default function Sidebar() {
  return (
    <aside className="flex w-56 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center gap-2 border-b border-gray-200 px-5 py-4">
        <span className="text-xl">📚</span>
        <h1 className="text-lg font-bold text-brand-700">知序</h1>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-200 p-4 text-xs text-gray-400">
        SeekDB + PowerContext
      </div>
    </aside>
  )
}
