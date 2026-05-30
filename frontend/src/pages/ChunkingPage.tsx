import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { downloadDocumentFile, fetchChunkingStrategies, fetchDocuments, previewChunking, previewDocumentChunking } from '../api'
import { getChunkingStrategyLabel } from '../chunkingStrategyLabels'
import { FormField, SectionHeader } from '../components/shared'
import type { ChunkingPreviewSource, ChunkingStrategyInfo, ChunkPreviewResult, DocumentItem } from '../types'

type StrategyGuide = {
  label: string
  summary: string
  details: string
  recommendedFor: string
  tuningAdvice: string
}

type ParamGuide = {
  label: string
  shortHint: string
  helpText: string
}

type PreviewChunkItem = ChunkPreviewResult['chunks'][number]
type ParentChildPreviewGroup = {
  groupKey: string
  parentIndex: number
  parentUuid?: string | null
  parentTotal?: unknown
  chunks: PreviewChunkItem[]
}

const STRATEGY_GUIDES: Record<string, StrategyGuide> = {
  fixed: {
    label: '固定长度切分',
    summary: '按固定字数直接切块，逻辑最简单，适合先快速验证索引和检索链路。',
    details: '系统会按设定的最大字符数顺序切分文本，并保留一定重叠内容，避免刚好在关键信息边界处断开。',
    recommendedFor: '适合纯文本、格式不稳定的资料，或你只是想先确认系统能不能正常切分。',
    tuningAdvice: '如果命中过于零碎，就把单块长度调大；如果单块信息过杂、命中不精准，就把单块长度调小。',
  },
  structural: {
    label: '按结构切分',
    summary: '优先按标题、段落、换行等自然结构切，再对过长片段做二次拆分。',
    details: '相比固定长度，它更尊重文档本身的章节和段落边界，通常更适合规章制度、说明文档、知识库文章。',
    recommendedFor: '适合 Markdown、制度文档、说明手册、FAQ 等本来就有清晰层级结构的内容。',
    tuningAdvice: '一般先保持默认值。若段落很长导致命中不准，可适当缩小最大长度；若上下文丢失，可增大重叠。',
  },
  'table-aware': {
    label: '表格感知切分',
    summary: '识别表格内容，按表头和数据行分组切块，避免把表格拆得支离破碎。',
    details: '系统会尽量保留同一批表格行与表头的对应关系；对非表格文本则回退到普通切分方式。',
    recommendedFor: '适合 CSV、Excel 导出文本、配置表、名录、规则矩阵这类以行列为主的资料。',
    tuningAdvice: '如果每个 chunk 里的表格行太多、不方便命中，就减小每块行数；如果上下文太碎，就增大每块行数。',
  },
  'parent-child': {
    label: '父子分层切分',
    summary: '先切出较大的父块保留上下文，再从父块中切出更小的子块用于精确命中。',
    details: '这种方式适合“既要检索命中精准，又希望回答时拿到更完整上下文”的场景。通常子块用于向量检索，父块用于补充背景。',
    recommendedFor: '适合长制度、长手册、长流程文档，尤其适合一段内容内部有细节，但回答时又需要整段上下文的资料。',
    tuningAdvice: '父块偏大可以保留更多上下文，子块偏小可以提升命中精度。常见做法是父块 2000~4000 字、子块 500~800 字。',
  },
  semantic: {
    label: '语义切分',
    summary: '尽量按语义变化点来切，而不是只看字数或换行。',
    details: '系统会先做句子级拆分，再根据相邻句子的语义相似度寻找断点，让每个 chunk 在主题上更集中。',
    recommendedFor: '适合自然语言较多、段落长度不均、主题切换频繁的说明文、经验总结、会议纪要等内容。',
    tuningAdvice: '如果切得太碎，可降低相似度阈值或提高最小句数；如果一块里主题太杂，可提高阈值或降低最大句数。',
  },
}

const PARAM_GUIDES: Record<string, ParamGuide> = {
  max_chars: {
    label: '单块最大字符数',
    shortHint: '每个切片最多允许多长。',
    helpText: '值越大，单个 chunk 上下文越完整，但命中可能变钝；值越小，命中更细，但可能丢上下文。一般 800~1500 较常见。',
  },
  overlap_chars: {
    label: '相邻切片重叠字符数',
    shortHint: '避免在边界处把关键信息截断。',
    helpText: '值越大，相邻 chunk 重复内容越多，边界信息越不容易丢，但索引冗余会增加。一般可以取主 chunk 长度的 10%~20%。',
  },
  table_rows_per_chunk: {
    label: '每块表格行数',
    shortHint: '每个表格切片最多包含多少行数据。',
    helpText: '值越大，表格上下文更完整；值越小，命中更精准。对结构紧凑的配置表通常 10~30 行较合适，明细表可更小。',
  },
  parent_max_chars: {
    label: '父块最大字符数',
    shortHint: '父块负责保留大段上下文。',
    helpText: '父块建议调大一些，常用 2000~4000。太小会失去“上下文父块”的意义，太大则可能导致上下文过重、不够聚焦。',
  },
  child_max_chars: {
    label: '子块最大字符数',
    shortHint: '子块负责精确检索命中。',
    helpText: '子块建议比父块明显更小，常用 500~800。太大不够精准，太小又容易把完整语义切碎。',
  },
  min_chunk_sentences: {
    label: '每块最少句数',
    shortHint: '防止语义切分切得太碎。',
    helpText: '值越大，每个 chunk 至少会包含更多句子，更稳定但更粗；值越小，切分会更细。常见起点是 3~5 句。',
  },
  max_chunk_sentences: {
    label: '每块最多句数',
    shortHint: '限制语义切分后单块不要过长。',
    helpText: '值越大，每块可容纳更多句子；值越小，主题更聚焦。一般 10~20 句适合作为起点。',
  },
  similarity_threshold: {
    label: '语义断点阈值',
    shortHint: '相邻句子多不像时就更容易断开。',
    helpText: '值越高，系统越敏感，更容易切开主题变化；值越低，系统更倾向于把内容并在一起。通常从 0.4~0.6 开始试。',
  },
  merge_window: {
    label: '语义观察窗口',
    shortHint: '判断语义变化时一次参考多少句。',
    helpText: '窗口越大，判断更平滑，切分更稳；窗口越小，切分更敏感。一般 2~4 就够用，除非文档句子特别短。',
  },
}

function getStrategyGuide(name: string): StrategyGuide {
  return STRATEGY_GUIDES[name] ?? {
    label: getChunkingStrategyLabel(name),
    summary: '当前策略暂无中文说明。',
    details: '可以先用默认参数预览，再根据切分结果决定是否需要调大或调小参数。',
    recommendedFor: '适合先做试切，再根据结果调整。',
    tuningAdvice: '优先观察切片是否过碎、是否过长、是否丢上下文。',
  }
}

function getParamGuide(key: string, minimum?: number, maximum?: number): ParamGuide {
  const guide = PARAM_GUIDES[key]
  if (guide) return guide
  return {
    label: key,
    shortHint: `建议先使用默认值，允许范围 ${minimum ?? '—'} ~ ${maximum ?? '—'}。`,
    helpText: '当前参数暂无中文说明。建议先预览结果，再根据“切得太碎 / 太长 / 丢上下文”来调节。',
  }
}

function metadataText(chunk: PreviewChunkItem, key: string) {
  const value = chunk.metadata_json[key]
  if (value == null || value === '') return ''
  return String(value)
}

function locationItems(chunk: PreviewChunkItem) {
  const items: Array<{ label: string; value: string }> = []
  if (chunk.page_no) items.push({ label: '页码', value: String(chunk.page_no) })
  if (chunk.sheet_name) items.push({ label: 'Sheet', value: chunk.sheet_name })
  if (chunk.row_start || chunk.row_end) {
    items.push({ label: '行号', value: `${chunk.row_start ?? '—'}-${chunk.row_end ?? '—'}` })
  }
  const heading = metadataText(chunk, 'section_heading') || metadataText(chunk, 'parent_section_heading') || chunk.section_title || ''
  if (heading) items.push({ label: '标题', value: heading })
  return items
}

function explainItems(chunk: PreviewChunkItem) {
  const metadata = chunk.metadata_json
  const strategy = metadataText(chunk, 'chunking_strategy')
  const items: Array<{ label: string; value: string }> = []
  if (strategy === 'structural') {
    items.push({ label: '依据', value: metadataText(chunk, 'split_reason') || '结构边界' })
    items.push({
      label: '结构段',
      value: `${metadata.structural_section_index ?? metadata.section_part ?? '—'} / ${metadata.structural_section_total ?? metadata.section_total ?? '—'}`,
    })
  } else if (strategy === 'parent-child') {
    items.push({ label: '父块', value: `${Number(metadata.parent_index ?? 0) + 1} / ${metadata.parent_total ?? '—'}` })
    items.push({ label: '子块', value: `${Number(metadata.child_index ?? 0) + 1} / ${metadata.child_total ?? metadata.total_children_in_parent ?? '—'}` })
    items.push({ label: '父块依据', value: metadataText(chunk, 'parent_split_reason') || '结构聚合' })
  } else if (strategy === 'semantic') {
    items.push({ label: '语义段', value: `${metadata.semantic_segment_index ?? '—'} / ${metadata.semantic_segment_total ?? '—'}` })
    items.push({ label: '句子', value: `${metadata.sentence_start ?? '—'}-${metadata.sentence_end ?? '—'}` })
    items.push({ label: '断点', value: metadataText(chunk, 'semantic_split_reason') || '语义边界' })
    if (metadata.semantic_breakpoint_score != null) {
      items.push({ label: '相似度', value: String(metadata.semantic_breakpoint_score) })
    }
  } else if (strategy === 'table-aware') {
    items.push({ label: '表格批次', value: `${metadata.table_batch ?? '—'} / ${metadata.table_batch_total ?? '—'}` })
    items.push({ label: '渲染', value: metadataText(chunk, 'table_render_mode') || 'plain' })
  } else {
    items.push({ label: '分片', value: `${metadata.split_part ?? chunk.chunk_index + 1} / ${metadata.split_total ?? '—'}` })
  }
  return items.filter((item) => item.value && item.value !== '— / —')
}

function numericMetadata(value: unknown, fallback = 0) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = Number(value ?? fallback)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parentPreviewGroupKey(chunk: PreviewChunkItem) {
  return chunk.parent_chunk_uuid || `parent-index:${numericMetadata(chunk.metadata_json.parent_index)}`
}

function parentGroupLocation(group: ParentChildPreviewGroup) {
  const first = group.chunks[0]
  if (!first) return ''

  const items: string[] = []
  const pageStart = first.metadata_json.parent_page_start
  const pageEnd = first.metadata_json.parent_page_end
  if (pageStart && pageEnd) {
    items.push(`页码 ${pageStart === pageEnd ? pageStart : `${pageStart}-${pageEnd}`}`)
  } else if (first.page_no) {
    items.push(`页码 ${first.page_no}`)
  }
  const heading = metadataText(first, 'parent_section_heading') || first.section_title || ''
  if (heading) items.push(`标题 ${heading}`)
  if (group.parentUuid) items.push(`UUID ${group.parentUuid.slice(0, 8)}`)
  return items.join(' · ')
}

function PreviewExplain({ chunk }: { chunk: PreviewChunkItem }) {
  const explain = explainItems(chunk)
  const locations = locationItems(chunk)
  return (
    <>
      {explain.length > 0 ? (
        <div className="preview-facts">
          {explain.map((item) => (
            <span key={`${item.label}-${item.value}`}><b>{item.label}</b>{item.value}</span>
          ))}
        </div>
      ) : null}
      {locations.length > 0 ? (
        <div className="preview-location-row">
          {locations.map((item) => (
            <span key={`${item.label}-${item.value}`}>{item.label}: {item.value}</span>
          ))}
        </div>
      ) : null}
      <details className="metadata-details">
        <summary>元数据</summary>
        <div className="debug-meta-row">
          {Object.entries(chunk.metadata_json).map(([k, v]) => (
            <span key={k}>{k}: {String(v)}</span>
          ))}
        </div>
      </details>
    </>
  )
}

export function ChunkingPage() {
  const [strategies, setStrategies] = useState<ChunkingStrategyInfo[]>([])
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState('fixed')
  const [params, setParams] = useState<Record<string, number>>({})
  const [paramInputs, setParamInputs] = useState<Record<string, string>>({})
  const [previewText, setPreviewText] = useState('')
  const [previewResult, setPreviewResult] = useState<ChunkPreviewResult | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [docKeyword, setDocKeyword] = useState('')
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null)
  const [previewSource, setPreviewSource] = useState<ChunkingPreviewSource>('text')
  const [previewError, setPreviewError] = useState('')

  function buildDefaultParams(strategy?: ChunkingStrategyInfo) {
    const defaults: Record<string, number> = {}
    const inputDefaults: Record<string, string> = {}
    if (strategy?.params_schema?.properties) {
      for (const [key, prop] of Object.entries(strategy.params_schema.properties)) {
        defaults[key] = prop.default
        inputDefaults[key] = String(prop.default)
      }
    }
    return { defaults, inputDefaults }
  }

  function sanitizeNumericInput(rawValue: string, type: string) {
    if (rawValue === '') return ''
    if (type === 'number') {
      const normalized = rawValue.replace(/[^\d.]/g, '')
      const firstDot = normalized.indexOf('.')
      if (firstDot === -1) return normalized
      return `${normalized.slice(0, firstDot + 1)}${normalized.slice(firstDot + 1).replace(/\./g, '')}`
    }
    return rawValue.replace(/[^\d]/g, '')
  }

  useEffect(() => {
    fetchChunkingStrategies().then((data) => {
      setStrategies(data.strategies)
      if (data.strategies.length > 0) {
        const first = data.strategies[0]
        setSelectedStrategy(first.name)
        const { defaults, inputDefaults } = buildDefaultParams(first)
        setParams(defaults)
        setParamInputs(inputDefaults)
      }
    }).catch(() => {})
    fetchDocuments({ pageSize: 100 }).then((data) => setDocuments(data.items)).catch(() => {})
  }, [])

  function handleStrategyChange(name: string) {
    setSelectedStrategy(name)
    const strategy = strategies.find((s) => s.name === name)
    const { defaults, inputDefaults } = buildDefaultParams(strategy)
    setParams(defaults)
    setParamInputs(inputDefaults)
  }

  function handleParamInputChange(key: string, rawValue: string, type: string) {
    const nextValue = sanitizeNumericInput(rawValue, type)
    setParamInputs((current) => ({ ...current, [key]: nextValue }))
    if (nextValue === '') return
    const parsed = type === 'number' ? Number.parseFloat(nextValue) : Number.parseInt(nextValue, 10)
    if (!Number.isNaN(parsed)) {
      setParams((current) => ({ ...current, [key]: parsed }))
    }
  }

  function handleParamInputBlur(key: string, prop: { default: number; minimum?: number; maximum?: number; type: string }) {
    const rawValue = paramInputs[key]
    if (rawValue === '' || rawValue == null) {
      setParams((current) => ({ ...current, [key]: prop.default }))
      setParamInputs((current) => ({ ...current, [key]: String(prop.default) }))
      return
    }
    const parsed = prop.type === 'number' ? Number.parseFloat(rawValue) : Number.parseInt(rawValue, 10)
    if (Number.isNaN(parsed)) {
      setParams((current) => ({ ...current, [key]: prop.default }))
      setParamInputs((current) => ({ ...current, [key]: String(prop.default) }))
      return
    }

    const min = prop.minimum ?? parsed
    const max = prop.maximum ?? parsed
    const clamped = Math.min(Math.max(parsed, min), max)
    setParams((current) => ({ ...current, [key]: clamped }))
    setParamInputs((current) => ({ ...current, [key]: prop.type === 'number' ? String(clamped) : String(Math.trunc(clamped)) }))
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault()
    setPreviewError('')
    setPreviewing(true)
    try {
      let result: ChunkPreviewResult
      if (previewSource === 'document' && selectedDoc) {
        if (!selectedDoc.file_exists) {
          setPreviewResult(null)
          setPreviewError('该文档的原始文件不存在，无法按真实文件预览切分。请重新上传文件，或切回手动文本预览。')
          return
        }
        result = await previewDocumentChunking(selectedDoc.doc_uuid, { strategy: selectedStrategy, options: params })
      } else {
        if (!previewText.trim()) {
          setPreviewResult(null)
          return
        }
        result = await previewChunking({ strategy: selectedStrategy, text: previewText, options: params })
      }
      setPreviewResult(result)
    } catch (error) {
      setPreviewResult(null)
      setPreviewError(error instanceof Error ? error.message : '预览切分失败')
    }
    finally { setPreviewing(false) }
  }

  function handleDocSelect(doc: DocumentItem) {
    setPreviewError('')
    if (!doc.file_exists) {
      setSelectedDoc(doc)
      setPreviewSource('document')
      setPreviewResult(null)
      setPreviewError('该文档的原始文件不存在，无法下载或按真实文件预览。请重新上传文件。')
      return
    }
    setSelectedDoc(doc)
    setPreviewSource('document')
    setPreviewResult(null)
  }

  function switchToTextPreview() {
    setPreviewSource('text')
    setSelectedDoc(null)
    setPreviewResult(null)
    setPreviewError('')
  }

  const currentStrategy = strategies.find((s) => s.name === selectedStrategy)
  const currentGuide = useMemo(() => getStrategyGuide(selectedStrategy), [selectedStrategy])
  const groupedParentChildPreview = useMemo(() => {
    if (!previewResult || previewResult.strategy !== 'parent-child') return []

    const groups = new Map<string, PreviewChunkItem[]>()
    previewResult.chunks.forEach((chunk) => {
      const groupKey = parentPreviewGroupKey(chunk)
      const current = groups.get(groupKey) ?? []
      current.push(chunk)
      groups.set(groupKey, current)
    })

    return Array.from(groups.entries())
      .map(([groupKey, chunks]) => {
        const sortedChunks = [...chunks].sort((a, b) => numericMetadata(a.metadata_json.child_index) - numericMetadata(b.metadata_json.child_index))
        const first = sortedChunks[0]
        return {
          groupKey,
          parentIndex: numericMetadata(first?.metadata_json.parent_index),
          parentUuid: first?.parent_chunk_uuid,
          parentTotal: first?.metadata_json.parent_total,
          chunks: sortedChunks,
        }
      })
      .sort((a, b) => a.parentIndex - b.parentIndex)
  }, [previewResult])

  const filteredDocs = documents.filter((d) =>
    !docKeyword || d.title.toLowerCase().includes(docKeyword.toLowerCase())
  )

  return (
    <>
      <section className="panel hero-panel compact-hero">
        <div className="hero-copy">
          <p className="eyebrow">切分</p>
          <h2>切分配置</h2>
          <p className="muted">选择切分策略、调整参数、预览切分效果。</p>
        </div>
      </section>

      <section className="grid two-up chunking-config-grid">
        <article className="panel">
          <SectionHeader eyebrow="切分" title="策略与参数" />
          <form className="form-grid" onSubmit={handlePreview}>
            <FormField
              label="切分策略"
              hint="先选策略，再看下方中文说明和推荐调参方向。"
              helpText="不同策略适合不同文档类型。规则制度、手册类一般优先试“按结构切分”或“父子分层切分”。"
            >
              <select value={selectedStrategy} onChange={(e) => handleStrategyChange(e.target.value)}>
                {strategies.map((s) => (
                  <option key={s.name} value={s.name}>{getChunkingStrategyLabel(s.name)}</option>
                ))}
              </select>
            </FormField>
            <div className="span-two strategy-guide-card">
              <div className="strategy-guide-head">
                <div>
                  <p className="eyebrow">策略说明</p>
                  <h4>{currentGuide.label}</h4>
                </div>
                <span className="strategy-guide-badge">{selectedStrategy}</span>
              </div>
              <p className="strategy-guide-summary">{currentGuide.summary}</p>
              <dl className="definition-list strategy-guide-list">
                <div className="definition-row">
                  <dt>它是做什么的</dt>
                  <dd>{currentGuide.details}</dd>
                </div>
                <div className="definition-row">
                  <dt>适合什么文档</dt>
                  <dd>{currentGuide.recommendedFor}</dd>
                </div>
                <div className="definition-row">
                  <dt>调参建议</dt>
                  <dd>{currentGuide.tuningAdvice}</dd>
                </div>
              </dl>
            </div>
            {currentStrategy?.params_schema?.properties &&
              Object.entries(currentStrategy.params_schema.properties).map(([key, prop]) => (
                <FormField
                  key={key}
                  label={getParamGuide(key, prop.minimum, prop.maximum).label}
                  hint={`${getParamGuide(key, prop.minimum, prop.maximum).shortHint} 范围: ${prop.minimum ?? '—'} ~ ${prop.maximum ?? '—'}`}
                  helpText={getParamGuide(key, prop.minimum, prop.maximum).helpText}
                >
                  <input
                    type="number"
                    value={paramInputs[key] ?? String(prop.default)}
                    min={prop.minimum}
                    max={prop.maximum}
                    step={prop.type === 'number' ? 0.1 : 1}
                    onChange={(e) => handleParamInputChange(key, e.target.value, prop.type)}
                    onBlur={() => handleParamInputBlur(key, prop)}
                  />
                </FormField>
              ))}
            <FormField
              label={previewSource === 'document' ? '已上传文件预览' : '预览文本'}
              spanTwo
              helpText={previewSource === 'document'
                ? '当前会直接读取已上传原文件，再按左侧当前策略和参数重新解析、重新切分。Excel、CSV、PDF 等文件都会走各自解析器，不再依赖文本框内容。'
                : '当前预览是对输入框中的文本试切。你可以手动粘贴正文，也可以从右侧点选文档切换为“按真实文件解析结果预览”。文本太短时，不管选哪种策略，通常都只会得到 1 个切片。'}
              hint={previewSource === 'document'
                ? `当前文档：${selectedDoc?.title ?? '未选择'}。预览切分时会使用原始文件内容，并继续套用左侧当前切分策略和参数。`
                : '输入或粘贴一段真实正文来预览切分效果。若切换到已上传文件模式，文本框内容不会参与实际切分。'}
            >
              {previewSource === 'document' ? (
                <div className="definition-list">
                  <div className="definition-row">
                    <dt>文件名</dt>
                    <dd>{selectedDoc?.title ?? '未选择文档'}</dd>
                  </div>
                  <div className="definition-row">
                    <dt>来源</dt>
                    <dd>{selectedDoc ? `${selectedDoc.source_module} · ${selectedDoc.source_type}` : '—'}</dd>
                  </div>
                  <div className="definition-row">
                    <dt>预览方式</dt>
                    <dd>按真实文件解析后切分</dd>
                  </div>
                </div>
              ) : (
                <textarea
                  className="text-area"
                  rows={5}
                  value={previewText}
                  onChange={(e) => {
                    setPreviewText(e.target.value)
                    if (previewSource !== 'text') switchToTextPreview()
                  }}
                />
              )}
            </FormField>
            <div className="span-two form-submit-row">
              {previewSource === 'document' && selectedDoc && selectedDoc.file_exists ? (
                <button className="secondary-button" type="button" onClick={() => downloadDocumentFile(selectedDoc.doc_uuid)}>下载原文件</button>
              ) : null}
              {previewSource === 'document' ? (
                <button className="secondary-button" type="button" onClick={switchToTextPreview}>切回手动文本</button>
              ) : null}
              <button className="primary-button" type="submit" disabled={previewing || (previewSource === 'text' && !previewText.trim()) || (previewSource === 'document' && !!selectedDoc && !selectedDoc.file_exists)}>
                {previewing ? '预览中...' : '预览切分'}
              </button>
            </div>
          </form>
        </article>

        <article className="panel chunking-doc-panel">
          <SectionHeader eyebrow="文档" title="文档列表" />
          <FormField label="搜索文档">
            <input type="text" value={docKeyword} onChange={(e) => setDocKeyword(e.target.value)} placeholder="输入标题关键词..." />
          </FormField>
          <div className="mini-list chunking-doc-list">
            {filteredDocs.slice(0, 20).map((doc) => (
              <button
                key={doc.doc_uuid}
                type="button"
                className={`mini-list-item chunking-doc-list-item align-left ${selectedDoc?.doc_uuid === doc.doc_uuid && previewSource === 'document' ? 'is-selected' : ''}`}
                onClick={() => handleDocSelect(doc)}
              >
                <strong>{doc.title || doc.doc_uuid.slice(0, 8)}</strong>
                <small>{doc.source_module} · {doc.source_type}</small>
                <small>
                  {!doc.file_exists
                    ? '原文件缺失，需重新上传'
                    : selectedDoc?.doc_uuid === doc.doc_uuid && previewSource === 'document'
                    ? '当前将按真实文件预览切分'
                    : '点击切换为真实文件预览'}
                </small>
              </button>
            ))}
            {filteredDocs.length === 0 && <p className="muted">暂无匹配文档。</p>}
          </div>
        </article>
      </section>

      {previewError ? (
        <section className="panel">
          <p className="error-text">{previewError}</p>
        </section>
      ) : null}

      {previewResult ? (
        <section className="panel">
          <SectionHeader eyebrow="预览" title={`${getStrategyGuide(previewResult.strategy).label} · ${previewResult.total_chunks} 个切片`} />
          {previewResult.strategy === 'parent-child' ? (
            <div className="parent-preview-list">
              {groupedParentChildPreview.map((group) => (
                <article key={group.groupKey} className="parent-preview-card">
                  <div className="debug-hit-head">
                    <div>
                      <strong>父块 #{group.parentIndex + 1}</strong>
                      <p>
                        包含 {group.chunks.length} 个子块，下面按顺序展示。
                        {parentGroupLocation(group) ? ` ${parentGroupLocation(group)}` : ''}
                      </p>
                    </div>
                    <span className="status-chip status-chip-neutral">parent: {group.parentIndex + 1} / {String(group.parentTotal ?? '—')}</span>
                  </div>
                  <div className="debug-hit-list">
                    {group.chunks.map((chunk) => (
                      <article key={chunk.chunk_index} className="debug-hit-card child-preview-card">
                        <div className="debug-hit-head">
                          <strong>子块 #{chunk.chunk_index + 1}</strong>
                          <span className="status-chip status-chip-success">{chunk.char_count} 字符</span>
                        </div>
                        <p className="debug-snippet">{chunk.chunk_text}</p>
                        {chunk.context_text ? (
                          <details className="context-details">
                            <summary>父块上下文</summary>
                            <p className="debug-snippet">{chunk.context_text}</p>
                          </details>
                        ) : null}
                        <PreviewExplain chunk={chunk} />
                      </article>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="debug-hit-list">
              {previewResult.chunks.map((chunk) => (
                <article key={chunk.chunk_index} className="debug-hit-card">
                  <div className="debug-hit-head">
                    <strong>#{chunk.chunk_index + 1}</strong>
                    <span className="status-chip status-chip-success">{chunk.char_count} 字符</span>
                  </div>
                  <p className="debug-snippet">{chunk.chunk_text}</p>
                  <PreviewExplain chunk={chunk} />
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </>
  )
}
