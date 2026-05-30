import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  API_BASE,
  batchDelete,
  batchReindex,
  downloadDocumentFile,
  fetchChunkingStrategies,
  fetchConfigs,
  fetchDocumentDetail,
  fetchDocuments,
  fetchHealth,
  fetchJobs,
  updateDocument,
  uploadDocument,
} from '../api'
import { getChunkingStrategyLabel } from '../chunkingStrategyLabels'
import { FormField, SectionHeader } from '../components/shared'
import {
  DEFAULT_FIELD_OPTIONS_CONFIG,
  firstEnabledValue,
  getFieldLabel,
  getFieldOptions,
  loadFieldOptionsSystemConfig,
} from '../fieldOptions'
import { formatDateTime, getHealthTone, getJobTone, getLoadStateLabel, stringifyValue } from '../utils'
import type {
  ChunkingStrategyInfo,
  ConfigData,
  DocumentDetail,
  DocumentItem,
  FieldKey,
  FieldOptionsConfig,
  HealthData,
  JobItem,
} from '../types'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'
type ToastTone = 'info' | 'success' | 'danger'

type ToastState = {
  id: number
  tone: ToastTone
  message: string
}

type DocumentQueryState = {
  keyword: string
  sourceModule: string
  sourceType: string
  parseStatus: string
  indexStatus: string
  page: number
  pageSize: number
}

type JobQueryState = {
  status: string
  page: number
  pageSize: number
}

type UploadFormState = {
  title: string
  source_type: string
  source_module: string
  tags: string[]
  chunkingStrategy: string
}

type DocumentEditFormState = {
  title: string
  source_module: string
  source_type: string
  tags: string[]
  chunkingStrategy: string
}

const DEFAULT_DOCUMENT_QUERY: DocumentQueryState = {
  keyword: '',
  sourceModule: '',
  sourceType: '',
  parseStatus: '',
  indexStatus: '',
  page: 1,
  pageSize: 10,
}

const DEFAULT_JOB_QUERY: JobQueryState = {
  status: '',
  page: 1,
  pageSize: 8,
}

const HEALTH_LABELS: Record<string, string> = {
  app: '应用服务',
  postgres: 'PostgreSQL',
  redis: 'Redis',
  zilliz: 'Zilliz',
  embedding: '向量模型',
  llm_provider: '大模型',
  provider_fallbacks_enabled: '回退开关',
  ingestion_mode: '入库模式',
  probes: '真实探测',
}

const JOB_TYPE_LABELS: Record<string, string> = {
  ingest: '文档入库',
  reindex: '重建索引',
}

const JOB_STATUS_LABELS: Record<string, string> = {
  pending: '排队中',
  running: '处理中',
  success: '已完成',
  failed: '失败',
}

const JOB_STEP_LABELS: Record<string, string> = {
  queued: '等待处理',
  created: '已创建',
  parsing: '解析中',
  chunking: '切分中',
  vector_upsert: '写入索引中',
  indexed: '索引完成',
  chunking_completed: '切分完成',
  failed: '处理失败',
}

const DEFAULT_UPLOAD_FIELDS: UploadFormState = {
  title: '',
  source_type: 'rule_doc',
  source_module: 'oa',
  tags: [],
  chunkingStrategy: 'fixed',
}

const EMPTY_DOCUMENT_EDIT_FORM: DocumentEditFormState = {
  title: '',
  source_module: '',
  source_type: 'rule_doc',
  tags: [],
  chunkingStrategy: 'fixed',
}

function getJobTypeLabel(value: string) {
  return JOB_TYPE_LABELS[value] ?? value
}

function getJobStatusLabel(value: string) {
  return JOB_STATUS_LABELS[value] ?? value
}

function getJobStepLabel(value: string) {
  return JOB_STEP_LABELS[value] ?? value
}

function normalizeTags(tags: string[]) {
  return Array.from(new Set(tags.map((item) => item.trim()).filter(Boolean)))
}

function isImageFile(file: File | null): boolean {
  if (!file) return false
  return file.type.startsWith('image/')
}

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp'])

function isImageExtension(ext: string): boolean {
  return IMAGE_EXTENSIONS.has(ext.toLowerCase())
}

function buildExtraMeta(chunkingStrategy: string, previousExtraMeta?: Record<string, unknown>) {
  const nextMeta = { ...(previousExtraMeta ?? {}) }
  nextMeta.chunking_strategy = chunkingStrategy || 'fixed'
  return nextMeta
}

function ensureEnabledFieldValue(config: FieldOptionsConfig, fieldKey: FieldKey, value: string, fallback: string) {
  if (getFieldOptions(config, fieldKey).some((option) => option.value === value)) return value
  return firstEnabledValue(config, fieldKey, fallback)
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [documentsTotal, setDocumentsTotal] = useState(0)
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [jobsTotal, setJobsTotal] = useState(0)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [configs, setConfigs] = useState<ConfigData | null>(null)
  const [fieldOptions, setFieldOptions] = useState<FieldOptionsConfig>(DEFAULT_FIELD_OPTIONS_CONFIG)
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null)
  const [coreState, setCoreState] = useState<LoadState>('idle')
  const [healthState, setHealthState] = useState<LoadState>('idle')
  const [, setStatusMessage] = useState('控制台已就绪')
  const [toast, setToast] = useState<ToastState | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)
  const [savingDoc, setSavingDoc] = useState(false)
  const [uploadInputKey, setUploadInputKey] = useState(0)
  const [healthCollapsed, setHealthCollapsed] = useState(true)
  const [chunkingStrategies, setChunkingStrategies] = useState<ChunkingStrategyInfo[]>([])
  const [tagInputValue, setTagInputValue] = useState('')
  const [editTagInputValue, setEditTagInputValue] = useState('')
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [openMoreMenuDocUuid, setOpenMoreMenuDocUuid] = useState<string | null>(null)

  const [documentFilters, setDocumentFilters] = useState(DEFAULT_DOCUMENT_QUERY)
  const [documentQuery, setDocumentQuery] = useState(DEFAULT_DOCUMENT_QUERY)
  const [jobFilters, setJobFilters] = useState(DEFAULT_JOB_QUERY)
  const [jobQuery, setJobQuery] = useState(DEFAULT_JOB_QUERY)

  const [uploadFields, setUploadFields] = useState<UploadFormState>(DEFAULT_UPLOAD_FIELDS)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const [imagePreviewOpen, setImagePreviewOpen] = useState(false)

  const [documentEditForm, setDocumentEditForm] = useState<DocumentEditFormState>(EMPTY_DOCUMENT_EDIT_FORM)

  const selectedSummary = useMemo(() => {
    if (selectedIds.length === 0) return '未选择文档'
    return `已选择 ${selectedIds.length} 个文档`
  }, [selectedIds])

  const allVisibleSelected = useMemo(() => {
    if (documents.length === 0) return false
    return documents.every((document) => selectedIds.includes(document.doc_uuid))
  }, [documents, selectedIds])

  const documentPageCount = Math.max(1, Math.ceil(documentsTotal / documentQuery.pageSize))
  const jobPageCount = Math.max(1, Math.ceil(jobsTotal / jobQuery.pageSize))
  const isAsyncMode = configs?.ingestion_mode === 'async'
  const sourceModuleOptions = useMemo(() => getFieldOptions(fieldOptions, 'source_module'), [fieldOptions])
  const sourceTypeOptions = useMemo(() => getFieldOptions(fieldOptions, 'source_type'), [fieldOptions])



  const tagSuggestions = useMemo(() => {
    const values = new Set<string>()
    documents.forEach((doc) => {
      if ('tags' in doc && Array.isArray((doc as DocumentDetail).tags)) {
        ;((doc as DocumentDetail).tags ?? []).forEach((tag) => values.add(String(tag).trim()))
      }
    })
    if (selectedDoc?.tags) selectedDoc.tags.forEach((tag) => values.add(String(tag).trim()))
    return Array.from(values).filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [documents, selectedDoc])

  const uploadTagSuggestions = useMemo(() => {
    const keyword = tagInputValue.trim().toLowerCase()
    return tagSuggestions.filter((tag) => !uploadFields.tags.includes(tag) && (!keyword || tag.toLowerCase().includes(keyword))).slice(0, 8)
  }, [tagInputValue, tagSuggestions, uploadFields.tags])

  const editTagSuggestions = useMemo(() => {
    const keyword = editTagInputValue.trim().toLowerCase()
    return tagSuggestions.filter((tag) => !documentEditForm.tags.includes(tag) && (!keyword || tag.toLowerCase().includes(keyword))).slice(0, 8)
  }, [documentEditForm.tags, editTagInputValue, tagSuggestions])

  useEffect(() => {
    if (!toast) return
    const timeoutId = window.setTimeout(() => setToast(null), 4000)
    return () => window.clearTimeout(timeoutId)
  }, [toast])

  const showToast = useCallback((message: string, tone: ToastTone) => {
    setToast({ id: Date.now(), tone, message })
  }, [])

  const showError = useCallback((message: string) => {
    setStatusMessage(message)
    showToast(message, 'danger')
  }, [showToast])

  const showSuccess = useCallback((message: string) => {
    setStatusMessage(message)
    showToast(message, 'success')
  }, [showToast])

  const refreshCoreData = useCallback(async () => {
    setCoreState('loading')
    const [documentsData, jobsData] = await Promise.all([
      fetchDocuments({
        page: documentQuery.page, pageSize: documentQuery.pageSize,
        keyword: documentQuery.keyword, sourceModule: documentQuery.sourceModule,
        sourceType: documentQuery.sourceType, parseStatus: documentQuery.parseStatus,
        indexStatus: documentQuery.indexStatus,
      }),
      fetchJobs({ page: jobQuery.page, pageSize: jobQuery.pageSize, status: jobQuery.status }),
    ])
    setDocuments(documentsData.items)
    setDocumentsTotal(documentsData.total)
    setJobs(jobsData.items)
    setJobsTotal(jobsData.total)
    setCoreState('ready')
    setSelectedIds((current) =>
      current.filter((docUuid) => documentsData.items.some((item) => item.doc_uuid === docUuid)),
    )
    if (selectedDocId && !documentsData.items.some((item) => item.doc_uuid === selectedDocId)) {
      setSelectedDocId(null)
      setSelectedDoc(null)
    }
    return { documentCount: documentsData.total, jobCount: jobsData.total }
  }, [documentQuery, jobQuery, selectedDocId])

  async function refreshHealthData() {
    setHealthState('loading')
    const result = await fetchHealth()
    setHealth(result)
    setHealthState('ready')
  }

  async function refreshConfigData() {
    const configsData = await fetchConfigs()
    setConfigs(configsData)
  }

  async function refreshFieldOptionsData() {
    const data = await loadFieldOptionsSystemConfig()
    setFieldOptions(data.config)
    setUploadFields((current) => ({
      ...current,
      source_module: ensureEnabledFieldValue(data.config, 'source_module', current.source_module, 'oa'),
      source_type: ensureEnabledFieldValue(data.config, 'source_type', current.source_type, 'rule_doc'),
    }))
  }

  async function refreshChunkingStrategies() {
    const data = await fetchChunkingStrategies()
    setChunkingStrategies(data.strategies)
    setUploadFields((current) => {
      if (data.strategies.some((item) => item.name === current.chunkingStrategy)) return current
      return { ...current, chunkingStrategy: data.strategies[0]?.name ?? 'fixed' }
    })
    setDocumentEditForm((current) => {
      if (data.strategies.some((item) => item.name === current.chunkingStrategy)) return current
      return { ...current, chunkingStrategy: data.strategies[0]?.name ?? 'fixed' }
    })
  }

  async function refreshDashboard() {
    const results = await Promise.allSettled([refreshCoreData(), refreshHealthData(), refreshConfigData(), refreshChunkingStrategies(), refreshFieldOptionsData()])
    const failures = results.filter((result) => result.status === 'rejected')
    if (failures.length > 0) {
      if (results[0]?.status === 'rejected') setCoreState('error')
      if (results[1]?.status === 'rejected') setHealthState('error')
      const reason = failures[0]?.reason
      showError(reason instanceof Error ? reason.message : '部分数据加载失败')
    } else {
      const coreResult = results[0]
      if (coreResult.status === 'fulfilled') {
        setStatusMessage(`当前已加载 ${coreResult.value.documentCount} 个文档，${coreResult.value.jobCount} 个任务`)
      }
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void (async () => {
        const results = await Promise.allSettled([
          refreshCoreData(),
          refreshHealthData(),
          refreshConfigData(),
          refreshChunkingStrategies(),
          refreshFieldOptionsData(),
        ])
        const failures = results.filter((result) => result.status === 'rejected')
        if (failures.length > 0) {
          if (results[0]?.status === 'rejected') setCoreState('error')
          if (results[1]?.status === 'rejected') setHealthState('error')
          const reason = failures[0]?.reason
          showError(reason instanceof Error ? reason.message : '部分数据加载失败')
        } else {
          const coreResult = results[0]
          if (coreResult.status === 'fulfilled') {
            setStatusMessage(`当前已加载 ${coreResult.value.documentCount} 个文档，${coreResult.value.jobCount} 个任务`)
          }
        }
      })()
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [documentQuery, jobQuery, refreshCoreData, showError])

  function toggleSelected(docUuid: string) {
    setSelectedIds((current) =>
      current.includes(docUuid) ? current.filter((item) => item !== docUuid) : [...current, docUuid],
    )
  }

  function toggleVisibleSelection() {
    const visibleIds = documents.map((document) => document.doc_uuid)
    setSelectedIds((current) => {
      if (visibleIds.every((docUuid) => current.includes(docUuid))) {
        return current.filter((docUuid) => !visibleIds.includes(docUuid))
      }
      return Array.from(new Set([...current, ...visibleIds]))
    })
  }

  function applyDocumentFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setDocumentQuery({ ...documentFilters, page: 1 })
  }

  function resetDocumentFilters() {
    setDocumentFilters(DEFAULT_DOCUMENT_QUERY)
    setDocumentQuery(DEFAULT_DOCUMENT_QUERY)
  }

  function applyJobFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setJobQuery({ ...jobFilters, page: 1 })
  }

  function resetJobFilters() {
    setJobFilters(DEFAULT_JOB_QUERY)
    setJobQuery(DEFAULT_JOB_QUERY)
  }

  async function openDocumentDetail(docId: string) {
    try {
      const data = await fetchDocumentDetail(docId)
      setSelectedDocId(docId)
      setSelectedDoc(data)
      setDocumentEditForm({
        title: data.title,
        source_module: data.source_module,
        source_type: data.source_type,
        tags: normalizeTags((data.tags ?? []).map((tag) => String(tag))),
        chunkingStrategy: typeof data.extra_meta?.chunking_strategy === 'string' ? data.extra_meta.chunking_strategy : 'fixed',
      })
    } catch (error) {
      showError(error instanceof Error ? error.message : '加载文档详情失败')
    }
  }

  async function handleBatchDelete(ids?: string[]) {
    const targets = ids ?? selectedIds
    if (targets.length === 0) { showError('请先选择要删除的文档'); return }
    if (!window.confirm(`确认删除已选中的 ${targets.length} 个文档吗？此操作不可撤销。`)) return
    try {
      const result = await batchDelete(targets)
      setSelectedIds([])
      if (selectedDocId && targets.includes(selectedDocId)) setSelectedDocId(null)
      await refreshDashboard()
      showSuccess(`批量删除完成：成功 ${result.success_count} / ${result.total}`)
    } catch (error) { showError(error instanceof Error ? error.message : '批量删除失败') }
  }

  async function handleBatchReindex(ids?: string[]) {
    const targets = ids ?? selectedIds
    if (targets.length === 0) { showError('请先选择要重建索引的文档'); return }
    if (!window.confirm(`确认重建已选中 ${targets.length} 个文档的索引吗？`)) return
    try {
      const result = await batchReindex(targets)
      await refreshDashboard()
      showSuccess(`批量重建索引完成：成功 ${result.success_count} / ${result.total}`)
    } catch (error) { showError(error instanceof Error ? error.message : '批量重建索引失败') }
  }

  function addUploadTag(tag: string) {
    const normalized = tag.trim()
    if (!normalized) return
    setUploadFields((current) => ({ ...current, tags: normalizeTags([...current.tags, normalized]) }))
    setTagInputValue('')
  }

  function removeUploadTag(tag: string) {
    setUploadFields((current) => ({ ...current, tags: current.tags.filter((item) => item !== tag) }))
  }

  function addEditTag(tag: string) {
    const normalized = tag.trim()
    if (!normalized) return
    setDocumentEditForm((current) => ({ ...current, tags: normalizeTags([...current.tags, normalized]) }))
    setEditTagInputValue('')
  }

  function removeEditTag(tag: string) {
    setDocumentEditForm((current) => ({ ...current, tags: current.tags.filter((item) => item !== tag) }))
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!uploadFile) { showError('请先选择要上传的文件'); return }
    if (!uploadFields.source_type.trim() || !uploadFields.source_module.trim()) {
      showError('文档类型和知识库不能为空'); return
    }

    const formData = new FormData()
    formData.append('file', uploadFile)
    formData.append('title', uploadFields.title)
    formData.append('source_type', uploadFields.source_type)
    formData.append('source_module', uploadFields.source_module)
    formData.append('tags', JSON.stringify(normalizeTags(uploadFields.tags)))
    formData.append('extra_meta', JSON.stringify(buildExtraMeta(uploadFields.chunkingStrategy)))
    try {
      setUploading(true)
      setStatusMessage(`正在上传 ${uploadFile.name}...`)
      const result = await uploadDocument(formData)
      setUploadFile(null)
      if (imagePreviewUrl) {
        URL.revokeObjectURL(imagePreviewUrl)
        setImagePreviewUrl(null)
      }
      setUploadFields((current) => ({
        ...DEFAULT_UPLOAD_FIELDS,
        source_module: firstEnabledValue(fieldOptions, 'source_module', DEFAULT_UPLOAD_FIELDS.source_module),
        source_type: firstEnabledValue(fieldOptions, 'source_type', DEFAULT_UPLOAD_FIELDS.source_type),
        chunkingStrategy: current.chunkingStrategy,
      }))
      setTagInputValue('')
      setUploadInputKey((current) => current + 1)
      await refreshDashboard()
      setSelectedDocId(result.doc_uuid)
      showSuccess(`上传成功，任务号 ${result.job_uuid}`)
    } catch (error) { showError(error instanceof Error ? error.message : '上传失败') }
    finally { setUploading(false) }
  }

  async function startEditDocument(docId: string) {
    setEditDialogOpen(true)
    setEditTagInputValue('')
    try {
      const data = selectedDocId === docId && selectedDoc ? selectedDoc : await fetchDocumentDetail(docId)
      setSelectedDocId(docId)
      setSelectedDoc(data)
      setDocumentEditForm({
        title: data.title,
        source_module: data.source_module,
        source_type: data.source_type,
        tags: normalizeTags((data.tags ?? []).map((tag) => String(tag))),
        chunkingStrategy: typeof data.extra_meta?.chunking_strategy === 'string' ? data.extra_meta.chunking_strategy : 'fixed',
      })
    } catch (error) {
      setEditDialogOpen(false)
      setSelectedDoc(null)
      setSelectedDocId(null)
      showError(error instanceof Error ? error.message : '加载待编辑文档失败')
    }
  }

  function cancelEditDocument() {
    setEditDialogOpen(false)
    setEditTagInputValue('')
    setDocumentEditForm(EMPTY_DOCUMENT_EDIT_FORM)
    setSelectedDoc(null)
    setSelectedDocId(null)
  }

  function closeMoreMenu() {
    setOpenMoreMenuDocUuid(null)
  }

  async function handleSaveDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedDocId) { showError('请先选择要编辑的文档'); return }
    if (!documentEditForm.title.trim()) { showError('文档标题不能为空'); return }
    try {
      setSavingDoc(true)
      const result = await updateDocument(selectedDocId, {
        title: documentEditForm.title.trim(),
        source_module: documentEditForm.source_module.trim(),
        source_type: documentEditForm.source_type.trim(),
        tags: normalizeTags(documentEditForm.tags),
        extra_meta: buildExtraMeta(documentEditForm.chunkingStrategy, selectedDoc?.extra_meta),
      })
      setEditDialogOpen(false)
      setEditTagInputValue('')
      await refreshDashboard()
      setSelectedDoc(null)
      setSelectedDocId(null)
      showSuccess(`已更新文档《${result.title}》`)
    } catch (error) { showError(error instanceof Error ? error.message : '文档更新失败') }
    finally { setSavingDoc(false) }
  }

  return (
    <>
      <section className="panel hero-panel document-hero">
        <div className="hero-copy">
          <p className="eyebrow">文档管理</p>
          <h2>知识文档管理</h2>
          <p className="muted">上传、查看、编辑、删除和重建索引。管理文档元数据。</p>
        </div>
        <div className="hero-actions hero-actions-dashboard">
          <div className="summary-stat-grid">
            <div className="summary-stat">
              <strong>{documentsTotal}</strong>
              <span>当前文档</span>
            </div>
            <div className="summary-stat">
              <strong>{jobsTotal}</strong>
              <span>当前任务</span>
            </div>
            <div className="summary-stat">
              <strong>{selectedIds.length}</strong>
              <span>已选文档</span>
            </div>
          </div>
          <button className="secondary-button hero-action-button" type="button" onClick={() => void refreshDashboard()}>刷新控制台</button>
        </div>
      </section>

      {toast ? <div className="toast-stack"><div className={`toast toast-${toast.tone}`}>{toast.message}</div></div> : null}

      <section className="panel">
        <SectionHeader eyebrow="系统" title="健康与配置" stateLabel={getLoadStateLabel(healthState)} stateClass={`badge-${healthState}`} collapsed={healthCollapsed} onToggle={() => setHealthCollapsed((c) => !c)} />
        {!healthCollapsed ? (
          <div className="health-config-row">
            <div className="health-config-col">
              <p className="eyebrow" style={{marginBottom:6}}>服务状态</p>
              {health ? (
                <div className="status-chips">
                  {Object.entries(health).slice(0, 6).map(([key, value]) => (
                    <span key={key} className={`status-chip status-chip-${getHealthTone(value)}`}>
                      {HEALTH_LABELS[key] ?? key}: {stringifyValue(value)}
                    </span>
                  ))}
                </div>
              ) : <p className="muted">加载中...</p>}
            </div>
            <div className="health-config-col">
              <p className="eyebrow" style={{marginBottom:6}}>运行参数</p>
              {configs ? (
                <div className="status-chips">
                  <span className="status-chip status-chip-neutral">环境: {configs.app_env}</span>
                  <span className="status-chip status-chip-neutral">入库: {configs.ingestion_mode}</span>
                  <span className="status-chip status-chip-neutral">回退: {configs.allow_provider_fallbacks ? '开启' : '关闭'}</span>
                  <span className="status-chip status-chip-neutral">向量: {configs.embedding_model} / {configs.embedding_vector_size}d</span>
                  {configs.llm_model ? <span className="status-chip status-chip-neutral">LLM: {configs.llm_model}</span> : null}
                </div>
              ) : <p className="muted">加载中...</p>}
            </div>
          </div>
        ) : <p className="collapsed-summary">默认折叠。展开后可查看服务状态与运行参数。</p>}
      </section>

      <section className="grid two-up">
        <article className="panel">
          <SectionHeader eyebrow="文档" title="上传文档" stateLabel={uploading ? '上传中' : '待上传'} />
          <form className="form-grid" onSubmit={handleUpload}>
            <FormField label="文档标题" hint="展示在文档列表与检索结果中的主标题。">
              <input type="text" value={uploadFields.title} onChange={(e) => setUploadFields((c) => ({ ...c, title: e.target.value }))} />
            </FormField>
            <FormField label="知识库">
              <select value={uploadFields.source_module} onChange={(e) => setUploadFields((c) => ({ ...c, source_module: e.target.value }))}>
                {sourceModuleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </FormField>
            <FormField label="文档类型">
              <select value={uploadFields.source_type} onChange={(e) => setUploadFields((c) => ({ ...c, source_type: e.target.value }))}>
                {sourceTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </FormField>
            <FormField label="标签" spanTwo hint="标签显示在输入框下方；输入后回车创建。">
              <div className="tag-editor compact-tag-editor">
                <input
                  type="text"
                  value={tagInputValue}
                  placeholder="输入标签后回车"
                  onChange={(e) => setTagInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addUploadTag(tagInputValue)
                    }
                  }}
                />
                <div className="tag-chip-row">
                  {uploadFields.tags.length > 0 ? uploadFields.tags.map((tag) => (
                    <button key={tag} type="button" className="tag-chip" onClick={() => removeUploadTag(tag)}>
                      {tag}<span>×</span>
                    </button>
                  )) : <span className="muted">暂无标签</span>}
                </div>
                {uploadTagSuggestions.length > 0 ? (
                  <div className="tag-suggestion-row">
                    {uploadTagSuggestions.map((tag) => (
                      <button key={tag} type="button" className="tag-suggestion-chip" onClick={() => addUploadTag(tag)}>{tag}</button>
                    ))}
                  </div>
                ) : null}
              </div>
            </FormField>
            <FormField label="切分策略" spanTwo hint="当前扩展元数据主要用于配置切分策略。">
              <select value={uploadFields.chunkingStrategy} onChange={(e) => setUploadFields((c) => ({ ...c, chunkingStrategy: e.target.value }))}>
                {chunkingStrategies.map((strategy) => (
                  <option key={strategy.name} value={strategy.name}>{getChunkingStrategyLabel(strategy.name)}</option>
                ))}
              </select>
            </FormField>
            <FormField label="上传文件" spanTwo hint="支持 pdf/docx/xlsx/txt/md/html/csv/eml/jsonl，以及 jpg/png/gif/bmp/tiff/webp 图片。">
              <div className="file-upload-area">
                <label className="file-upload-label">
                  {uploadFile ? uploadFile.name : '选择文件...'}
                  <input key={uploadInputKey} type="file" className="file-upload-input" onChange={(e) => {
                    const file = e.target.files?.[0] ?? null
                    setUploadFile(file)
                    if (imagePreviewUrl) {
                      URL.revokeObjectURL(imagePreviewUrl)
                      setImagePreviewUrl(null)
                    }
                    if (file && isImageFile(file)) {
                      setImagePreviewUrl(URL.createObjectURL(file))
                    }
                  }} />
                </label>
                {uploadFile ? (
                  <button type="button" className="file-remove-btn" onClick={() => {
                    setUploadFile(null)
                    if (imagePreviewUrl) {
                      URL.revokeObjectURL(imagePreviewUrl)
                      setImagePreviewUrl(null)
                    }
                    setUploadInputKey((c) => c + 1)
                  }}>删除</button>
                ) : null}
                {imagePreviewUrl ? (
                  <img 
                    src={imagePreviewUrl} 
                    alt="图片预览" 
                    className="file-preview-thumb" 
                    onClick={() => setImagePreviewOpen(true)}
                    title="点击查看原图"
                  />
                ) : null}
                {!uploadFields.title.trim() ? (
                  <p className="field-hint muted">建议先补齐标题，再上传文件。</p>
                ) : null}
              </div>
            </FormField>
            <div className="span-two form-submit-row">
              <button className="primary-button" type="submit" disabled={uploading}>{uploading ? '上传中...' : '上传文档'}</button>
            </div>
          </form>
        </article>

        <article className="panel">
          <SectionHeader eyebrow="文档" title="文档列表" stateLabel={getLoadStateLabel(coreState)} stateClass={`badge-${coreState}`} />
          <form className="doc-filter-bar" onSubmit={applyDocumentFilters}>
            <div className="doc-filter-field">
              <label>关键词</label>
              <input type="text" value={documentFilters.keyword} onChange={(e) => setDocumentFilters((c) => ({ ...c, keyword: e.target.value }))} placeholder="标题搜索..." />
            </div>
            <div className="doc-filter-field">
              <label>模块</label>
              <select value={documentFilters.sourceModule} onChange={(e) => setDocumentFilters((c) => ({ ...c, sourceModule: e.target.value }))}>
                <option value="">全部模块</option>
                {sourceModuleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>
            <div className="doc-filter-field">
              <label>类型</label>
              <select value={documentFilters.sourceType} onChange={(e) => setDocumentFilters((c) => ({ ...c, sourceType: e.target.value }))}>
                <option value="">全部类型</option>
                {sourceTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>
            <div className="doc-filter-actions">
              <button className="secondary-button compact-button" type="submit">查询</button>
              <button className="secondary-button compact-button" type="button" onClick={resetDocumentFilters}>重置</button>
            </div>
          </form>
          <div className="doc-batch-bar">
            <span className="muted">{selectedSummary}</span>
            <div className="doc-batch-actions">
              <button className="secondary-button compact-button" type="button" onClick={toggleVisibleSelection}>{allVisibleSelected ? '取消全选' : '全选'}</button>
              <button className="danger-button compact-button" type="button" onClick={() => void handleBatchDelete()}>批量删除</button>
              <button className="secondary-button compact-button" type="button" onClick={() => void handleBatchReindex()}>批量重建</button>
            </div>
          </div>
          {documents.length > 0 ? (
            <table className="doc-table">
              <thead><tr><th style={{width:30}}></th><th className="doc-title-col">标题</th><th>模块</th><th>状态</th><th style={{width:220}}>操作</th></tr></thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.doc_uuid} className={selectedDocId === doc.doc_uuid ? 'row-selected' : ''}>
                    <td className="doc-select-cell"><input className="doc-row-checkbox" type="checkbox" checked={selectedIds.includes(doc.doc_uuid)} onChange={() => toggleSelected(doc.doc_uuid)} onClick={(e) => e.stopPropagation()} /></td>
                    <td className="doc-title-col">
                      <div className="doc-title-with-icon">
                        {isImageExtension(doc.file_ext) ? <span className="doc-type-icon" title="图片文件">🖼️</span> : null}
                        <strong>{doc.title || doc.doc_uuid.slice(0, 8)}</strong>
                      </div>
                    </td>
                    <td>{getFieldLabel(fieldOptions, 'source_module', doc.source_module)} · {getFieldLabel(fieldOptions, 'source_type', doc.source_type)}</td>
                    <td><span className={`status-chip status-chip-${doc.parse_status === 'success' ? 'success' : 'warning'}`}>{doc.parse_status}/{doc.index_status}</span></td>
                    <td className="doc-actions-cell">
                      <button className="secondary-button small" type="button" onClick={() => void openDocumentDetail(doc.doc_uuid)}>查看</button>
                      <button className="danger-button small" type="button" onClick={() => void handleBatchDelete([doc.doc_uuid])}>删除</button>
                      <div className="more-menu-wrap">
                        <button
                          className="secondary-button small"
                          type="button"
                          aria-expanded={openMoreMenuDocUuid === doc.doc_uuid}
                          onClick={() => setOpenMoreMenuDocUuid((current) => current === doc.doc_uuid ? null : doc.doc_uuid)}
                        >
                          更多
                        </button>
                        {openMoreMenuDocUuid === doc.doc_uuid ? (
                          <>
                            <button className="menu-backdrop" type="button" aria-label="关闭更多操作" onClick={closeMoreMenu} />
                            <div className="more-menu" role="menu">
                              {doc.file_exists ? (
                                <button className="more-menu-item" type="button" onClick={() => { downloadDocumentFile(doc.doc_uuid); closeMoreMenu() }}>下载</button>
                              ) : (
                                <button className="more-menu-item" type="button" disabled onClick={closeMoreMenu}>原文件缺失</button>
                              )}
                              <button className="more-menu-item" type="button" onClick={() => { void startEditDocument(doc.doc_uuid); closeMoreMenu() }}>编辑</button>
                              <button className="more-menu-item" type="button" onClick={() => { void handleBatchReindex([doc.doc_uuid]); closeMoreMenu() }}>重建</button>
                            </div>
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted">暂无文档。</p>}
          {documentPageCount > 1 && (
            <div className="pagination">
              <button disabled={documentQuery.page <= 1} onClick={() => setDocumentQuery((c) => ({ ...c, page: c.page - 1 }))}>上一页</button>
              <span>{documentQuery.page} / {documentPageCount}</span>
              <button disabled={documentQuery.page >= documentPageCount} onClick={() => setDocumentQuery((c) => ({ ...c, page: c.page + 1 }))}>下一页</button>
            </div>
          )}
        </article>
      </section>

      {isAsyncMode ? (
        <section className="grid two-up">
          <article className="panel">
            <SectionHeader eyebrow="任务" title="后台处理记录" stateLabel={getLoadStateLabel(coreState)} stateClass={`badge-${coreState}`} />
            <form className="form-grid compact-form" onSubmit={applyJobFilters}>
              <FormField label="状态"><input type="text" value={jobFilters.status} onChange={(e) => setJobFilters((c) => ({ ...c, status: e.target.value }))} /></FormField>
              <div className="span-two form-submit-row">
                <button className="secondary-button" type="submit">查询</button>
                <button className="secondary-button" type="button" onClick={resetJobFilters}>重置</button>
              </div>
            </form>
            {jobs.length > 0 ? (
              <div className="mini-list">
                {jobs.map((job) => (
                  <div key={job.job_uuid} className="mini-list-item align-left">
                    <strong>{getJobTypeLabel(job.job_type)}</strong>
                    <small>状态：<span className={`status-chip status-chip-${getJobTone(job.status)}`}>{getJobStatusLabel(job.status)}</span></small>
                    <small>进度：{getJobStepLabel(job.current_step)} · {formatDateTime(job.created_at)}</small>
                    {job.error_message ? <small className="error-text">{job.error_message}</small> : null}
                  </div>
                ))}
              </div>
            ) : <p className="muted">暂无后台处理记录。</p>}
            {jobPageCount > 1 && (
              <div className="pagination">
                <button disabled={jobQuery.page <= 1} onClick={() => setJobQuery((c) => ({ ...c, page: c.page - 1 }))}>上一页</button>
                <span>{jobQuery.page} / {jobPageCount}</span>
                <button disabled={jobQuery.page >= jobPageCount} onClick={() => setJobQuery((c) => ({ ...c, page: c.page + 1 }))}>下一页</button>
              </div>
            )}
          </article>
        </section>
      ) : null}

      {selectedDoc && !editDialogOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => { setSelectedDocId(null); setSelectedDoc(null) }}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="document-view-dialog-title" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">文档</p>
                <h3 id="document-view-dialog-title">查看文档信息</h3>
              </div>
              <div className="document-actions">
                {selectedDoc.file_exists ? (
                  <button className="secondary-button compact-button" type="button" onClick={() => downloadDocumentFile(selectedDoc.doc_uuid)}>下载原文件</button>
                ) : null}
                <button className="secondary-button compact-button" type="button" onClick={() => { setSelectedDocId(null); setSelectedDoc(null) }}>关闭</button>
              </div>
            </div>
            <dl className="definition-list">
              <div className="definition-row"><dt>标题</dt><dd>{selectedDoc.title}</dd></div>
              <div className="definition-row"><dt>UUID</dt><dd>{selectedDoc.doc_uuid}</dd></div>
              <div className="definition-row"><dt>文件名</dt><dd>{selectedDoc.file_name}</dd></div>
              <div className="definition-row"><dt>知识库</dt><dd>{getFieldLabel(fieldOptions, 'source_module', selectedDoc.source_module)}</dd></div>
              <div className="definition-row"><dt>文档类型</dt><dd>{getFieldLabel(fieldOptions, 'source_type', selectedDoc.source_type)}</dd></div>
              <div className="definition-row"><dt>标签</dt><dd>{selectedDoc.tags.length > 0 ? selectedDoc.tags.join('、') : '无'}</dd></div>
              <div className="definition-row"><dt>切分策略</dt><dd>{getChunkingStrategyLabel(String(selectedDoc.extra_meta?.chunking_strategy ?? 'fixed'))}</dd></div>
              <div className="definition-row"><dt>切片数</dt><dd>{selectedDoc.chunk_count}</dd></div>
              <div className="definition-row"><dt>文件存在</dt><dd><span className={`status-chip status-chip-${selectedDoc.file_exists ? 'success' : 'danger'}`}>{selectedDoc.file_exists ? '是' : '否'}</span></dd></div>
              {isImageExtension(selectedDoc.file_ext) ? (
                <>
                  <div className="definition-row"><dt>文件类型</dt><dd><span className="status-chip status-chip-info">图片文件</span></dd></div>
                  {selectedDoc.file_exists ? (
                    <div className="definition-row">
                      <dt>图片预览</dt>
                      <dd>
                        <div className="image-preview-container large">
                          <img 
                            src={`${API_BASE}/documents/${selectedDoc.doc_uuid}/download`} 
                            alt={selectedDoc.title} 
                            className="image-preview"
                          />
                        </div>
                      </dd>
                    </div>
                  ) : null}
                </>
              ) : null}
            </dl>
          </div>
        </div>
      ) : null}

      {editDialogOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={cancelEditDocument}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="document-edit-dialog-title" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">文档</p>
                <h3 id="document-edit-dialog-title">编辑文档信息</h3>
              </div>
              <button className="secondary-button compact-button" type="button" onClick={cancelEditDocument}>关闭</button>
            </div>
            <form className="form-grid compact-form" onSubmit={handleSaveDocument}>
              <FormField label="标题"><input type="text" value={documentEditForm.title} onChange={(e) => setDocumentEditForm((c) => ({ ...c, title: e.target.value }))} /></FormField>
            <FormField label="知识库">
                <select value={documentEditForm.source_module} onChange={(e) => setDocumentEditForm((c) => ({ ...c, source_module: e.target.value }))}>
                  {getFieldOptions(fieldOptions, 'source_module', documentEditForm.source_module).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </FormField>
              <FormField label="文档类型">
                <select value={documentEditForm.source_type} onChange={(e) => setDocumentEditForm((c) => ({ ...c, source_type: e.target.value }))}>
                  {getFieldOptions(fieldOptions, 'source_type', documentEditForm.source_type).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </FormField>
              <FormField label="标签" spanTwo hint="输入框下方展示已选标签；回车可新增。">
                <div className="tag-editor compact-tag-editor">
                  <input
                    type="text"
                    value={editTagInputValue}
                    placeholder="输入标签后回车"
                    onChange={(e) => setEditTagInputValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addEditTag(editTagInputValue)
                      }
                    }}
                  />
                  <div className="tag-chip-row">
                    {documentEditForm.tags.length > 0 ? documentEditForm.tags.map((tag) => (
                      <button key={tag} type="button" className="tag-chip" onClick={() => removeEditTag(tag)}>{tag}<span>×</span></button>
                    )) : <span className="muted">暂无标签</span>}
                  </div>
                  {editTagSuggestions.length > 0 ? (
                    <div className="tag-suggestion-row">
                      {editTagSuggestions.map((tag) => (
                        <button key={tag} type="button" className="tag-suggestion-chip" onClick={() => addEditTag(tag)}>{tag}</button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </FormField>
              <FormField label="切分策略" spanTwo>
                <select value={documentEditForm.chunkingStrategy} onChange={(e) => setDocumentEditForm((c) => ({ ...c, chunkingStrategy: e.target.value }))}>
                  {chunkingStrategies.map((strategy) => (
                    <option key={strategy.name} value={strategy.name}>{getChunkingStrategyLabel(strategy.name)}</option>
                  ))}
                </select>
              </FormField>
              <div className="span-two form-submit-row">
                <button className="secondary-button" type="button" onClick={cancelEditDocument}>取消</button>
                <button className="primary-button" type="submit" disabled={savingDoc}>{savingDoc ? '保存中...' : '保存修改'}</button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {imagePreviewOpen && imagePreviewUrl ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setImagePreviewOpen(false)}>
          <div className="modal-card image-preview-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">图片预览</p>
                <h3>{uploadFile?.name || '图片'}</h3>
              </div>
              <button className="secondary-button compact-button" type="button" onClick={() => setImagePreviewOpen(false)}>关闭</button>
            </div>
            <div className="image-preview-modal-body">
              <img src={imagePreviewUrl} alt="原图预览" className="image-preview-full" />
            </div>
          </div>
        </div>
      ) : null}

    </>
  )
}
