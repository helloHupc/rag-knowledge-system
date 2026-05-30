import type {
  ApiEnvelope,
  BatchOperationResult,
  ChunkingStrategiesResponse,
  ChunkPreviewResult,
  ConfigData,
  CurrentUserResponse,
  DebugSearchDataV2,
  DocumentDetail,
  DocumentItem,
  DocumentUpdatePayload,
  DepartmentItem,
  EvaluationDataset,
  EvaluationDatasetDetail,
  EvaluationRun,
  EvaluationRunDetail,
  FolderSyncPayload,
  FolderSyncResult,
  HealthData,
  JobItem,
  LogoutResponse,
  PaginatedResponse,
  RetrievalStrategiesResponse,
  SourceSyncRunDetail,
  SourceSyncRunItem,
  SystemConfigItem,
  SystemConfigPayload,
  UploadResult,
  UserItem,
} from './types'

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:18080/api/v1'

export { API_BASE }
const AUTH_TOKEN_STORAGE_KEY = 'oa_rag_auth_token'

function getStoredAuthToken() {
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
}

export function saveAuthToken(token: string) {
  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
}

export function clearAuthToken() {
  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

export function hasAuthToken() {
  return Boolean(getStoredAuthToken())
}

function withAuthHeader(init?: RequestInit): RequestInit | undefined {
  const token = getStoredAuthToken()
  if (!token) return init
  const headers = new Headers(init?.headers)
  if (!headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return { ...init, headers }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, withAuthHeader(init))
  } catch (error) {
    throw new Error(
      `请求后端失败，请确认前后端服务已启动且允许跨域访问。${error instanceof Error ? error.message : ''}`,
      { cause: error },
    )
  }

  const rawText = await response.text()
  let payload: ApiEnvelope<T> | null = null

  if (rawText) {
    try {
      payload = JSON.parse(rawText) as ApiEnvelope<T>
    } catch {
      throw new Error(`接口返回了无法解析的响应，HTTP ${response.status}`)
    }
  }

  if (!payload) {
    throw new Error(`接口返回为空，HTTP ${response.status}`)
  }

  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || `接口请求失败，HTTP ${response.status}`)
  }

  return payload.data
}

export function getApiBaseUrl() {
  return API_BASE
}

export function fetchCurrentUser() {
  return requestJson<CurrentUserResponse>('/auth/me')
}

export function logoutCurrentSession() {
  return requestJson<LogoutResponse>('/auth/logout', { method: 'POST' })
}

export function getDocumentDownloadUrl(docUuid: string) {
  return `${API_BASE}/documents/${docUuid}/download`
}

export function downloadDocumentFile(docUuid: string) {
  window.open(getDocumentDownloadUrl(docUuid), '_blank', 'noopener,noreferrer')
}

export function fetchDocuments(params?: {
  page?: number
  pageSize?: number
  keyword?: string
  sourceModule?: string
  sourceType?: string
  parseStatus?: string
  indexStatus?: string
}) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 50))
  if (params?.keyword) {
    searchParams.set('keyword', params.keyword)
  }
  if (params?.sourceModule) {
    searchParams.set('source_module', params.sourceModule)
  }
  if (params?.sourceType) {
    searchParams.set('source_type', params.sourceType)
  }
  if (params?.parseStatus) {
    searchParams.set('parse_status', params.parseStatus)
  }
  if (params?.indexStatus) {
    searchParams.set('index_status', params.indexStatus)
  }
  return requestJson<PaginatedResponse<DocumentItem>>(`/documents?${searchParams.toString()}`)
}

export function fetchDocumentDetail(docUuid: string) {
  return requestJson<DocumentDetail>(`/documents/${docUuid}`)
}

export function updateDocument(docUuid: string, payload: DocumentUpdatePayload) {
  return requestJson<DocumentDetail>(`/documents/${docUuid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchJobs(params?: { page?: number; pageSize?: number; status?: string }) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 50))
  if (params?.status) {
    searchParams.set('status', params.status)
  }
  return requestJson<PaginatedResponse<JobItem>>(`/jobs?${searchParams.toString()}`)
}

export function fetchHealth() {
  return requestJson<HealthData>('/health')
}

export function fetchConfigs() {
  return requestJson<ConfigData>('/configs')
}

export function fetchSystemConfigs(params?: { page?: number; pageSize?: number; keyword?: string }) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 50))
  if (params?.keyword) {
    searchParams.set('keyword', params.keyword)
  }
  return requestJson<PaginatedResponse<SystemConfigItem>>(`/admin/system-configs?${searchParams.toString()}`)
}

export function createSystemConfig(payload: Required<Pick<SystemConfigItem, 'config_key'>> & {
  config_value: Record<string, unknown>
  description?: string | null
}) {
  return requestJson<SystemConfigItem>('/admin/system-configs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateSystemConfig(configId: number, payload: SystemConfigPayload) {
  return requestJson<SystemConfigItem>(`/admin/system-configs/${configId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function uploadDocument(formData: FormData) {
  return requestJson<UploadResult>('/documents/upload', {
    method: 'POST',
    body: formData,
  })
}

export function batchDelete(docUuids: string[]) {
  return requestJson<BatchOperationResult>('/documents/batch/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_uuids: docUuids }),
  })
}

export function batchReindex(docUuids: string[]) {
  return requestJson<BatchOperationResult>('/documents/batch/reindex', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_uuids: docUuids }),
  })
}

export function syncFolderSource(payload: FolderSyncPayload) {
  return requestJson<FolderSyncResult>('/sources/folder/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchSourceSyncRuns(params?: {
  page?: number
  pageSize?: number
  sourceType?: string
  status?: string
}) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 20))
  if (params?.sourceType) {
    searchParams.set('source_type', params.sourceType)
  }
  if (params?.status) {
    searchParams.set('status', params.status)
  }
  return requestJson<PaginatedResponse<SourceSyncRunItem>>(`/sources/sync-runs?${searchParams.toString()}`)
}

export function fetchSourceSyncRunDetail(runUuid: string) {
  return requestJson<SourceSyncRunDetail>(`/sources/sync-runs/${runUuid}`)
}

export function debugSearch(payload: {
  query: string
  top_k: number
  strategy?: string
  strategy_params?: Record<string, unknown>
  filters?: { source_module?: string[] }
  user_context?: {
    user_id: string
  }
}) {
  return requestJson<DebugSearchDataV2>('/retrieval/debug-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Chunking
export function fetchChunkingStrategies() {
  return requestJson<ChunkingStrategiesResponse>('/chunking/strategies')
}

export function previewChunking(payload: {
  strategy: string
  text: string
  options: Record<string, number>
}) {
  return requestJson<ChunkPreviewResult>('/chunking/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function previewDocumentChunking(docUuid: string, payload: {
  strategy: string
  options: Record<string, number>
}) {
  return requestJson<ChunkPreviewResult>(`/chunking/documents/${docUuid}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Retrieval
export function fetchRetrievalStrategies() {
  return requestJson<RetrievalStrategiesResponse>('/retrieval/strategies')
}

export function searchV2(payload: {
  query: string
  top_k?: number
  strategy?: string
  strategy_params?: Record<string, unknown>
  filters?: Record<string, unknown>
  user_context?: Record<string, unknown>
}) {
  return requestJson<{ hits: unknown[]; latency_ms: number }>('/retrieval/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// Evaluation
export function createEvaluationDataset(payload: {
  name: string
  description?: string
  queries: Array<{
    query_text: string
    expected_doc_titles: string[]
    expected_terms: string[]
    notes?: string
  }>
}) {
  return requestJson<EvaluationDataset>('/evaluation/datasets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchEvaluationDatasets() {
  return requestJson<{ datasets: EvaluationDataset[] }>('/evaluation/datasets').then(d => d.datasets)
}

export function fetchEvaluationDatasetDetail(datasetUuid: string) {
  return requestJson<EvaluationDatasetDetail>(`/evaluation/datasets/${datasetUuid}`)
}

export function deleteEvaluationDataset(datasetUuid: string) {
  return requestJson<{ deleted: boolean }>(`/evaluation/datasets/${datasetUuid}`, {
    method: 'DELETE',
  })
}

export function createEvaluationRun(payload: {
  dataset_uuid: string
  chunking_strategy: string
  chunking_params?: Record<string, unknown>
  retrieval_strategy: string
  retrieval_params?: Record<string, unknown>
  doc_uuids?: string[]
  source_module?: string
}) {
  return requestJson<EvaluationRun>('/evaluation/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchEvaluationRuns(params?: { dataset_uuid?: string }) {
  const searchParams = new URLSearchParams()
  if (params?.dataset_uuid) searchParams.set('dataset_uuid', params.dataset_uuid)
  const qs = searchParams.toString()
  return requestJson<{ runs: EvaluationRun[] }>(`/evaluation/runs${qs ? `?${qs}` : ''}`).then(d => d.runs)
}

export function fetchEvaluationRunDetail(runUuid: string) {
  return requestJson<EvaluationRunDetail>(`/evaluation/runs/${runUuid}`)
}

export function deleteEvaluationRun(runUuid: string) {
  return requestJson<{ deleted: boolean }>(`/evaluation/runs/${runUuid}`, {
    method: 'DELETE',
  })
}

export function fetchUsers(params?: { page?: number; pageSize?: number; status?: string }) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 100))
  if (params?.status) searchParams.set('status', params.status)
  return requestJson<PaginatedResponse<UserItem>>(`/admin/users?${searchParams.toString()}`)
}

export function fetchDepartments(params?: { page?: number; pageSize?: number }) {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.pageSize ?? 100))
  return requestJson<PaginatedResponse<DepartmentItem>>(`/admin/departments?${searchParams.toString()}`)
}

export function updateUserStatus(userId: string, status: string) {
  return requestJson<UserItem>(`/admin/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}
