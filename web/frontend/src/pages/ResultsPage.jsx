import React, { useState, useEffect } from 'react'
import { api } from '../api/client.js'

function TaxonomyTreeNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2)
  if (!node) return null

  const children = node.children
    ? (Array.isArray(node.children) ? node.children : Object.values(node.children))
    : []
  const hasChildren = children.length > 0
  const paperCount = node.paper_ids?.length || node.papers?.length || 0

  return (
    <li className="tree-node">
      <div className="tree-node-label" onClick={() => hasChildren && setOpen(!open)}>
        {hasChildren && (
          <span className={`tree-node-toggle ${open ? 'open' : ''}`}>▶</span>
        )}
        {!hasChildren && <span style={{ width: 16 }}></span>}
        <span style={{ fontWeight: depth < 2 ? 600 : 400 }}>{node.label || node.name || '(unnamed)'}</span>
        {paperCount > 0 && <span className="tree-node-count">({paperCount})</span>}
        {node.source && <span className="badge badge-accent" style={{ marginLeft: 6 }}>{node.source}</span>}
      </div>
      {hasChildren && open && (
        <ul className="tree-node-children">
          {children.map((child, i) => (
            <TaxonomyTreeNode key={child.label || child.name || i} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function ResultsPage() {
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [detail, setDetail] = useState(null)
  const [statusMsg, setStatusMsg] = useState(null)

  useEffect(() => { loadRuns() }, [])

  async function loadRuns() {
    try {
      const data = await api.listRuns('')
      setRuns(data.runs || [])
    } catch { /* ignore */ }
  }

  async function loadDetail(runId) {
    try {
      const data = await api.getRunDetail(runId)
      setDetail(data)
      setSelectedRun(runId)
    } catch (e) {
      setStatusMsg({ type: 'error', text: `상세 로드 실패: ${e.message}` })
    }
  }

  function formatDate(str) {
    if (!str) return '-'
    try {
      return new Date(str).toLocaleString('ko-KR')
    } catch { return str }
  }

  return (
    <div>
      <div className="page-header">
        <h2>📊 분류 결과</h2>
        <p>실행 이력과 분류 결과를 확인하고 다운로드합니다.</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* Run History */}
      <div className="card">
        <div className="card-header">
          <h3>📋 실행 이력 ({runs.length})</h3>
          <button className="btn btn-secondary btn-sm" onClick={loadRuns}>🔄 새로고침</button>
        </div>

        {runs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📭</div>
            <h4>실행 이력이 없습니다</h4>
            <p>▶️ 실행 페이지에서 분류를 실행하세요</p>
          </div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>상태</th>
                  <th>일시</th>
                  <th>모델</th>
                  <th>문서수</th>
                  <th>차원수</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.run_id} style={selectedRun === run.run_id ? { background: 'var(--bg-active)' } : {}}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{run.run_id}</td>
                    <td>
                      <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'info'}`}>
                        {run.status}
                      </span>
                    </td>
                    <td>{formatDate(run.created_at)}</td>
                    <td>{run.model || '-'}</td>
                    <td>{run.total_documents}</td>
                    <td>{run.dimensions?.length || 0}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-primary btn-sm" onClick={() => loadDetail(run.run_id)}>📖 상세</button>
                        <a className="btn btn-secondary btn-sm" href={api.downloadResults(run.run_id)} download>📥 다운로드</a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Run Detail */}
      {detail && (
        <>
          {/* Summary */}
          <div className="card" style={{ marginTop: 20 }}>
            <div className="card-header">
              <h3>📊 Run 상세: {selectedRun}</h3>
              <button className="btn btn-secondary btn-sm" onClick={() => { setDetail(null); setSelectedRun(null) }}>✕ 닫기</button>
            </div>

            <div className="form-row">
              <div>
                <label style={{ fontSize: '0.73rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Topic</label>
                <p style={{ fontWeight: 600 }}>{detail.summary?.topic || '-'}</p>
              </div>
              <div>
                <label style={{ fontSize: '0.73rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model</label>
                <p style={{ fontWeight: 600 }}>{detail.summary?.model || '-'}</p>
              </div>
              <div>
                <label style={{ fontSize: '0.73rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Documents</label>
                <p style={{ fontWeight: 600 }}>{detail.summary?.total_documents || 0}</p>
              </div>
              <div>
                <label style={{ fontSize: '0.73rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Dimensions</label>
                <p style={{ fontWeight: 600 }}>{detail.summary?.dimensions?.join(', ') || '-'}</p>
              </div>
            </div>
          </div>

          {/* Taxonomy Tree */}
          {detail.taxonomy_tree && Object.keys(detail.taxonomy_tree).length > 0 && (
            <div className="card" style={{ marginTop: 20 }}>
              <div className="card-header">
                <h3>🌳 Taxonomy 트리</h3>
              </div>
              {Object.entries(detail.taxonomy_tree).map(([dim, tree]) => (
                <div key={dim} style={{ marginBottom: 24 }}>
                  <h4 style={{ fontSize: '0.9rem', color: 'var(--accent-light)', marginBottom: 8 }}>
                    📌 {dim}
                  </h4>
                  <ul className="tree-view">
                    <TaxonomyTreeNode node={tree} />
                  </ul>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
