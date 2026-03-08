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
  const [configStatus, setConfigStatus] = useState(null)
  const [eta, setEta] = useState(null)
  const [queueInfo, setQueueInfo] = useState(null)
  const logsEndRef = useRef(null)
  const pollingRef = useRef(null)

  useEffect(() => {
    loadAll()
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [])

  useEffect(() => {
    if (logsEndRef.current) logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  async function loadAll() {
    try {
      const [dims, data, config, queue] = await Promise.all([
        api.getDimensions().catch(() => []),
        api.preprocessStatus('web_custom_data').catch(() => null),
        api.configStatus('web_custom_data').catch(() => null),
        api.queueStatus().catch(() => null),
      ])
      setDimensions(dims || [])
      setSelectedDims((dims || []).map(d => d.name))
      setDataStatus(data)
      setConfigStatus(config)
      setQueueInfo(queue)
    } catch { /* ignore */ }
  }

  async function loadEta() {
    try {
      const e = await api.estimateTime({
        dim_count: selectedDims.length,
        max_depth: parseInt(localStorage.getItem('taxoadapt_depth') || '2'),
        test_samples: parseInt(localStorage.getItem('taxoadapt_samples') || '0'),
        dataset_folder: 'web_custom_data',
      })
      setEta(e)
      setDataStatus(prev => ({
        ...prev,
        document_count: e.total_documents || prev?.document_count || 0,
        effective_documents: e.effective_documents || e.total_documents || prev?.document_count || 0,
      }))
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (selectedDims.length > 0) loadEta()
  }, [selectedDims])

  function toggleDim(name) {
    setSelectedDims(prev => prev.includes(name) ? prev.filter(d => d !== name) : [...prev, name])
  }

  async function handleRun() {
    if (selectedDims.length === 0) {
      setStatusMsg({ type: 'warning', text: '최소 1개 차원을 선택해주세요' })
      return
    }
    if (!dataStatus?.has_data) {
      setStatusMsg({ type: 'error', text: '데이터가 없습니다. 데이터 소스 페이지에서 파일을 업로드하고 변환하세요.' })
      return
    }
    if (!configStatus?.applied) {
      setStatusMsg({ type: 'error', text: 'Config가 적용되지 않았습니다. 분류 설정 페이지에서 YAML을 업로드하고 적용하세요.' })
      return
    }

    setRunning(true); setLogs([]); setProgress(null); setStatusMsg(null)

    const settings = {
      model: localStorage.getItem('taxoadapt_model') || 'gpt-5-2025-08-07',
      temperature: parseFloat(localStorage.getItem('taxoadapt_temp') || '1.0'),
      max_depth: parseInt(localStorage.getItem('taxoadapt_depth') || '2'),
      max_density: parseInt(localStorage.getItem('taxoadapt_density') || '40'),
      test_samples: parseInt(localStorage.getItem('taxoadapt_samples') || '0'),
      topic: localStorage.getItem('taxoadapt_topic') || 'technology',
      selected_dimensions: selectedDims,
      dataset_folder: 'web_custom_data',
      resume,
    }

    try {
      const result = await api.runClassification(settings)
      if (result.status === 'rejected') {
        setRunning(false)
        setStatusMsg({ type: 'error', text: result.message })
        return
      }
      setRunId(result.run_id)
      setStatusMsg({ type: 'info', text: `실행 시작 (Run: ${result.run_id}) | 예상 시간: ${result.estimated_seconds ? formatTime(result.estimated_seconds) : '계산 중...'}` })

      // SSE first, polling fallback
      try {
        const es = createProgressStream(result.run_id)
        es.onmessage = (event) => handleProgressEvent(JSON.parse(event.data), es)
        es.onerror = () => { es.close(); startPolling(result.run_id) }
      } catch {
        startPolling(result.run_id)
      }
    } catch (e) {
      setRunning(false)
      setStatusMsg({ type: 'error', text: `실행 실패: ${e.message}` })
    }
  }

  function handleProgressEvent(data, es) {
    setProgress(data)
    if (data.logs) setLogs(data.logs)
    if (['completed', 'failed', 'cancelled'].includes(data.status)) {
      setRunning(false)
      if (es) es.close()
      if (data.status === 'completed') setStatusMsg({ type: 'success', text: '분류 완료!' })
      else if (data.status === 'failed') setStatusMsg({ type: 'error', text: `실패: ${data.error || 'Unknown'}` })
      else setStatusMsg({ type: 'warning', text: '사용자에 의해 중지됨' })
    }
  }

  function startPolling(id) {
    pollingRef.current = setInterval(async () => {
      try {
        const data = await api.getProgress(id)
        handleProgressEvent(data, null)
        if (['completed', 'failed', 'cancelled'].includes(data.status)) clearInterval(pollingRef.current)
      } catch { clearInterval(pollingRef.current) }
    }, 2000)
  }

  async function handleCancel() {
    if (!runId) return
    try {
      await api.cancelRun(runId)
      setStatusMsg({ type: 'warning', text: '중지 요청 전송됨. 다음 체크포인트에서 중지됩니다.' })
    } catch { /* ignore */ }
  }

  function formatTime(s) {
    if (s > 3600) return `${Math.floor(s / 3600)}시간 ${Math.floor((s % 3600) / 60)}분`
    if (s > 60) return `${Math.floor(s / 60)}분 ${Math.floor(s % 60)}초`
    return `${Math.floor(s)}초`
  }

  const hasErrors = logs.some(l => l.includes('ERROR') || l.includes('Error'))

  return (
    <div>
      <div className="page-header">
        <h2>분류 실행</h2>
        <p>설정된 파라미터로 특허 기술 분류를 실행합니다.</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* Active Data Summary */}
      <div className="card">
        <div className="card-header"><h3>실행 환경</h3></div>
        <div className="form-row" style={{ gap: 24 }}>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>데이터</label>
            <p style={{ fontWeight: 600, color: dataStatus?.has_data ? 'var(--success)' : 'var(--error)' }}>
              {dataStatus?.has_data
                ? (dataStatus.effective_documents && dataStatus.effective_documents < dataStatus.document_count
                    ? `${dataStatus.effective_documents.toLocaleString()}개 사용 (전체 ${dataStatus.document_count.toLocaleString()}개)`
                    : `${dataStatus.document_count.toLocaleString()}개 문서`)
                : '데이터 없음'}
            </p>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Config</label>
            <p style={{ fontWeight: 600, color: configStatus?.applied ? 'var(--success)' : 'var(--error)' }}>
              {configStatus?.applied ? `${configStatus.applied_files?.length}개 taxo 적용됨` : '미적용'}
            </p>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>모델</label>
            <p style={{ fontWeight: 600 }}>{localStorage.getItem('taxoadapt_model') || 'gpt-5'}</p>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Test Samples</label>
            <p style={{ fontWeight: 600, color: parseInt(localStorage.getItem('taxoadapt_samples') || '0') > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
              {parseInt(localStorage.getItem('taxoadapt_samples') || '0') > 0
                ? `${localStorage.getItem('taxoadapt_samples')}개 (테스트)`
                : '전체'}
            </p>
          </div>
          <div>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>서버 부하</label>
            <p style={{ fontWeight: 600, color: queueInfo?.available_slots > 0 ? 'var(--success)' : 'var(--error)' }}>
              {queueInfo ? `${queueInfo.active_runs}/${queueInfo.max_concurrent} 실행 중` : '-'}
            </p>
          </div>
          {eta && (
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>예상 시간</label>
              <p style={{ fontWeight: 600 }}>{eta.estimated_display}</p>
            </div>
          )}
        </div>
      </div>

      {/* Dimension Selection */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <h3>실행할 차원 ({selectedDims.length}/{dimensions.length})</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedDims(dimensions.map(d => d.name))}>전체</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setSelectedDims([])}>해제</button>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {dimensions.map(dim => (
            <button key={dim.name}
              className={`btn btn-sm ${selectedDims.includes(dim.name) ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => toggleDim(dim.name)}>
              {selectedDims.includes(dim.name) ? '+ ' : ''}{dim.name}
            </button>
          ))}
        </div>
        {dimensions.length === 0 && (
          <div className="alert alert-warning" style={{ marginTop: 10 }}>차원을 먼저 설정하세요.</div>
        )}
      </div>

      {/* Run Controls */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 16 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem' }}>
            <input type="checkbox" checked={resume} onChange={e => setResume(e.target.checked)} /> Resume Mode
          </label>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn btn-primary btn-lg" onClick={handleRun}
            disabled={running || selectedDims.length === 0 || !dataStatus?.has_data || !configStatus?.applied}>
            {running ? '실행 중...' : '분류 실행'}
          </button>
          {running && (
            <button className="btn btn-danger btn-lg" onClick={handleCancel}>중지</button>
          )}
        </div>
        {(!dataStatus?.has_data || !configStatus?.applied) && (
          <p style={{ fontSize: '0.8rem', color: 'var(--error)', marginTop: 10 }}>
            {!dataStatus?.has_data && '데이터를 먼저 업로드하고 변환하세요. '}
            {!configStatus?.applied && 'YAML Config를 먼저 적용하세요.'}
          </p>
        )}
      </div>

      {/* Progress */}
      {progress && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <h3>진행 상황</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={`status-dot ${progress.status}`}></span>
              <span className="badge badge-accent">{progress.status?.toUpperCase()}</span>
              {progress.elapsed_seconds > 0 && (
                <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>경과: {formatTime(progress.elapsed_seconds)}</span>
              )}
              {progress.estimated_seconds > 0 && progress.elapsed_seconds > 0 && (
                <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  / 남은: {formatTime(Math.max(0, progress.estimated_seconds - progress.elapsed_seconds))}
                </span>
              )}
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
          {progress.error && (
            <div className="alert alert-error" style={{ marginTop: 12 }}>
              <strong>오류 발생:</strong> {progress.error}
            </div>
          )}
        </div>
      )}

      {/* Logs */}
      {logs.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <h3>실행 로그</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {hasErrors && <span className="badge badge-error">오류 포함</span>}
              <span className="badge badge-info">{logs.length} lines</span>
            </div>
          </div>
          <div className="log-viewer">
            {logs.map((line, i) => (
              <div key={i} className={`log-line ${line.includes('ERROR') || line.includes('Error') ? 'error' : line.includes('Complete') ? 'success' : ''}`}>
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
