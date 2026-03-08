/**
 * API client — wrapper around fetch for backend communication.
 */
const BASE_URL = '/api';

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };

  // Don't set Content-Type for FormData
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
  // Files
  uploadFile: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/files/upload', { method: 'POST', body: form });
  },
  listFiles: () => request('/files/list'),
  scanFiles: (folder) => request(`/files/scan?folder=${encodeURIComponent(folder || '')}`),
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
  getDimensions: () => request('/taxonomy/dimensions'),
  updateDimensions: (config) => request('/taxonomy/dimensions', { method: 'PUT', body: JSON.stringify(config) }),
  deleteDimension: (name) => request(`/taxonomy/dimensions/${name}`, { method: 'DELETE' }),
  generateYaml: (body) => request('/taxonomy/generate-yaml', { method: 'POST', body: JSON.stringify(body) }),
  generateTaxoTxt: (body) => request('/taxonomy/generate-taxo-txt', { method: 'POST', body: JSON.stringify(body) }),
  getYaml: () => request('/taxonomy/yaml'),

  // Classification
  runClassification: (body) => request('/classify/run', { method: 'POST', body: JSON.stringify(body) }),
  getProgress: (runId) => request(`/classify/progress/${runId}`),
  cancelRun: (runId) => request(`/classify/cancel/${runId}`, { method: 'POST' }),

  // Results
  listRuns: (folder) => request(`/results/list?dataset_folder=${encodeURIComponent(folder || '')}`),
  getRunDetail: (runId) => request(`/results/${runId}`),
  getTaxonomy: (runId, dim) => request(`/results/${runId}/taxonomy?dimension=${encodeURIComponent(dim || '')}`),
  downloadResults: (runId) => `${BASE_URL}/results/${runId}/download`,

  // Health
  health: () => request('/health').catch(() => null),
};

/**
 * SSE hook helper — returns an EventSource for progress streaming.
 */
export function createProgressStream(runId) {
  return new EventSource(`${BASE_URL}/classify/progress/${runId}/stream`);
}
