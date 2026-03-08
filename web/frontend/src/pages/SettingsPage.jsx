import React, { useState, useEffect, useRef } from 'react'
import { api } from '../api/client.js'

export default function SettingsPage() {
  const [dimensions, setDimensions] = useState([])
  const [configStatus, setConfigStatus] = useState(null)
  const [statusMsg, setStatusMsg] = useState(null)
  const [yamlUploading, setYamlUploading] = useState(false)
  const yamlInputRef = useRef(null)

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
  const [saved, setSaved] = useState(false)

  useEffect(() => { loadAll() }, [])

  function saveSettings() {
    localStorage.setItem('taxoadapt_model', model)
    localStorage.setItem('taxoadapt_temp', String(temperature))
    localStorage.setItem('taxoadapt_depth', String(maxDepth))
    localStorage.setItem('taxoadapt_density', String(maxDensity))
    localStorage.setItem('taxoadapt_samples', String(testSamples))
    localStorage.setItem('taxoadapt_topic', topic)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function loadAll() {
    loadDimensions()
    loadConfigStatus()
  }

  async function loadDimensions() {
    try {
      const dims = await api.getDimensions()
      setDimensions(dims || [])
    } catch { /* backend might not be running */ }
  }

  async function loadConfigStatus() {
    try {
      const status = await api.configStatus('web_custom_data')
      setConfigStatus(status)
    } catch { /* ignore */ }
  }

  async function handleYamlUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setYamlUploading(true)
    setStatusMsg(null)
    try {
      const result = await api.uploadYaml(file)
      setStatusMsg({ type: 'success', text: `YAML 로드 완료: ${result.dimension_count}개 차원 (아직 적용 전 — "적용하기" 버튼을 눌러주세요)` })
      await loadAll()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `YAML 업로드 실패: ${e.message}` })
    } finally {
      setYamlUploading(false)
      // Reset file input so same file can be re-uploaded
      if (yamlInputRef.current) yamlInputRef.current.value = ''
    }
  }

  async function handleApplyConfig() {
    setStatusMsg(null)
    try {
      const result = await api.applyConfig('web_custom_data')
      setStatusMsg({ type: 'success', text: result.message })
      loadConfigStatus()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `적용 실패: ${e.message}` })
    }
  }

  async function handleAddDimension() {
    if (!newName || !newDef) {
      setStatusMsg({ type: 'warning', text: '이름과 정의를 입력해주세요' })
      return
    }
    try {
      await api.updateDimensions({
        dimensions: { [newName.replace(/\s+/g, '_')]: { definition: newDef, node_definition: newNodeDef || newDef } },
        topic: topic,
      })
      setStatusMsg({ type: 'success', text: `차원 추가: ${newName}` })
      setNewName(''); setNewDef(''); setNewNodeDef('')
      loadAll()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `추가 실패: ${e.message}` })
    }
  }

  async function handleDeleteDim(name) {
    try {
      await api.deleteDimension(name)
      setStatusMsg({ type: 'success', text: `차원 삭제: ${name}` })
      loadAll()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `삭제 실패: ${e.message}` })
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>분류 설정</h2>
        <p>모델 파라미터와 차원 구성을 설정하고 적용합니다.</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* Config Status */}
      <div className="card" style={{ borderLeft: `3px solid ${configStatus?.applied ? 'var(--success)' : 'var(--warning)'}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 600, color: configStatus?.applied ? 'var(--success)' : 'var(--warning)' }}>
              {configStatus?.applied ? '✓ Config 적용됨' : '✗ Config 미적용'}
            </span>
            {configStatus?.loaded && (
              <span className="badge badge-info" style={{ marginLeft: 12 }}>{configStatus.loaded_dimensions?.length || 0}개 차원 로드됨</span>
            )}
            {configStatus?.applied && (
              <span className="badge badge-success" style={{ marginLeft: 8 }}>{configStatus.applied_files?.length || 0}개 taxo 파일</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {configStatus?.loaded && !configStatus?.applied && (
              <button className="btn btn-primary" onClick={handleApplyConfig}>적용하기</button>
            )}
            {configStatus?.loaded && configStatus?.applied && (
              <button className="btn btn-secondary btn-sm" onClick={handleApplyConfig}>재적용</button>
            )}
          </div>
        </div>
      </div>

      {/* Model Parameters — with explicit Save button */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <h3>모델 파라미터</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {saved && <span style={{ color: 'var(--success)', fontSize: '0.82rem', fontWeight: 600 }}>저장됨 ✓</span>}
            <button className="btn btn-primary btn-sm" onClick={saveSettings}>설정 저장</button>
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>LLM Model</label>
            <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
              <option value="gpt-5-2025-08-07">GPT-5</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="gpt-4o">GPT-4o</option>
            </select>
          </div>
          <div className="form-group"><label>Temperature</label>
            <input className="form-input" type="number" step="0.1" min="0" max="2" value={temperature} onChange={e => setTemperature(parseFloat(e.target.value) || 0)} />
          </div>
          <div className="form-group"><label>Topic</label>
            <input className="form-input" type="text" value={topic} onChange={e => setTopic(e.target.value)} />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group"><label>Max Depth</label>
            <input className="form-input" type="number" min="1" max="10" value={maxDepth} onChange={e => setMaxDepth(parseInt(e.target.value) || 1)} />
          </div>
          <div className="form-group"><label>Max Density</label>
            <input className="form-input" type="number" min="1" max="200" value={maxDensity} onChange={e => setMaxDensity(parseInt(e.target.value) || 1)} />
          </div>
          <div className="form-group">
            <label>Test Samples (0=전체)</label>
            <input className="form-input" type="number" min="0" value={testSamples} onChange={e => setTestSamples(parseInt(e.target.value) || 0)} />
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
              테스트 시 소량의 문서만 사용하려면 값을 설정하세요. 0이면 전체 실행.
            </p>
          </div>
        </div>
      </div>

      {/* Dimensions */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <h3>Dimension 구성 ({dimensions.length})</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {yamlUploading && <div className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }}></div>}
            <label className="btn btn-secondary btn-sm" style={{ cursor: yamlUploading ? 'not-allowed' : 'pointer', opacity: yamlUploading ? 0.5 : 1 }}>
              {yamlUploading ? 'YAML 로딩...' : 'YAML 업로드'}
              <input ref={yamlInputRef} type="file" accept=".yaml,.yml" onChange={handleYamlUpload}
                style={{ display: 'none' }} disabled={yamlUploading} />
            </label>
          </div>
        </div>

        {dimensions.length === 0 ? (
          <div className="empty-state" style={{ padding: '28px 20px' }}>
            <h4>차원이 설정되지 않았습니다</h4>
            <p>YAML 파일을 업로드하거나 아래에서 수동으로 추가하세요</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {dimensions.map(dim => (
              <div key={dim.name} style={{ background: 'var(--bg-glass)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, color: 'var(--accent-light)' }}>{dim.name}</span>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDeleteDim(dim.name)}>삭제</button>
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.5 }}>
                  {dim.definition?.substring(0, 200)}{dim.definition?.length > 200 ? '...' : ''}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Add dimension */}
        <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.88rem', marginBottom: 10, color: 'var(--text-secondary)' }}>새 차원 추가</h4>
          <div className="form-group"><label>차원 이름</label>
            <input className="form-input" placeholder="예: Energy_Efficiency" value={newName} onChange={e => setNewName(e.target.value)} />
          </div>
          <div className="form-group"><label>정의</label>
            <textarea className="form-textarea" rows="2" value={newDef} onChange={e => setNewDef(e.target.value)} />
          </div>
          <div className="form-group"><label>노드 정의</label>
            <textarea className="form-textarea" rows="2" value={newNodeDef} onChange={e => setNewNodeDef(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={handleAddDimension}>추가</button>
        </div>
      </div>
    </div>
  )
}
