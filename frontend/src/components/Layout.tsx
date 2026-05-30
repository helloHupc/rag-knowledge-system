import { Link, Outlet, useLocation } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: '文档管理' },
  { to: '/chunking', label: '切分配置' },
  { to: '/retrieval', label: '检索测试' },
  { to: '/evaluation', label: '评测工作台' },
  { to: '/settings', label: '配置管理' },
  { to: '/api-endpoints', label: 'API 接口' },
]

export function Layout() {
  const location = useLocation()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Knowledge Core</p>
          <h1>知识库管理台</h1>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`sidebar-link ${location.pathname === item.to ? 'active' : ''}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="dashboard">
        <Outlet />
      </main>
    </div>
  )
}
