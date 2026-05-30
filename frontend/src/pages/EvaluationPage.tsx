import { useEffect, useState, type FormEvent } from 'react'
import {
  createEvaluationDataset,
  createEvaluationRun,
  deleteEvaluationDataset,
  deleteEvaluationRun,
  fetchChunkingStrategies,
  fetchEvaluationDatasetDetail,
  fetchEvaluationDatasets,
  fetchEvaluationRunDetail,
  fetchEvaluationRuns,
  fetchRetrievalStrategies,
} from '../api'
import { getChunkingStrategyLabel, getRetrievalStrategyLabel, getStatusLabel } from '../chunkingStrategyLabels'
import { FormField, SectionHeader } from '../components/shared'
import { formatDateTime } from '../utils'
import type { ChunkingStrategyInfo, EvaluationDataset, EvaluationDatasetDetail, EvaluationRun, EvaluationRunDetail, RetrievalStrategyInfo } from '../types'

type Tab = 'datasets' | 'runs'

export function EvaluationPage() {
  const [tab, setTab] = useState<Tab>('datasets')
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState<EvaluationDatasetDetail | null>(null)
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [selectedRun, setSelectedRun] = useState<EvaluationRunDetail | null>(null)
  const [chunkStrats, setChunkStrats] = useState<ChunkingStrategyInfo[]>([])
  const [retrStrats, setRetrStrats] = useState<RetrievalStrategyInfo[]>([])
  const [creating, setCreating] = useState(false)
  const [running, setRunning] = useState(false)
  const [queryCount, setQueryCount] = useState(0)
  const [runDatasetUuid, setRunDatasetUuid] = useState('')

  // Dataset form
  const [dsForm, setDsForm] = useState({ name: '', description: '' })
  const [jsonlText, setJsonlText] = useState('')

  // Run form
  const [runForm, setRunForm] = useState({
    dataset_uuid: '',
    chunking_strategy: 'fixed',
    retrieval_strategy: 'dense',
    fusion_alpha: 0.7,
  })

  useEffect(() => {
    void refreshDatasets()
  }, [])
  useEffect(() => {
    fetchChunkingStrategies().then((d) => setChunkStrats(d.strategies)).catch(() => undefined)
    fetchRetrievalStrategies().then((d) => setRetrStrats(d.strategies)).catch(() => undefined)
  }, [])

  async function refreshDatasets() {
    try {
      setDatasets(await fetchEvaluationDatasets())
    } catch {
      return
    }
  }

  async function refreshRuns(datasetUuid?: string) {
    try {
      setRuns(await fetchEvaluationRuns(datasetUuid ? { dataset_uuid: datasetUuid } : undefined))
    } catch {
      return
    }
  }

  async function handleCreateDataset(event: FormEvent) {
    event.preventDefault()
    if (!dsForm.name.trim()) return
    setCreating(true)
    try {
      const queries = parseJsonl(jsonlText)
      await createEvaluationDataset({ name: dsForm.name.trim(), description: dsForm.description.trim(), queries })
      setDsForm({ name: '', description: '' })
      setJsonlText('')
      setQueryCount(0)
      await refreshDatasets()
    } catch (e) {
      alert(e instanceof Error ? e.message : '创建失败')
    } finally {
      setCreating(false)
    }
  }

  async function handleViewDataset(uuid: string) {
    try {
      setSelectedDataset(await fetchEvaluationDatasetDetail(uuid))
    } catch {
      return
    }
  }

  async function handleDeleteDataset(uuid: string) {
    if (!window.confirm('确认删除此评测集？')) return
    try {
      await deleteEvaluationDataset(uuid)
      setSelectedDataset(null)
      await refreshDatasets()
    } catch {
      return
    }
  }

  async function handleCreateRun(event: FormEvent) {
    event.preventDefault()
    if (!runForm.dataset_uuid.trim()) return
    setRunning(true)
    try {
      await createEvaluationRun({
        dataset_uuid: runForm.dataset_uuid.trim(),
        chunking_strategy: runForm.chunking_strategy,
        retrieval_strategy: runForm.retrieval_strategy,
        retrieval_params: runForm.retrieval_strategy === 'hybrid' ? { fusion_alpha: runForm.fusion_alpha } : undefined,
      })
      await refreshRuns(runForm.dataset_uuid.trim())
    } catch (e) {
      alert(e instanceof Error ? e.message : '启动评测失败')
    } finally {
      setRunning(false)
    }
  }

  async function handleViewRun(uuid: string) {
    try {
      setSelectedRun(await fetchEvaluationRunDetail(uuid))
    } catch {
      return
    }
  }

  async function handleDeleteRun(uuid: string) {
    if (!window.confirm('确认删除此评测运行？')) return
    try {
      await deleteEvaluationRun(uuid)
      if (selectedRun?.run_uuid === uuid) setSelectedRun(null)
      await refreshRuns(runDatasetUuid || undefined)
    } catch {
      return
    }
  }

  function parseJsonl(raw: string) {
    if (!raw.trim()) return []
    const lines = raw.trim().split('\n').filter(Boolean)
    return lines.map((line, i) => {
      try {
        const obj = JSON.parse(line)
        return {
          query_text: String(obj.query ?? obj.query_text ?? ''),
          expected_doc_titles: Array.isArray(obj.expected_doc_titles) ? obj.expected_doc_titles.map(String) : [],
          expected_terms: Array.isArray(obj.expected_terms) ? obj.expected_terms.map(String) : [],
          notes: obj.notes ? String(obj.notes) : undefined,
        }
      } catch { throw new Error(`第 ${i + 1} 行 JSON 解析失败`) }
    })
  }

  function handleJsonlChange(text: string) {
    setJsonlText(text)
    if (!text.trim()) { setQueryCount(0); return }
    try { setQueryCount(parseJsonl(text).length) } catch { setQueryCount(-1) }
  }

  return (
    <>
      <section className="panel hero-panel compact-hero evaluation-hero">
        <div className="hero-copy">
          <p className="eyebrow">评测</p>
          <h2>评测工作台</h2>
          <p className="muted">管理评测数据集、运行评测、查看指标对比。评测使用独立隔离表，不污染生产数据。</p>
        </div>
        <div className="hero-actions hero-actions-inline">
          <div className="tab-switcher" role="tablist" aria-label="评测工作台标签">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'datasets'}
              className={`tab-switch-button ${tab === 'datasets' ? 'active' : ''}`}
              onClick={() => setTab('datasets')}
            >
              评测集
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'runs'}
              className={`tab-switch-button ${tab === 'runs' ? 'active' : ''}`}
              onClick={() => { setTab('runs'); void refreshRuns() }}
            >
              评测运行
            </button>
          </div>
        </div>
      </section>

      {tab === 'datasets' ? (
        <section className="grid two-up">
          <article className="panel">
            <SectionHeader eyebrow="评测" title="创建评测集" />
            <form className="form-grid" onSubmit={handleCreateDataset}>
              <FormField label="名称"><input type="text" value={dsForm.name} onChange={(e) => setDsForm((c) => ({ ...c, name: e.target.value }))} placeholder="例如：客服知识库评测" /></FormField>
              <FormField label="描述"><input type="text" value={dsForm.description} onChange={(e) => setDsForm((c) => ({ ...c, description: e.target.value }))} placeholder="例如：评测客服相关查询的检索效果" /></FormField>
              <FormField label="查询列表 JSONL" spanTwo helpText='每行一个 JSON，必填 query 字段，可选 expected_doc_titles 和 expected_terms'>
                <textarea className="text-area" rows={8} value={jsonlText} onChange={(e) => handleJsonlChange(e.target.value)} placeholder={`示例格式：
{"query":"客服工单系统","expected_doc_titles":["测试图片2"],"expected_terms":["工单","客服"]}
{"query":"出差审批流程","expected_doc_titles":["出差文档"],"expected_terms":["出差","审批"]}
{"query":"请假类型有哪些","expected_doc_titles":["技术文档"],"expected_terms":["请假","年假","病假"]}`} />
              </FormField>
              <div className="span-two form-submit-row">
                <span className="muted" style={{ alignSelf: 'center' }}>
                  {queryCount > 0 ? `已识别 ${queryCount} 条查询` : queryCount === 0 ? '尚未输入' : 'JSON 格式有误'}
                </span>
                <button className="primary-button" type="submit" disabled={creating || queryCount <= 0}>创建评测集</button>
              </div>
            </form>
          </article>
          <article className="panel">
            <SectionHeader eyebrow="评测" title="评测集列表" />
            {datasets.length > 0 ? (
              <div className="mini-list">
                {datasets.map((ds) => (
                  <div key={ds.dataset_uuid} className="mini-list-item align-left">
                    <strong>{ds.name}</strong>
                    <small>{ds.description || '无描述'} · {formatDateTime(ds.created_at)}</small>
                    <div className="inline-actions">
                      <button className="secondary-button" onClick={() => handleViewDataset(ds.dataset_uuid)}>查看</button>
                      <button className="danger-button" onClick={() => handleDeleteDataset(ds.dataset_uuid)}>删除</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="muted">暂无评测集。</p>}
          </article>
        </section>
      ) : (
        <section className="grid two-up">
          <article className="panel">
            <SectionHeader eyebrow="评测" title="发起评测" />
            <form className="form-grid" onSubmit={handleCreateRun}>
              <FormField label="评测集">
                <select value={runForm.dataset_uuid} onChange={(e) => setRunForm((c) => ({ ...c, dataset_uuid: e.target.value }))}>
                  <option value="">请选择评测集</option>
                  {datasets.map((ds) => (
                    <option key={ds.dataset_uuid} value={ds.dataset_uuid}>{ds.name} ({ds.query_count}条查询)</option>
                  ))}
                </select>
              </FormField>
              <FormField label="切分策略">
                <select value={runForm.chunking_strategy} onChange={(e) => setRunForm((c) => ({ ...c, chunking_strategy: e.target.value }))}>
                  {chunkStrats.map((s) => <option key={s.name} value={s.name}>{getChunkingStrategyLabel(s.name)}</option>)}
                </select>
              </FormField>
              <FormField label="检索策略">
                <select value={runForm.retrieval_strategy} onChange={(e) => setRunForm((c) => ({ ...c, retrieval_strategy: e.target.value }))}>
                  {retrStrats.map((s) => <option key={s.name} value={s.name}>{s.label}</option>)}
                </select>
              </FormField>
              {runForm.retrieval_strategy === 'hybrid' && (
                <FormField label="融合权重 alpha">
                  <input type="range" min="0" max="1" step="0.1" value={runForm.fusion_alpha} onChange={(e) => setRunForm((c) => ({ ...c, fusion_alpha: Number(e.target.value) }))} />
                  <span style={{ fontSize: 12, color: '#76624f' }}>{runForm.fusion_alpha}</span>
                </FormField>
              )}
              <div className="span-two form-submit-row">
                <button className="primary-button" type="submit" disabled={running}>{running ? '运行中...' : '运行评测'}</button>
              </div>
            </form>
          </article>
          <article className="panel">
            <SectionHeader eyebrow="评测" title="运行历史" />
            <FormField label="按评测集过滤">
              <input type="text" value={runDatasetUuid} onChange={(e) => { setRunDatasetUuid(e.target.value); refreshRuns(e.target.value || undefined) }} placeholder="输入 dataset_uuid..." />
            </FormField>
            {runs.length > 0 ? (
              <div className="mini-list">
                {runs.map((run) => (
                  <div key={run.run_uuid} className="mini-list-item align-left">
                    <strong>
                      <span className={`status-chip status-chip-${run.status === 'completed' ? 'success' : run.status === 'running' ? 'loading' : run.status === 'failed' ? 'danger' : 'neutral'}`}>{getStatusLabel(run.status)}</span>
                      &nbsp;{getChunkingStrategyLabel(run.chunking_strategy)} + {getRetrievalStrategyLabel(run.retrieval_strategy)}
                    </strong>
                    <small>{run.dataset_name || run.run_uuid.slice(0, 8)} · {run.summary ? `命中率@1: ${(run.summary.hit_at_1_rate * 100).toFixed(0)}%` : ''}</small>
                    <div className="inline-actions">
                      <button className="secondary-button" onClick={() => handleViewRun(run.run_uuid)}>详情</button>
                      <button className="danger-button" onClick={() => handleDeleteRun(run.run_uuid)}>删除</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="muted">暂无评测运行。</p>}
          </article>
        </section>
      )}

      {selectedDataset ? (
        <section className="panel">
          <SectionHeader eyebrow="详情" title={`评测集：${selectedDataset.name}`} />
          <p className="muted">{selectedDataset.description}</p>
          <div className="mini-list">
            {selectedDataset.queries.map((q) => (
              <div key={q.query_uuid} className="mini-list-item align-left">
                <strong>{q.query_text}</strong>
                <small>文档：{q.expected_doc_titles.join(', ') || '无'}</small>
                <small>关键词：{q.expected_terms.join(', ') || '无'}</small>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {selectedRun?.results ? (
        <section className="panel">
          <SectionHeader eyebrow="结果" title={`评测运行：${selectedRun.run_uuid.slice(0, 8)}`} stateLabel={selectedRun.status} stateClass={`badge-${selectedRun.status === 'completed' ? 'ready' : 'loading'}`} />
          {selectedRun.summary ? (
            <div className="debug-overview-grid">
              <div className="summary-stat compact-stat"><strong>{(selectedRun.summary.hit_at_1_rate * 100).toFixed(0)}%</strong><span>命中率@1</span></div>
              <div className="summary-stat compact-stat"><strong>{(selectedRun.summary.hit_at_3_rate * 100).toFixed(0)}%</strong><span>命中率@3</span></div>
              <div className="summary-stat compact-stat"><strong>{(selectedRun.summary.hit_at_5_rate * 100).toFixed(0)}%</strong><span>命中率@5</span></div>
              <div className="summary-stat compact-stat"><strong>{selectedRun.summary.mean_mrr.toFixed(3)}</strong><span>平均倒数排名</span></div>
              <div className="summary-stat compact-stat"><strong>{(selectedRun.summary.mean_term_hit_rate * 100).toFixed(0)}%</strong><span>关键词命中率</span></div>
              <div className="summary-stat compact-stat"><strong>{selectedRun.summary.mean_latency_ms}ms</strong><span>平均延迟</span></div>
            </div>
          ) : null}
          <div className="mini-list">
            {selectedRun.results.map((r) => (
              <div key={r.query_uuid} className="mini-list-item align-left">
                <strong>{r.query_text}</strong>
                <small>
                  命中@1:{r.hit_at_1 ? '✅' : '❌'} @3:{r.hit_at_3 ? '✅' : '❌'} @5:{r.hit_at_5 ? '✅' : '❌'} ·
                  平均倒数排名:{r.mrr.toFixed(2)} · 关键词命中:{(r.expected_term_hit_rate * 100).toFixed(0)}% · {r.avg_latency_ms}ms
                </small>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  )
}
