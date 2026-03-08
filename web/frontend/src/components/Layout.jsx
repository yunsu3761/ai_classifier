import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client.js'

const navItems = [
  { path: '/',           icon: '📂', label: '데이터 소스',    desc: 'Data Sources' },
  { path: '/settings',   icon: '⚙️', label: '분류 설정',     desc: 'Settings' },
  { path: '/execution',  icon: '▶️', label: '실행',          desc: 'Execution' },
  { path: '/results',    icon: '📊', label: '결과',          desc: 'Results' },
]

export default function Layout({ children }) {
  const location = useLocation()
  const [userId, setUserId] = useState(api.getUserId())
  const [editing, setEditing] = useState(false)
  const [nameInput, setNameInput] = useState(userId)

  function handleSave() {
    const newId = nameInput.trim() || userId
    api.setUserId(newId)
    setUserId(newId)
    setEditing(false)
  }

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>사용자:</span>
            {editing ? (
              <div style={{ display: 'flex', gap: 4 }}>
                <input className="form-input" style={{ height: 24, fontSize: '0.72rem', padding: '0 6px', width: 100 }}
                  value={nameInput} onChange={e => setNameInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSave()} autoFocus />
                <button className="btn btn-primary btn-sm" style={{ padding: '0 6px', height: 24, fontSize: '0.7rem' }} onClick={handleSave}>OK</button>
              </div>
            ) : (
              <span onClick={() => setEditing(true)} style={{ cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem', color: 'var(--accent-light)' }}
                title="Click to change user ID">
                {userId}
              </span>
            )}
          </div>
          <p style={{ marginTop: 6 }}>v2.0 — Patent Classifier</p>
        </div>
      </aside>

      <main className="main-content fade-in">
        {children}
      </main>
    </div>
  )
}
