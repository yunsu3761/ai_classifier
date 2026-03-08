import React, { useState, useRef, useEffect } from 'react'
import { api } from '../api/client.js'

export default function DataSourcePage() {
  const [files, setFiles] = useState([])
  const [converted, setConverted] = useState([])
  const [preview, setPreview] = useState(null)
  const [previewFile, setPreviewFile] = useState('')
  const [uploading, setUploading] = useState(false)
  const [converting, setConverting] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [statusMsg, setStatusMsg] = useState(null)
  const [dataStatus, setDataStatus] = useState(null)
  const fileInputRef = useRef(null)

  // On mount: check existing data FIRST, then load file lists
  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    await loadDataStatus() // Check existing converted data first
    loadFiles()
    loadConverted()
  }

  async function loadFiles() {
    try {
      const data = await api.listFiles()
      setFiles(data.files || [])
    } catch (e) {
      // Silently handle - server might not be running
    }
  }

  async function loadConverted() {
    try {
      const data = await api.listConverted()
      setConverted(data.files || [])
    } catch { /* ignore */ }
  }

  async function loadDataStatus() {
    try {
      const data = await api.preprocessStatus('web_custom_data')
      setDataStatus(data)
    } catch { /* ignore */ }
  }

  async function handleUpload(fileObj) {
    setUploading(true)
    setStatusMsg(null)
    try {
      const result = await api.uploadFile(fileObj)
      setStatusMsg({ type: 'success', text: `업로드 완료: ${result.filename} (${result.file_type})` })
      loadAll()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `업로드 실패: ${e.message}` })
    } finally {
      setUploading(false)
    }
  }

  async function handlePreview(file) {
    try {
      const data = await api.previewFile(file.filename)
      setPreview(data)
      setPreviewFile(file.filename)
    } catch (e) {
      setStatusMsg({ type: 'error', text: `미리보기 실패: ${e.message}` })
    }
  }

  async function handleConvert(file) {
    setConverting(file.filename)
    setStatusMsg(null)
    try {
      const fileId = file.filename.split('_')[0]
      const result = await api.convertToTxt({ file_id: fileId, dataset_folder: 'web_custom_data' })
      if (result.success) {
        setStatusMsg({ type: 'success', text: `변환 완료: ${result.total_documents}개 문서 → internal.txt` })
        loadAll()
      } else {
        setStatusMsg({ type: 'error', text: `변환 실패: ${result.message}` })
      }
    } catch (e) {
      setStatusMsg({ type: 'error', text: `변환 오류: ${e.message}` })
    } finally {
      setConverting(null)
    }
  }

  async function handleDelete(file) {
    setStatusMsg(null)
    try {
      await api.deleteFile(file.filename)
      setStatusMsg({ type: 'success', text: `삭제 완료: ${file.filename}` })
      if (previewFile === file.filename) setPreview(null)
      loadAll()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `삭제 실패: ${e.message}` })
    }
  }

  function onDragOver(e) { e.preventDefault(); setDragOver(true) }
  function onDragLeave() { setDragOver(false) }
  function onDrop(e) {
    e.preventDefault(); setDragOver(false)
    const f = Array.from(e.dataTransfer.files)
    if (f.length > 0) handleUpload(f[0])
  }

  const typeLabel = (t) => ({
    tech_definition: { text: '기술정의', cls: 'badge-info' },
    patent_dataset:  { text: '특허데이터', cls: 'badge-accent' },
    txt_file:        { text: 'TXT',  cls: 'badge-success' },
    yaml_config:     { text: 'YAML', cls: 'badge-warning' },
  }[t] || { text: '기타', cls: '' })

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(1)} MB`
  }

  return (
    <div>
      <div className="page-header">
        <h2>데이터 소스 관리</h2>
        <p>특허 데이터셋과 기술 정의 파일을 업로드, 변환, 관리합니다.</p>
      </div>

      {statusMsg && <div className={`alert alert-${statusMsg.type}`}>{statusMsg.text}</div>}

      {/* ★ Existing Data Check — shown first */}
      <div className="card" style={{ borderLeft: `3px solid ${dataStatus?.has_data ? 'var(--success)' : 'var(--warning)'}` }}>
        <div className="card-header"><h3>현재 데이터 상태</h3></div>
        {dataStatus?.has_data ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ color: 'var(--success)', fontWeight: 700, fontSize: '1.1rem' }}>✓ 변환된 데이터 확인됨</span>
              <span className="badge badge-success">{dataStatus.document_count.toLocaleString()}개 문서</span>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 8 }}>
              경로: {dataStatus.internal_txt_path}
            </p>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: 4 }}>
              이전에 변환한 데이터가 이미 존재합니다. 동일한 데이터를 다시 변환할 필요 없이 바로 분류 실행에 사용할 수 있습니다.
            </p>
          </div>
        ) : (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ color: 'var(--warning)', fontWeight: 700 }}>변환된 데이터 없음</span>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: 4 }}>
              아래에서 특허 데이터 파일을 업로드한 후 "변환" 버튼을 눌러 internal.txt를 생성하세요.
            </p>
          </div>
        )}
      </div>

      {/* Upload Zone */}
      <div className="card" style={{ marginTop: 16 }}>
        <div
          className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="upload-icon">{uploading ? '...' : '+'}</div>
          <h4>{uploading ? '업로드 중...' : '파일을 드래그하거나 클릭하여 업로드'}</h4>
          <p>지원: Excel (.xlsx), TXT, YAML, CSV, JSON</p>
          <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.txt,.yaml,.yml,.csv,.json,.jsonl"
            onChange={e => { if (e.target.files[0]) handleUpload(e.target.files[0]) }} style={{ display: 'none' }} />
        </div>
      </div>

      {/* Uploaded Files */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <h3>업로드된 파일 ({files.length})</h3>
          <button className="btn btn-secondary btn-sm" onClick={loadAll}>새로고침</button>
        </div>
        {files.length === 0 ? (
          <div className="empty-state" style={{ padding: '28px 20px' }}><h4>업로드된 파일이 없습니다</h4></div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>파일명</th><th>유형</th><th>크기</th><th>작업</th></tr></thead>
              <tbody>
                {files.map(f => {
                  const { text, cls } = typeLabel(f.file_type)
                  const isConverting = converting === f.filename
                  return (
                    <tr key={f.filename}>
                      <td style={{ fontWeight: 500 }}>{f.filename}</td>
                      <td><span className={`badge ${cls}`}>{text}</span></td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{formatSize(f.size_bytes)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => handlePreview(f)}>미리보기</button>
                          {(f.file_type === 'patent_dataset' || f.file_type === 'tech_definition') && (
                            <button className="btn btn-primary btn-sm" onClick={() => handleConvert(f)}
                              disabled={isConverting}>
                              {isConverting ? '변환중...' : '변환'}
                            </button>
                          )}
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(f)}>삭제</button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Converted Files */}
      {converted.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <h3>변환된 파일 ({converted.length})</h3>
          </div>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 12 }}>
            이전에 변환된 파일들. 실행 시 자동으로 사용됩니다.
          </p>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>파일명</th><th>크기</th><th>작업</th></tr></thead>
              <tbody>
                {converted.map(f => (
                  <tr key={f.filename}>
                    <td style={{ fontWeight: 500 }}>{f.filename}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{formatSize(f.size_bytes)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => handlePreview(f)}>미리보기</button>
                        <button className="btn btn-danger btn-sm" onClick={() => handleDelete(f)}>삭제</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Conversion Progress */}
      {converting && (
        <div className="card" style={{ marginTop: 16, borderLeft: '3px solid var(--accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div className="spinner"></div>
            <div>
              <p style={{ fontWeight: 600 }}>변환 진행 중: {converting}</p>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>파일 크기에 따라 수 분이 소요될 수 있습니다.</p>
            </div>
          </div>
        </div>
      )}

      {/* Preview */}
      {preview && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <h3>미리보기: {previewFile}</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="badge badge-info">총 {preview.total_rows}행</span>
              <button className="btn btn-secondary btn-sm" onClick={() => setPreview(null)}>닫기</button>
            </div>
          </div>
          {preview.columns && preview.columns.length > 0 && (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr>{preview.columns.map(col => <th key={col}>{col}</th>)}</tr></thead>
                <tbody>
                  {preview.rows?.map((row, i) => (
                    <tr key={i}>{preview.columns.map(col => <td key={col}>{String(row[col] ?? '')}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
