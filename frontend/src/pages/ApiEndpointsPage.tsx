import { useCallback, useEffect, useMemo, useState } from 'react'
import { getApiBaseUrl } from '../api'
import { SectionHeader } from '../components/shared'
import { loadFieldOptionsSystemConfig } from '../fieldOptions'
import type { FieldOption } from '../types'

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

type ToastTone = 'success' | 'danger'
type ToastState = { id: number; tone: ToastTone; message: string } | null

export function ApiEndpointsPage() {
  const [modules, setModules] = useState<FieldOption[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loadState, setLoadState] = useState<LoadState>('idle')
  const [toast, setToast] = useState<ToastState>(null)

  useEffect(() => {
    const tid = window.setTimeout(() => {
      void (async () => {
        setLoadState('loading')
        try {
          const { config } = await loadFieldOptionsSystemConfig()
          const enabled = config.fields.source_module.filter((o) => o.enabled && o.value.trim())
          setModules(enabled)
          if (enabled.length > 0) {
            setSelected(new Set([enabled[0].value]))
          }
          setLoadState('ready')
        } catch (err) {
          setLoadState('error')
          showToast(err instanceof Error ? err.message : '加载知识库列表失败', 'danger')
        }
      })()
    }, 0)
    return () => window.clearTimeout(tid)
  }, [])

  useEffect(() => {
    if (!toast) return
    const tid = window.setTimeout(() => setToast(null), 2200)
    return () => window.clearTimeout(tid)
  }, [toast])

  function showToast(message: string, tone: ToastTone) {
    setToast({ id: Date.now(), tone, message })
  }

  function toggleModule(value: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  function selectAll() {
    setSelected(new Set(modules.map((m) => m.value)))
  }

  function clearAll() {
    setSelected(new Set())
  }

  const selectedArray = useMemo(() => [...selected].sort(), [selected])

  const baseUrl = getApiBaseUrl()

  // 通用 HTTP 查询接口地址
  const httpUrl = useMemo(() => {
    return `${baseUrl}/knowledge/query`
  }, [baseUrl])

  // Dify 外部知识库接口地址（Dify会自动拼接 /retrieval，这里只填基础路径）
  const difyRetrievalUrl = useMemo(() => {
    return `${baseUrl}/dify`
  }, [baseUrl])

  const difyKnowledgeUrl = useMemo(() => {
    return `${baseUrl}/dify/knowledge`
  }, [baseUrl])

  const filtersJson = useMemo(() => {
    if (selectedArray.length === 0) return '{}'
    return JSON.stringify({ source_module: selectedArray }, null, 2)
  }, [selectedArray])

  const httpExampleBody = useMemo(() => {
    return JSON.stringify(
      {
        query: '你的查询内容',
        top_k: 8,
        response_mode: 'search',
        filters: selectedArray.length > 0 ? { source_module: selectedArray } : undefined,
      },
      null,
      2,
    )
  }, [selectedArray])

  const difyRetrievalExampleBody = useMemo(() => {
    return JSON.stringify(
      {
        knowledge_id: selectedArray.length > 0 ? selectedArray.join(',') : '<知识库编码>',
        query: '你的查询内容',
        retrieval_setting: { top_k: 5, score_threshold: 0.2 },
      },
      null,
      2,
    )
  }, [selectedArray])

  const copyText = useCallback(
    async (text: string, label: string) => {
      try {
        await navigator.clipboard.writeText(text)
        showToast(`${label} 已复制`, 'success')
      } catch {
        showToast('复制失败，请手动选择复制', 'danger')
      }
    },
    [],
  )

  return (
    <>
      <section className="panel hero-panel compact-hero">
        <div className="hero-copy">
          <p className="eyebrow">API 接口</p>
          <h2>接口地址生成</h2>
          <p className="muted">选择知识库，生成可直接用于 Dify 和 HTTP 调用的接口地址。</p>
        </div>
      </section>

      {toast ? (
        <div className="toast-stack">
          <div className={`toast toast-${toast.tone}`}>{toast.message}</div>
        </div>
      ) : null}

      {/* 知识库选择 */}
      <section className="panel">
        <SectionHeader
          eyebrow="第一步"
          title="选择知识库"
          stateLabel={loadState === 'loading' ? '加载中' : loadState === 'error' ? '失败' : '就绪'}
          stateClass={`badge-${loadState === 'error' ? 'error' : loadState === 'ready' ? 'ready' : 'loading'}`}
        />
        <div className="module-selector">
          <div className="module-selector-actions">
            <button className="secondary-button compact-button" type="button" onClick={selectAll}>
              全选
            </button>
            <button className="secondary-button compact-button" type="button" onClick={clearAll}>
              清空
            </button>
            <span className="muted">已选 {selectedArray.length} 个</span>
          </div>
          <div className="module-chips">
            {modules.map((mod) => {
              const active = selected.has(mod.value)
              return (
                <button
                  key={mod.value}
                  className={`chip ${active ? 'chip-active' : ''}`}
                  type="button"
                  onClick={() => toggleModule(mod.value)}
                >
                  {mod.label || mod.value}
                </button>
              )
            })}
            {modules.length === 0 && loadState === 'ready' && (
              <p className="muted">暂无可用知识库，请先在配置管理中添加。</p>
            )}
          </div>
        </div>
      </section>

      {/* 通用 HTTP 查询接口 */}
      <section className="panel">
        <SectionHeader eyebrow="通用接口" title="HTTP 知识库查询" />
        <div className="api-endpoint-block">
          <div className="api-endpoint-header">
            <code className="api-method">POST</code>
            <code className="api-url">{httpUrl}</code>
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => void copyText(httpUrl, '接口地址')}
            >
              复制地址
            </button>
          </div>
          <p className="muted">支持 search（纯检索）和 qa（检索+问答）两种模式，返回完整引用信息。</p>
          <div className="api-example">
            <div className="api-example-head">
              <span>请求示例</span>
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={() => void copyText(httpExampleBody, '请求示例')}
              >
                复制
              </button>
            </div>
            <pre className="code-block">{httpExampleBody}</pre>
          </div>
          <div className="api-example">
            <div className="api-example-head">
              <span>filters 说明</span>
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={() => void copyText(filtersJson, 'filters')}
              >
                复制
              </button>
            </div>
            <pre className="code-block">{`// filters 字段用于按知识库筛选
// source_module: 知识库编码数组
${filtersJson}`}</pre>
          </div>
        </div>
      </section>

      {/* Dify 外部知识库接口 */}
      <section className="panel">
        <SectionHeader eyebrow="Dify 对接" title="Dify External Knowledge API" />
        <div className="api-endpoint-block">
          <div className="api-endpoint-header">
            <code className="api-method">POST</code>
            <code className="api-url">{difyRetrievalUrl}</code>
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => void copyText(difyRetrievalUrl, 'Dify 外部知识库地址')}
            >
              复制地址
            </button>
          </div>
          <p className="muted">
            官方 External Knowledge API 格式。在 Dify 中配置时，API 端点填写 <code>{difyRetrievalUrl}</code>（不含 /retrieval），Dify 会自动拼接。
          </p>
          <div className="api-example">
            <div className="api-example-head">
              <span>Dify 知识库配置说明</span>
            </div>
            <pre className="code-block">{`# Dify 外部知识库配置

# ⚠️ Dify容器内访问宿主机，必须用 host.docker.internal
API 端点：http://host.docker.internal:18080/api/v1/dify
API 密钥：在 .env 中配置的 DIFY_APP_KEY

# 多知识库组合方式（推荐）
# 知识库ID 填写多个 source_module，用逗号分隔
知识库ID：oa,kf

# 单知识库方式
知识库ID：oa

# 元数据过滤方式（在请求中传递）
metadata_condition:
  logical_operator: or
  conditions:
    - name: source_module
      comparison_operator: "="
      value: oa
    - name: source_module
      comparison_operator: "="
      value: kf`}</pre>
          </div>
          <div className="api-example">
            <div className="api-example-head">
              <span>请求示例</span>
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={() => void copyText(difyRetrievalExampleBody, 'Dify 请求示例')}
              >
                复制
              </button>
            </div>
            <pre className="code-block">{difyRetrievalExampleBody}</pre>
          </div>
        </div>

        <div className="api-endpoint-block" style={{ marginTop: '1.5rem' }}>
          <div className="api-endpoint-header">
            <code className="api-method">POST</code>
            <code className="api-url">{difyKnowledgeUrl}</code>
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => void copyText(difyKnowledgeUrl, 'Dify knowledge 地址')}
            >
              复制地址
            </button>
          </div>
          <p className="muted">
            Dify 工作流 / HTTP 工具节点格式，同样需要 Bearer Token 认证。
          </p>
        </div>
      </section>

      {/* 接口说明文档 */}
      <section className="panel">
        <SectionHeader eyebrow="参考" title="接口参数说明" />
        <div className="api-doc-section">
          <h4>通用查询接口 <code>/api/v1/knowledge/query</code></h4>
          <table className="api-doc-table">
            <thead>
              <tr>
                <th>参数</th>
                <th>类型</th>
                <th>必填</th>
                <th>默认值</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>query</td><td>string</td><td>是</td><td>—</td><td>查询文本</td></tr>
              <tr><td>top_k</td><td>int</td><td>否</td><td>8</td><td>返回条数，1-50</td></tr>
              <tr><td>min_score</td><td>float</td><td>否</td><td>0.2</td><td>最低分数阈值，0-1</td></tr>
              <tr><td>response_mode</td><td>string</td><td>否</td><td>search</td><td>search（纯检索）/ qa（检索+问答）</td></tr>
              <tr><td>filters.source_module</td><td>string[]</td><td>否</td><td>null</td><td>按知识库筛选</td></tr>
              <tr><td>filters.source_type</td><td>string[]</td><td>否</td><td>null</td><td>按文档类型筛选</td></tr>
              <tr><td>filters.file_ext</td><td>string[]</td><td>否</td><td>null</td><td>按文件扩展名筛选</td></tr>
              <tr><td>generation_options.temperature</td><td>float</td><td>否</td><td>0.1</td><td>LLM 温度（qa 模式）</td></tr>
              <tr><td>generation_options.max_tokens</td><td>int</td><td>否</td><td>1200</td><td>LLM 最大输出 token（qa 模式）</td></tr>
            </tbody>
          </table>

          <h4 style={{ marginTop: '1.5rem' }}>响应字段</h4>
          <table className="api-doc-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>类型</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>query</td><td>string</td><td>原始查询</td></tr>
              <tr><td>mode</td><td>string</td><td>search / qa</td></tr>
              <tr><td>answer</td><td>string</td><td>回答文本（search 模式为拼接摘要）</td></tr>
              <tr><td>answer_status</td><td>string</td><td>grounded / insufficient_evidence</td></tr>
              <tr><td>references[]</td><td>array</td><td>引用列表，包含 doc_uuid, chunk_uuid, title, snippet, score 等</td></tr>
              <tr><td>filters_applied</td><td>object</td><td>实际生效的过滤条件</td></tr>
              <tr><td>latency_ms</td><td>object</td><td>耗时统计（retrieval, generation, total）</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
