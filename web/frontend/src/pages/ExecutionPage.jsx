import React, { useState, useEffect, useRef } from 'react'
import { api, createProgressStream } from '../api/client.js'

export default function ExecutionPage() {
  const [dimensions, setDimensions] = useState([])
  const [selectedDims, setSelectedDims] = useState([])
  const [running, setRunning] = useState(false)
  const [runId, setRunId] = useState(null)
  const [progress, setProgress] = useState(null)
  const [logs, setLogs] = useState([])
  const [statusMsg, setStatusMsg] = useState(null)
  const [resume, setResume] = useState(false)
  const [dataStatus, setDataStatus] = useState(null)

  const logsEndRef = useRef(null)

  useEffect(() => {
    loadDimensions()
    checkDataStatus()
  }, [])

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  async function loadDimensions() {
    try {
      const dims = await api.getDimensions()
      setDimensions(dims || [])
      setSelectedDims((dims || []).map(d => d.name))
    } catch { /* backend not running */ }
  }

  async function checkDataStatus() {
    try {
      const status = await api.preprocessStatus('web_custom_data')
      setDataStatus(status)
    } catch { /* ignore */ }
  }

  function toggleDim(name) {
    setSelectedDims(prev =>
      prev.includes(name) ? prev.filter(d => d !== name) : [...prev, name]
    )
  }

  async function handleRun() {
    if (selectedDims.length === 0) {
      setStatusMsg({ type: 'warning', text: '최소 1개 차원을 선택해주세요' })
      return
    }

    setRunning(true)
    setLogs([])
    setProgress(null)
    setStatusMsg(null)

    const settings = {
      model: localStorage.getItem('taxoadapt_model') || 'gpt-5-2025-08-07',
      temperature: parseFloat(localStorage.getItem('taxoadapt_temp') || '1.0'),
      max_depth: parseInt(localStorage.getItem('taxoadapt_depth') || '2'),
      max_density: parseInt(localStorage.getItem('taxoadapt_density') || '40'),
      test_samples: parseInt(localStorage.getItem('taxoadapt_samples') || '0'),
      topic: localStorage.getItem('taxoadapt_topic') || 'technology',
      selected_dimensions: selectedDims,
      dataset_folder: 'web_custom_data',
      resume: resume,
    }

    try {
      const result = await api.runClassification(settings)
      setRunId(result.run_id)
      setStatusMsg({ type: 'info', text: `🚀 실행 시작 (Run ID: ${result.run_id})` })

      // Start SSE stream
      const es = createProgressStream(result.run_id)
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setProgress(data)
          if (data.logs) setLogs(data.logs)

          if (data.status === 'completed') {
            setRunning(false)
            setStatusMsg({ type: 'success', text: '✅ 분류 완료!' })
            es.close()
          } else if (data.status === 'failed') {
            setRunning(false)
            setStatusMsg({ type: 'error', text: `❌ 실패: ${data.error || 'Unknown error'}` })
            es.close()
          } else if (data.status === 'cancelled') {
            setRunning(false)
            setStatusMsg({ type: 'warning', text: '⚠️ 사용자에 의해 취소됨' })
            es.close()
          }
        } catch { /* parse error */ }
      }
      es.onerror = () => {
        // Try polling as fallback
        startPolling(result.run_id)
        es.close()
      }
    } catch (e) {
      setRunning(false)
      setStatusMsg({ type: 'error', text: `❌ 실행 실패: ${e.message}` })
    }
  }

  function startPolling(id) {
    const interval = setInterval(async () => {
      try {
        const data = await api.getProgress(id)
        setProgress(data)
        if (data.logs) setLogs(data.logs)
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          setRunning(false)
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)
  }

  async function handleCancel() {
    if (runId) {
      try {
        await api.cancelRun(runId)
        setStatusMsg({ type: 'warning', text: '취소 요청됨...' })
      } catch { /* ignore */ }
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>▶️ 분류 실행</h2>
        <p>설정된 파라미터로 특허 기술 분류를 실행합니다.</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* Data Status */}
      <div className="card">
        <div className="card-header">
          <h3>📊 데이터 상태</h3>
        </div>
        {dataStatus ? (
          <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
            <div>
              <span className={`status-dot ${dataStatus.has_data ? 'completed' : 'failed'}`}></span>
              {' '}
              {dataStatus.has_data
                ? <span style={{ color: 'var(--success)' }}>데이터 준비 완료</span>
                : <span style={{ color: 'var(--error)' }}>데이터 없음</span>
              }
            </div>
            <span className="badge badge-info">{dataStatus.document_count || 0}개 문서</span>
            <span className="badge badge-accent">{dimensions.length}개 차원</span>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)' }}>데이터 상태를 확인 중...</p>
        )}
      </div>

      {/* Dimension Selection */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <h3>🎯 실행할 차원 선택</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedDims(dimensions.map(d => d.name))}>전체 선택</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedDims([])}>전체 해제</button>
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {dimensions.map(dim => (
            <button
              key={dim.name}
              className={`btn btn-sm ${selectedDims.includes(dim.name) ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => toggleDim(dim.name)}
            >
              {selectedDims.includes(dim.name) ? '✓ ' : ''}{dim.name}
            </button>
          ))}
        </div>

        {dimensions.length === 0 && (
          <div className="alert alert-warning" style={{ marginTop: 12 }}>
            차원을 먼저 설정해주세요. ⚙️ 분류 설정 페이지에서 YAML을 업로드하거나 수동 추가하세요.
          </div>
        )}
      </div>

      {/* Run Controls */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <h3>🚀 실행 제어</h3>
        </div>

        <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.87rem' }}>
            <input type="checkbox" checked={resume} onChange={e => setResume(e.target.checked)} />
            🔄 Resume Mode (이어하기)
          </label>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <button
            className="btn btn-primary btn-lg"
            onClick={handleRun}
            disabled={running || selectedDims.length === 0}
          >
            {running ? '⏳ 실행 중...' : '▶️ 분류 실행'}
          </button>
          {running && (
            <button className="btn btn-danger btn-lg" onClick={handleCancel}>
              ⏹ 취소
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      {progress && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <h3>📈 진행 상황</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={`status-dot ${progress.status}`}></span>
              <span className="badge badge-accent">{progress.status?.toUpperCase()}</span>
            </div>
          </div>

          <div className="progress-container">
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{ width: `${progress.progress_pct || 0}%` }}></div>
            </div>
            <div className="progress-info">
              <span>{progress.current_step || ''}</span>
              <span className="progress-pct">{(progress.progress_pct || 0).toFixed(1)}%</span>
            </div>
          </div>

          {progress.current_dimension && (
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: 8 }}>
              현재 차원: <strong style={{ color: 'var(--accent-light)' }}>{progress.current_dimension}</strong>
            </p>
          )}
        </div>
      )}

      {/* Logs */}
      {logs.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <h3>📝 실행 로그</h3>
            <span className="badge badge-info">{logs.length} lines</span>
          </div>
          <div className="log-viewer">
            {logs.map((line, i) => (
              <div key={i} className={`log-line ${line.includes('ERROR') ? 'error' : line.includes('✅') ? 'success' : ''}`}>
                {line}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </div>
  )
}
