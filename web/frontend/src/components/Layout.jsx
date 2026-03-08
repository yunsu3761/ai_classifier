import React from 'react'
import { Link, useLocation } from 'react-router-dom'

const navItems = [
  { path: '/',           icon: '📂', label: '데이터 소스',    desc: 'Data Sources' },
  { path: '/settings',   icon: '⚙️', label: '분류 설정',     desc: 'Settings' },
  { path: '/execution',  icon: '▶️', label: '실행',          desc: 'Execution' },
  { path: '/results',    icon: '📊', label: '결과',          desc: 'Results' },
]

export default function Layout({ children }) {
  const location = useLocation()

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>TaxoAdapt</h1>
          <p>특허 기술 분류 시스템</p>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p>v1.0.0 — Patent Classifier</p>
        </div>
      </aside>

      <main className="main-content fade-in">
        {children}
      </main>
    </div>
  )
}
