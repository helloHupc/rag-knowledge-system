import { useEffect, useState, type FormEvent } from 'react'
import { FormField, SectionHeader } from '../components/shared'
import { API_BASE, debugSearch, fetchRetrievalStrategies } from '../api'
import {
  DEFAULT_FIELD_OPTIONS_CONFIG,
  getFieldOptions,
  loadFieldOptionsSystemConfig,
} from '../fieldOptions'
import type { DebugSearchDataV2, FieldOptionsConfig, RetrievalStrategiesResponse } from '../types'

export function RetrievalPage() {
  const [debugData, setDebugData] = useState<DebugSearchDataV2 | null>(null)
  const [debugState, setDebugState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [stratInfo, setStratInfo] = useState<RetrievalStrategiesResponse | null>(null)
  const [fieldOptions, setFieldOptions] = useState<FieldOptionsConfig>(DEFAULT_FIELD_OPTIONS_CONFIG)
  const [debugForm, setDebugForm] = useState({
    query: '',
    strategy: 'dense',
    fusionAlpha: 0.7,
    sourceModule: '',
  })

  useEffect(() => {
    fetchRetrievalStrategies().then(setStratInfo).catch(() => {})
    loadFieldOptionsSystemConfig().then((data) => setFieldOptions(data.config)).catch(() => {})
  }, [])

  async function handleDebugSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setDebugState('loading')
    try {
      const payload: Record<string, unknown> = {
        query: debugForm.query,
        top_k: 5,
        strategy: debugForm.strategy,
        filters: debugForm.sourceModule ? { source_module: [debugForm.sourceModule] } : undefined,
      }
      if (debugForm.strategy === 'hybrid') {
        payload.strategy_params = { fusion_alpha: debugForm.fusionAlpha }
      }
      const data = await debugSearch(payload as Parameters<typeof debugSearch>[0])
      setDebugData(data)
      setDebugState('ready')
    } catch { setDebugState('error') }
  }

  return (
    <>
      <section className="panel hero-panel compact-hero">
        <div className="hero-copy">
          <p className="eyebrow">检索</p>
          <h2>检索测试</h2>
          <p className="muted">选择检索策略、调整参数、即时搜索并查看详细结果和分数拆解。</p>
        </div>
        <div className="hero-actions">
          {stratInfo ? (
            <div className="summary-stat">
              <strong>{stratInfo.strategies.length}</strong>
              <span>可用策略</span>
            </div>
          ) : null}
          {stratInfo?.rerank?.enabled ? (
            <div className="summary-stat">
              <strong>Rerank</strong>
              <span>{stratInfo.rerank.model ?? '已启用'}</span>
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <SectionHeader eyebrow="检索" title="调试检索" stateLabel={debugState === 'loading' ? '搜索中' : debugState === 'ready' ? '完成' : debugState === 'error' ? '失败' : '就绪'} stateClass={`badge-${debugState === 'ready' ? 'ready' : debugState === 'error' ? 'error' : 'loading'}`} />
        <form className="form-grid debug-form" onSubmit={handleDebugSearch}>
          <FormField label="检索策略">
            <select value={debugForm.strategy} onChange={(e) => setDebugForm((c) => ({ ...c, strategy: e.target.value }))}>
              {stratInfo?.strategies.map((s) => (
                <option key={s.name} value={s.name}>{s.label}</option>
              )) ?? (
                <>
                  <option value="dense">稠密检索</option>
                  <option value="hybrid">混合检索</option>
                </>
              )}
            </select>
          </FormField>
          {debugForm.strategy === 'hybrid' && (
            <FormField label="融合权重 alpha" hint="向量权重（0~1），值越大越偏语义">
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={debugForm.fusionAlpha}
                onChange={(e) => setDebugForm((c) => ({ ...c, fusionAlpha: Number(e.target.value) }))}
              />
              <span style={{ fontSize: 12, color: '#76624f' }}>{debugForm.fusionAlpha}</span>
            </FormField>
          )}
          <div className="span-two strategy-guide-card">
            <div className="strategy-guide-head">
              <div>
                <p className="eyebrow">分数说明</p>
                <h4>{debugForm.strategy === 'hybrid' ? '混合检索打分' : '稠密检索打分'}</h4>
              </div>
            </div>
            {debugForm.strategy === 'hybrid' ? (
              <dl className="definition-list strategy-guide-list">
                <div className="definition-row">
                  <dt>向量分数</dt>
                  <dd>向量召回原始分，只代表语义相似度，不是最终排序分。</dd>
                </div>
                <div className="definition-row">
                  <dt>稀疏分数</dt>
                  <dd>BM25 关键词检索原始分。若显示 null，表示这条结果没有进入稀疏召回结果。</dd>
                </div>
                <div className="definition-row">
                  <dt>最终分数</dt>
                  <dd>不是平均数。系统会先分别对稠密分和稀疏分做归一化，再按 alpha 融合，公式约等于 alpha × dense_norm + (1 - alpha) × sparse_norm。</dd>
                </div>
              </dl>
            ) : (
              <dl className="definition-list strategy-guide-list">
                <div className="definition-row">
                  <dt>向量分数</dt>
                  <dd>纯向量检索分数，代表语义相似度，即最终排序分。</dd>
                </div>
              </dl>
            )}
          </div>
          <FormField label="查询词" hint="输入你要验证的检索问题或关键词。">
            <input type="text" value={debugForm.query} onChange={(e) => setDebugForm((c) => ({ ...c, query: e.target.value }))} />
          </FormField>
          <FormField label="知识库" hint="可留空。">
            <select value={debugForm.sourceModule} onChange={(e) => setDebugForm((c) => ({ ...c, sourceModule: e.target.value }))}>
              <option value="">全部模块</option>
              {getFieldOptions(fieldOptions, 'source_module', debugForm.sourceModule).map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </FormField>
          <div className="span-two form-submit-row">
            <button className="primary-button" type="submit">执行调试检索</button>
          </div>
        </form>

        {debugData ? (
          <div className="debug-result-area">
            <div className="debug-overview-grid">
              <div className="summary-stat compact-stat"><strong>{debugData.hits.length}</strong><span>命中条数</span></div>
              <div className="summary-stat compact-stat"><strong>{debugData.latency_ms}ms</strong><span>接口耗时</span></div>
              <div className="summary-stat compact-stat"><strong>{debugData.query}</strong><span>原始查询</span></div>
              <div className="summary-stat compact-stat"><strong>{debugData.rewritten_query}</strong><span>改写查询</span></div>
              {debugData.retrieval_strategy && (
                <div className="summary-stat compact-stat"><strong>{debugData.retrieval_strategy}</strong><span>检索策略</span></div>
              )}
              {debugData.rerank_enabled && (
                <div className="summary-stat compact-stat"><strong>{debugData.rerank_latency_ms}ms</strong><span>Rerank 耗时</span></div>
              )}
            </div>
            {debugData.hits.length > 0 ? (
              <div className="debug-hit-list">
                {debugData.hits.map((hit) => (
                  <article key={hit.chunk_uuid} className="debug-hit-card">
                    <div className="debug-hit-head">
                      <div>
                        <strong>{hit.title}</strong>
                        <p className="muted">文档：{hit.doc_uuid} · Chunk：{hit.chunk_uuid}</p>
                      </div>
                      <span className="status-chip status-chip-success">score {hit.score.toFixed(3)}</span>
                    </div>
                    <div className="debug-meta-row">
                      <span>模块：{hit.source_module}</span>
                      <span>版本：{hit.version}</span>
                      <span>向量原始分：{hit.vector_score?.toFixed(3) ?? '—'}</span>
                      {'sparse_score' in hit && <span>稀疏原始分：{(hit as { sparse_score?: number }).sparse_score?.toFixed(3) ?? '—'}</span>}
                      {'rerank_score' in hit && (hit as { rerank_score?: number }).rerank_score != null && <span>重排：{(hit as { rerank_score: number }).rerank_score.toFixed(3)}</span>}
                    </div>
                    <p className="debug-snippet">{hit.snippet}</p>
                    {hit.image_url && (
                      <div className="debug-hit-image">
                        <img src={`${API_BASE.replace('/api/v1', '')}${hit.image_url}`} alt={hit.title} />
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : (
               <div className="empty-debug-state"><strong>本次检索返回 0 条命中</strong><p>可以尝试放宽知识库限制，检查当前用户是否有对应权限，或者改用更明确的查询词。</p></div>
            )}
            <details className="debug-raw-box">
              <summary>查看排序调试明细</summary>
              <pre>{JSON.stringify(debugData.ranking_debug, null, 2)}</pre>
            </details>
            {(debugData.dense_hits?.length || debugData.sparse_hits?.length) ? (
              <details className="debug-raw-box">
                <summary>查看召回来源明细</summary>
                <pre>{JSON.stringify({ dense_hits: debugData.dense_hits, sparse_hits: debugData.sparse_hits }, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        ) : (
          <div className="empty-debug-state"><strong>执行后结果会显示在这里</strong><p>包括命中条数、耗时、命中卡片以及排序调试明细。</p></div>
        )}
      </section>
    </>
  )
}
