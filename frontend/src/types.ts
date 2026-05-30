export type ApiEnvelope<T> = {
  code: number
  message: string
  data: T
  trace_id: string
}

export type UserContext = {
  user_id: string
  roles: string[]
  departments: string[]
  is_authenticated: boolean
  is_trusted_identity?: boolean
  is_session_identity?: boolean
  is_external_identity?: boolean
}

export type AuthSessionResponse = {
  access_token: string
  token_type: string
  expires_in: number
  user_context: UserContext
  redirect_after_login?: string | null
}

export type LogoutResponse = {
  user_id: string
  revoked: boolean
}

export type CurrentUserResponse = {
  user_uuid: string
  user_id: string
  display_name: string
  email: string | null
  employee_no: string | null
  status: string
  external_source: string | null
  external_id: string | null
  extra_meta: Record<string, unknown>
  user_context: UserContext
}

export type PaginatedResponse<T> = {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type DocumentItem = {
  doc_uuid: string
  title: string
  source_type: string
  source_module: string
  version: string
  parse_status: string
  index_status: string
  access_level: string
  owner_dept: string | null
  created_at: string
  updated_at: string
  file_ext: string
  file_exists: boolean
}

export type DocumentDetail = DocumentItem & {
  file_name: string
  file_ext: string
  file_size: number | null
  file_path: string | null
  file_exists: boolean
  tags: string[]
  extra_meta: Record<string, unknown>
  chunk_count: number
}

export type DocumentUpdatePayload = {
  title?: string
  source_type?: string
  source_module?: string
  version?: string
  access_level?: string
  owner_dept?: string
  tags?: string[]
  extra_meta?: Record<string, unknown>
}

export type JobItem = {
  job_uuid: string
  doc_uuid: string
  job_type: string
  status: string
  current_step: string
  retry_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export type HealthData = {
  app: string
  postgres: string
  redis: string
  zilliz: string
  embedding: string
  llm_provider: string
  provider_fallbacks_enabled?: boolean
  ingestion_mode?: string
  probes?: Record<string, string>
}

export type ConfigData = {
  app_env: string
  app_port: number
  provider_timeout_seconds: number
  provider_retry_count: number
  health_probe_external_services: boolean
  allow_provider_fallbacks: boolean
  ingestion_mode: string
  enable_folder_source?: boolean
  folder_source_allowed_roots?: string[]
  vector_store_provider: string
  zilliz_collection: string
  embedding_model: string
  embedding_vector_size: number
  llm_provider: string
  llm_model: string
  dify_base_url: string
}

export type SearchHit = {
  doc_uuid: string
  chunk_uuid: string
  title: string
  source_module: string
  page_no: number | null
  sheet_name: string | null
  section_title: string | null
  snippet: string
  version: string
  updated_at: string
  score: number
  vector_score: number | null
  text_score: number | null
  image_url?: string | null
}

export type DebugSearchData = {
  query: string
  rewritten_query: string
  filters_applied: Record<string, unknown>
  hits: SearchHit[]
  latency_ms: number
  raw_filters: Record<string, unknown>
  user_context: Record<string, unknown>
  ranking_debug: Array<{
    chunk_uuid: string
    doc_uuid: string
    score: number
    vector_score: number | null
    text_score: number | null
    section_title: string | null
  }>
}

export type BatchOperationResult = {
  total: number
  success_count: number
  failed_count: number
  items: Array<{
    doc_uuid: string
    success: boolean
    message: string
    job_uuid?: string | null
    chunk_count?: number | null
  }>
}

export type SystemConfigItem = {
  id: number
  config_key: string
  config_value: Record<string, unknown>
  description: string | null
  created_at: string
  updated_at: string
}

export type SystemConfigPayload = {
  config_key?: string
  config_value?: Record<string, unknown>
  description?: string
}

export type FieldKey = 'source_module' | 'source_type'

export type FieldOption = {
  value: string
  label: string
  enabled: boolean
  sort_order: number
}

export type FieldOptionsConfig = {
  fields: Record<FieldKey, FieldOption[]>
}

export type UploadResult = {
  doc_uuid: string
  job_uuid: string
  status: string
  chunk_count: number | null
  execution_mode?: string
}

export type FolderSyncItem = {
  file_name: string
  relative_path: string | null
  success: boolean
  message: string
  doc_uuid?: string | null
  job_uuid?: string | null
  status?: string | null
  chunk_count?: number | null
}

export type FolderSyncResult = {
  run_uuid: string
  source_name: string
  folder_path: string
  recursive: boolean
  max_files: number
  total: number
  success_count: number
  failed_count: number
  skipped_count: number
  skipped: Array<Record<string, unknown>>
  items: FolderSyncItem[]
}

export type FolderSyncPayload = {
  folder_path: string
  recursive: boolean
  max_files: number
  source_type: string
  source_module: string
  version: string
  access_level: string
  owner_dept?: string | null
  tags: string[]
  extra_meta: Record<string, unknown>
}

export type SourceSyncRunItem = {
  run_uuid: string
  source_type: string
  source_name: string
  source_module: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export type SourceSyncRunDetail = SourceSyncRunItem & {
  folder_path: string | null
  recursive: boolean
  max_files: number
  request_json: Record<string, unknown>
  summary_json: Record<string, unknown>
  items: Array<{
    file_name: string
    relative_path: string | null
    status: string
    message: string | null
    doc_uuid: string | null
    job_uuid: string | null
    chunk_count: number | null
    metadata_json: Record<string, unknown>
  }>
}

// Chunking
export type ChunkingStrategyInfo = {
  name: string
  label?: string
  description?: string
  params_schema: {
    type: string
    properties: Record<string, {
      type: string
      default: number
      minimum?: number
      maximum?: number
    }>
  }
}

export type ChunkingStrategiesResponse = {
  strategies: ChunkingStrategyInfo[]
}

export type ChunkPreviewResult = {
  strategy: string
  total_chunks: number
  chunks: Array<{
    chunk_index: number
    chunk_text: string
    chunk_type?: string | null
    section_title?: string | null
    page_no?: number | null
    sheet_name?: string | null
    row_start?: number | null
    row_end?: number | null
    char_count: number
    token_count: number
    chunk_level?: string | null
    parent_chunk_uuid?: string | null
    chunk_group_uuid?: string | null
    context_text?: string | null
    metadata_json: Record<string, unknown>
  }>
}

export type ChunkingPreviewSource = 'text' | 'document'

// Retrieval v2
export type RetrievalStrategyInfo = {
  name: string
  label: string
  description: string
  requires: string[]
}

export type RetrievalStrategiesResponse = {
  strategies: RetrievalStrategyInfo[]
  rerank: {
    enabled: boolean
    model: string | null
    api_base: string | null
  }
}

export type SearchHitV2 = SearchHit & {
  sparse_score?: number | null
  rerank_score?: number | null
  pre_rerank_score?: number | null
}

export type DebugSearchDataV2 = DebugSearchData & {
  retrieval_strategy?: string
  dense_hits?: Array<{ chunk_uuid: string; doc_uuid: string; score: number }>
  sparse_hits?: Array<{ chunk_uuid: string; doc_uuid: string; score: number }>
  fusion_alpha?: number
  rerank_enabled?: boolean
  rerank_model?: string | null
  rerank_latency_ms?: number
  hits: SearchHitV2[]
}

// Evaluation
export type EvaluationDataset = {
  dataset_uuid: string
  name: string
  description: string
  query_count?: number
  created_at: string
}

export type EvaluationQuery = {
  query_uuid: string
  query_text: string
  expected_doc_titles: string[]
  expected_terms: string[]
  notes: string | null
}

export type EvaluationDatasetDetail = EvaluationDataset & {
  queries: EvaluationQuery[]
}

export type EvaluationRun = {
  run_uuid: string
  dataset_uuid: string
  dataset_name?: string | null
  chunking_strategy: string
  chunking_params: Record<string, unknown>
  retrieval_strategy: string
  retrieval_params: Record<string, unknown>
  status: string
  started_at: string | null
  finished_at: string | null
  summary?: {
    total_queries: number
    hit_at_1_rate: number
    hit_at_3_rate: number
    hit_at_5_rate: number
    mean_mrr: number
    mean_term_hit_rate: number
    mean_latency_ms: number
  }
}

export type EvaluationResult = {
  query_uuid: string
  query_text: string
  hit_at_1: boolean
  hit_at_3: boolean
  hit_at_5: boolean
  mrr: number
  expected_term_hit_rate: number
  avg_latency_ms: number
}

export type EvaluationRunDetail = EvaluationRun & {
  results: EvaluationResult[]
}

export type UserItem = {
  user_id: string
  display_name: string
  status: string
  external_source?: string
  external_id?: string
  department_codes?: string[]
}

export type DepartmentItem = {
  dept_code: string
  dept_name: string
  status: string
}

export type DocumentListOption = {
  doc_uuid: string
  title: string
  source_module: string
}
