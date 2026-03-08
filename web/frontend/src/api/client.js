/**
 * API client with user session management.
 * X-User-Id header sent with every request for multi-user support.
 */
const BASE_URL = '/api';

function getUserId() {
  let uid = localStorage.getItem('taxoadapt_user_id');
  if (!uid) {
    uid = 'user_' + Math.random().toString(36).substr(2, 8);
    localStorage.setItem('taxoadapt_user_id', uid);
  }
  return uid;
}

function setUserId(id) {
  localStorage.setItem('taxoadapt_user_id', id);
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = { 'Content-Type': 'application/json', 'X-User-Id': getUserId(), ...options.headers };
  const config = { headers, ...options };
  if (options.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  const res = await fetch(url, config);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // User
  getUserId,
  setUserId,

  // Files
  uploadFile: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/files/upload', { method: 'POST', body: form });
  },
  listFiles: () => request('/files/list'),
  listConverted: () => request('/files/converted'),
  previewFile: (filename, maxRows = 20) => request(`/files/${filename}/preview?max_rows=${maxRows}`),
  deleteFile: (filename) => request(`/files/${filename}`, { method: 'DELETE' }),

  // Preprocessing
  detectColumns: (fileId) => request(`/preprocess/columns?file_id=${fileId}`, { method: 'POST' }),
  convertToTxt: (body) => request('/preprocess/convert', { method: 'POST', body: JSON.stringify(body) }),
  preprocessStatus: (folder) => request(`/preprocess/status?dataset_folder=${encodeURIComponent(folder || 'web_custom_data')}`),

  // Taxonomy
  uploadYaml: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/taxonomy/upload-yaml', { method: 'POST', body: form });
  },
  applyConfig: (folder) => request(`/taxonomy/apply?dataset_folder=${encodeURIComponent(folder || 'web_custom_data')}`, { method: 'POST' }),
  configStatus: (folder) => request(`/taxonomy/status?dataset_folder=${encodeURIComponent(folder || 'web_custom_data')}`),
  getDimensions: () => request('/taxonomy/dimensions'),
  updateDimensions: (config) => request('/taxonomy/dimensions', { method: 'PUT', body: JSON.stringify(config) }),
  deleteDimension: (name) => request(`/taxonomy/dimensions/${name}`, { method: 'DELETE' }),
  generateYaml: (body) => request('/taxonomy/generate-yaml', { method: 'POST', body: JSON.stringify(body) }),

  // Classification
  runClassification: (body) => request('/classify/run', { method: 'POST', body: JSON.stringify(body) }),
  getProgress: (runId) => request(`/classify/progress/${runId}`),
  cancelRun: (runId) => request(`/classify/cancel/${runId}`, { method: 'POST' }),
  queueStatus: () => request('/classify/queue'),
  estimateTime: (params) => {
    const q = new URLSearchParams(params).toString();
    return request(`/classify/estimate?${q}`);
  },

  // Results
  listRuns: (folder) => request(`/results/list?dataset_folder=${encodeURIComponent(folder || '')}`),
  getRunDetail: (runId) => request(`/results/${runId}`),
  getRunTable: (runId) => request(`/results/${runId}/table`),
  downloadUrl: (runId, format = 'excel') => `${BASE_URL}/results/${runId}/download?format=${format}&user_id=${getUserId()}`,

  // Health
  health: () => request('/health').catch(() => null),
};

export function createProgressStream(runId) {
  return new EventSource(`${BASE_URL}/classify/progress/${runId}/stream`);
}
