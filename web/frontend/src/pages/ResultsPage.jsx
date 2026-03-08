import React, { useState, useEffect } from 'react'
import { api } from '../api/client.js'

function TaxonomyTreeNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2)
  if (!node) return null
  const children = node.children ? (Array.isArray(node.children) ? node.children : Object.values(node.children)) : []
  const hasChildren = children.length > 0
  const paperCount = node.paper_ids?.length || node.papers?.length || 0

  return (
    <li className="tree-node">
      <div className="tree-node-label" onClick={() => hasChildren && setOpen(!open)}>
        {hasChildren ? <span className={`tree-node-toggle ${open ? 'open' : ''}`}>&#9654;</span> : <span style={{ width: 16 }}></span>}
        <span style={{ fontWeight: depth < 2 ? 600 : 400 }}>{node.label || node.name || '(unnamed)'}</span>
        {paperCount > 0 && <span className="tree-node-count">({paperCount})</span>}
      </div>
      {hasChildren && open && (
        <ul className="tree-node-children">
          {children.map((child, i) => <TaxonomyTreeNode key={child.label || i} node={child} depth={depth + 1} />)}
        </ul>
      )}
    </li>
  )
}

export default function ResultsPage() {
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [detail, setDetail] = useState(null)
  const [tableData, setTableData] = useState([])
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
      const [data, table] = await Promise.all([
        api.getRunDetail(runId),
        api.getRunTable(runId).catch(() => [])
      ])
      setDetail(data)
      setTableData(table || [])
      setSelectedRun(runId)
    } catch (e) {
      setStatusMsg({ type: 'error', text: `상세 로드 실패: ${e.message}` })
    }
  }

  function formatDate(str) {
    try { return new Date(str).toLocaleString('ko-KR') } catch { return str || '-' }
  }

  return (
    <div>
      <div className="page-header">
        <h2>분류 결과</h2>
        <p>사용자별 실행 이력과 분류 결과를 확인합니다. (사용자: {api.getUserId()})</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* Run History */}
      <div className="card">
        <div className="card-header">
          <h3>실행 이력 ({runs.length})</h3>
          <button className="btn btn-secondary btn-sm" onClick={loadRuns}>새로고침</button>
        </div>
        {runs.length === 0 ? (
          <div className="empty-state"><h4>실행 이력이 없습니다</h4><p>실행 페이지에서 분류를 실행하세요</p></div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Run ID</th><th>상태</th><th>일시</th><th>모델</th><th>문서</th><th>차원</th><th>작업</th></tr></thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.run_id} style={selectedRun === run.run_id ? { background: 'var(--bg-active)' } : {}}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{run.run_id}</td>
                    <td><span className={`badge badge-${run.status === 'completed' ? 'success' : 'info'}`}>{run.status}</span></td>
                    <td>{formatDate(run.created_at)}</td>
                    <td>{run.model || '-'}</td>
                    <td>{run.total_documents}</td>
                    <td>{run.dimensions?.length || 0}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-primary btn-sm" onClick={() => loadDetail(run.run_id)}>상세</button>
                        <a className="btn btn-secondary btn-sm" href={api.downloadUrl(run.run_id, 'excel')} download>Excel</a>
                        <a className="btn btn-secondary btn-sm" href={api.downloadUrl(run.run_id, 'txt')} download>TXT</a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail */}
      {detail && (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <div className="card-header">
              <h3>Run 상세: {selectedRun}</h3>
              <button className="btn btn-secondary btn-sm" onClick={() => { setDetail(null); setSelectedRun(null) }}>닫기</button>
            </div>
            <div className="form-row" style={{ gap: 24 }}>
              {[
                ['Topic', detail.summary?.topic],
                ['Model', detail.summary?.model],
                ['Documents', detail.summary?.total_documents],
                ['Dimensions', detail.summary?.dimensions?.join(', ')],
              ].map(([k, v]) => (
                <div key={k}>
                  <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{k}</label>
                  <p style={{ fontWeight: 600 }}>{v || '-'}</p>
                </div>
              ))}
            </div>
          </div>

          {detail.taxonomy_tree && Object.keys(detail.taxonomy_tree).length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-header"><h3>Taxonomy 트리</h3></div>
              {Object.entries(detail.taxonomy_tree).map(([dim, tree]) => (
                <div key={dim} style={{ marginBottom: 20 }}>
                  <h4 style={{ fontSize: '0.88rem', color: 'var(--accent-light)', marginBottom: 6 }}>{dim}</h4>
                  <ul className="tree-view"><TaxonomyTreeNode node={tree} /></ul>
                </div>
              ))}
            </div>
          )}

          {/* Data Grid */}
          {tableData.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-header">
                <h3>분류 결과 데이터 ({tableData.length}행)</h3>
                <div style={{ display: 'flex', gap: 8 }}>
                  <a className="btn btn-primary btn-sm" href={api.downloadUrl(selectedRun, 'excel')} download>Excel 다운로드</a>
                  <a className="btn btn-secondary btn-sm" href={api.downloadUrl(selectedRun, 'txt')} download>TXT 다운로드</a>
                </div>
              </div>
              <div className="data-table-wrap" style={{ maxHeight: 500, overflowY: 'auto' }}>
                <table className="data-table">
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-card)' }}>
                    <tr>
                      <th>Dimension</th>
                      <th>Taxonomy Path</th>
                      <th>Node Label</th>
                      <th>Level</th>
                      <th style={{ minWidth: 200 }}>Description</th>
                      <th>Paper ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableData.map((row, i) => (
                      <tr key={i}>
                        <td>{row.dimension}</td>
                        <td style={{ fontSize: '0.82rem', color: 'var(--accent-light)' }}>{row.taxonomy_path}</td>
                        <td style={{ fontWeight: 600 }}>{row.node_label}</td>
                        <td style={{ textAlign: 'center' }}>{row.level}</td>
                        <td style={{ fontSize: '0.8rem', whiteSpace: 'normal', minWidth: 200 }}>{row.description}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{row.paper_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
