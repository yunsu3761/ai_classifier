import React, { useState, useRef, useEffect } from 'react'
import { api } from '../api/client.js'

export default function DataSourcePage() {
  const [files, setFiles] = useState([])
  const [preview, setPreview] = useState(null)
  const [previewFile, setPreviewFile] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [statusMsg, setStatusMsg] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => { loadFiles() }, [])

  async function loadFiles() {
    try {
      const data = await api.listFiles()
      setFiles(data.files || [])
    } catch (e) {
      setStatusMsg({ type: 'error', text: `파일 목록 로드 실패: ${e.message}` })
    }
  }

  async function handleUpload(fileObj) {
    setUploading(true)
    setStatusMsg(null)
    try {
      const result = await api.uploadFile(fileObj)
      setStatusMsg({ type: 'success', text: `✅ 업로드 완료: ${result.filename} (${result.file_type})` })
      loadFiles()
    } catch (e) {
      setStatusMsg({ type: 'error', text: `❌ 업로드 실패: ${e.message}` })
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
    setStatusMsg(null)
    try {
      const fileId = file.filename.split('_')[0]
      const result = await api.convertToTxt({ file_id: fileId, dataset_folder: 'web_custom_data' })
      if (result.success) {
        setStatusMsg({ type: 'success', text: `✅ 변환 완료: ${result.total_documents}개 문서 → internal.txt` })
      } else {
        setStatusMsg({ type: 'error', text: `❌ 변환 실패: ${result.message}` })
      }
    } catch (e) {
      setStatusMsg({ type: 'error', text: `❌ 변환 오류: ${e.message}` })
    }
  }

  async function handleDelete(file) {
    try {
      await api.deleteFile(file.filename)
      setStatusMsg({ type: 'success', text: `🗑️ 삭제 완료: ${file.filename}` })
      loadFiles()
      if (previewFile === file.filename) setPreview(null)
    } catch (e) {
      setStatusMsg({ type: 'error', text: `삭제 실패: ${e.message}` })
    }
  }

  function onDragOver(e) { e.preventDefault(); setDragOver(true) }
  function onDragLeave() { setDragOver(false) }
  function onDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const droppedFiles = Array.from(e.dataTransfer.files)
    if (droppedFiles.length > 0) handleUpload(droppedFiles[0])
  }
  function onFileSelect(e) {
    const selected = e.target.files[0]
    if (selected) handleUpload(selected)
  }

  const fileTypeLabel = (type) => {
    const labels = {
      tech_definition: { text: '기술정의', cls: 'badge-info' },
      patent_dataset:  { text: '특허데이터', cls: 'badge-accent' },
      txt_file:        { text: 'TXT',       cls: 'badge-success' },
      yaml_config:     { text: 'YAML',      cls: 'badge-warning' },
      unknown:         { text: '알수없음',    cls: '' },
    }
    return labels[type] || labels.unknown
  }

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div>
      <div className="page-header">
        <h2>📂 데이터 소스 관리</h2>
        <p>특허 데이터셋과 기술 정의 파일을 업로드하고 관리합니다.</p>
      </div>

      {statusMsg && (
        <div className={`alert alert-${statusMsg.type}`}>
          {statusMsg.text}
        </div>
      )}

      {/* Upload Zone */}
      <div className="card">
        <div
          className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="upload-icon">📤</div>
          <h4>{uploading ? '업로드 중...' : '파일을 드래그하거나 클릭하여 업로드'}</h4>
          <p>지원 형식: Excel (.xlsx), TXT, YAML, CSV, JSON</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.txt,.yaml,.yml,.csv,.json,.jsonl"
            onChange={onFileSelect}
            style={{ display: 'none' }}
          />
        </div>
      </div>

      {/* File List */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <h3>📋 업로드된 파일 ({files.length})</h3>
          <button className="btn btn-secondary btn-sm" onClick={loadFiles}>🔄 새로고침</button>
        </div>

        {files.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📁</div>
            <h4>업로드된 파일이 없습니다</h4>
            <p>위 영역에 파일을 드래그하여 시작하세요</p>
          </div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>파일명</th>
                  <th>유형</th>
                  <th>크기</th>
                  <th>컬럼수</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {files.map(f => {
                  const { text, cls } = fileTypeLabel(f.file_type)
                  return (
                    <tr key={f.filename}>
                      <td style={{ fontWeight: 500 }}>{f.filename}</td>
                      <td><span className={`badge ${cls}`}>{text}</span></td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{formatSize(f.size_bytes)}</td>
                      <td>{f.detected_columns?.length || '-'}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => handlePreview(f)}>👁️</button>
                          {(f.file_type === 'patent_dataset' || f.file_type === 'tech_definition') && (
                            <button className="btn btn-primary btn-sm" onClick={() => handleConvert(f)}>⚡ 변환</button>
                          )}
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(f)}>🗑️</button>
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

      {/* Preview */}
      {preview && (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">
            <h3>🔍 미리보기: {previewFile}</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className="badge badge-info">총 {preview.total_rows}행</span>
              <button className="btn btn-secondary btn-sm" onClick={() => setPreview(null)}>✕ 닫기</button>
            </div>
          </div>

          {preview.columns.length > 0 && (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {preview.columns.map(col => <th key={col}>{col}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i}>
                      {preview.columns.map(col => <td key={col}>{String(row[col] ?? '')}</td>)}
                    </tr>
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
