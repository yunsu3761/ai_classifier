import React, { useState, useEffect } from 'react'
import { api } from '../api/client.js'

export default function SettingsPage() {
  const [dimensions, setDimensions] = useState([])
  const [yamlContent, setYamlContent] = useState('')
  const [statusMsg, setStatusMsg] = useState(null)
  const [loading, setLoading] = useState(false)

  // New dimension form
  const [newName, setNewName] = useState('')
  const [newDef, setNewDef] = useState('')
  const [newNodeDef, setNewNodeDef] = useState('')

  // Model settings (persisted in localStorage)
  const [model, setModel] = useState(localStorage.getItem('taxoadapt_model') || 'gpt-5-2025-08-07')
  const [temperature, setTemperature] = useState(parseFloat(localStorage.getItem('taxoadapt_temp') || '1.0'))
  const [maxDepth, setMaxDepth] = useState(parseInt(localStorage.getItem('taxoadapt_depth') || '2'))
  const [maxDensity, setMaxDensity] = useState(parseInt(localStorage.getItem('taxoadapt_density') || '40'))
  const [testSamples, setTestSamples] = useState(parseInt(localStorage.getItem('taxoadapt_samples') || '0'))
  const [topic, setTopic] = useState(localStorage.getItem('taxoadapt_topic') || 'technology')

  useEffect(() => { loadDimensions() }, [])

  // Persist settings to localStorage
  useEffect(() => {
    localStorage.setItem('taxoadapt_model', model)
    localStorage.setItem('taxoadapt_temp', String(temperature))
    localStorage.setItem('taxoadapt_depth', String(maxDepth))
    localStorage.setItem('taxoadapt_density', String(maxDensity))
    localStorage.setItem('taxoadapt_samples', String(testSamples))
    localStorage.setItem('taxoadapt_topic', topic)
  }, [model, temperature, maxDepth, maxDensity, testSamples, topic])

  async function loadDimensions() {
    try {
      const dims = await api.getDimensions()
      setDimensions(dims || [])
    } catch {
      // Backend might not be running
    }
  }

  async function handleYamlUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setLoading(true)
    try {
      const result = await api.uploadYaml(file)
      setStatusMsg({ type: 'success', text: `✅ YAML 로드: ${result.dimension_count}개 차원` })
      loadDimensions()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `❌ YAML 업로드 실패: ${e.message}` })
    } finally {
      setLoading(false)
    }
  }

  async function handleAddDimension() {
    if (!newName || !newDef) {
      setStatusMsg({ type: 'warning', text: '이름과 정의를 입력해주세요' })
      return
    }
    try {
      const config = {
        dimensions: {
          [newName.replace(/\s+/g, '_')]: {
            definition: newDef,
            node_definition: newNodeDef || newDef,
          }
        },
        topic: topic,
      }
      await api.updateDimensions(config)
      setStatusMsg({ type: 'success', text: `✅ 차원 추가: ${newName}` })
      setNewName(''); setNewDef(''); setNewNodeDef('')
      loadDimensions()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `추가 실패: ${e.message}` })
    }
  }

  async function handleDeleteDimension(name) {
    try {
      await api.deleteDimension(name)
      setStatusMsg({ type: 'success', text: `🗑️ 차원 삭제: ${name}` })
      loadDimensions()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `삭제 실패: ${e.message}` })
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>⚙️ 분류 설정</h2>
        <p>모델 파라미터, 차원 구성, 분류 옵션을 설정합니다.</p>
      </div>

      {statusMsg && (
        <div className={`alert alert-${statusMsg.type}`}>
          {statusMsg.text}
        </div>
      )}

      {/* Model Parameters */}
      <div className="card">
        <div className="card-header">
          <h3>🤖 모델 파라미터</h3>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>LLM Model</label>
            <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
              <option value="gpt-5-2025-08-07">GPT-5 (2025-08-07)</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="gpt-4">GPT-4</option>
            </select>
          </div>
          <div className="form-group">
            <label>Temperature</label>
            <input className="form-input" type="number" step="0.1" min="0" max="2"
              value={temperature} onChange={e => setTemperature(parseFloat(e.target.value))} />
          </div>
          <div className="form-group">
            <label>Topic (주제)</label>
            <input className="form-input" type="text" value={topic} onChange={e => setTopic(e.target.value)} />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Max Depth</label>
            <input className="form-input" type="number" min="1" max="10"
              value={maxDepth} onChange={e => setMaxDepth(parseInt(e.target.value))} />
          </div>
          <div className="form-group">
            <label>Max Density</label>
            <input className="form-input" type="number" min="1" max="200"
              value={maxDensity} onChange={e => setMaxDensity(parseInt(e.target.value))} />
          </div>
          <div className="form-group">
            <label>Test Samples (0=전체)</label>
            <input className="form-input" type="number" min="0"
              value={testSamples} onChange={e => setTestSamples(parseInt(e.target.value))} />
          </div>
        </div>
      </div>

      {/* Dimensions */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <h3>📌 Dimension 구성 ({dimensions.length})</h3>
          <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
            📄 YAML 업로드
            <input type="file" accept=".yaml,.yml" onChange={handleYamlUpload} style={{ display: 'none' }} />
          </label>
        </div>

        {dimensions.length === 0 ? (
          <div className="empty-state" style={{ padding: '32px 20px' }}>
            <div className="empty-icon">📋</div>
            <h4>차원이 설정되지 않았습니다</h4>
            <p>YAML 파일을 업로드하거나 아래에서 수동 추가하세요</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {dimensions.map(dim => (
              <div key={dim.name} style={{
                background: 'var(--bg-glass)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: 16,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontWeight: 600, color: 'var(--accent-light)' }}>{dim.name}</span>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDeleteDimension(dim.name)}>🗑️</button>
                </div>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {dim.definition?.substring(0, 200)}{dim.definition?.length > 200 ? '...' : ''}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Add new dimension */}
        <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.9rem', marginBottom: 12, color: 'var(--text-secondary)' }}>➕ 새 차원 추가</h4>
          <div className="form-group">
            <label>차원 이름</label>
            <input className="form-input" placeholder="예: Energy_Efficiency_Improvement"
              value={newName} onChange={e => setNewName(e.target.value)} />
          </div>
          <div className="form-group">
            <label>정의 (Definition)</label>
            <textarea className="form-textarea" rows="3" placeholder="이 차원의 정의를 입력하세요..."
              value={newDef} onChange={e => setNewDef(e.target.value)} />
          </div>
          <div className="form-group">
            <label>노드 정의 (Node Definition)</label>
            <textarea className="form-textarea" rows="3" placeholder="노드 정의 (예시 포함)..."
              value={newNodeDef} onChange={e => setNewNodeDef(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={handleAddDimension}>➕ 차원 추가</button>
        </div>
      </div>
    </div>
  )
}
