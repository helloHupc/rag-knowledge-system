# 知识库查询 API 接口文档

## 概述

通用知识库查询接口，支持纯检索（search）和检索+问答（qa）两种模式。
可用于第三方平台（Dify、自建页面等）直接 HTTP 调用。

---

## `POST /api/v1/knowledge/query`

### 请求体

```json
{
  "query": "调岗审批流程",
  "top_k": 8,
  "min_score": 0.2,
  "response_mode": "search",
  "filters": {
    "source_module": ["hr"],
    "source_type": ["rule_doc"],
    "file_ext": [".pdf"]
  },
  "generation_options": {
    "temperature": 0.1,
    "max_tokens": 1200
  }
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | ✅ | — | 查询文本 |
| `top_k` | int | ❌ | 8 | 返回条数，范围 1-50 |
| `min_score` | float | ❌ | 0.2 | 最低分数阈值，范围 0-1 |
| `response_mode` | string | ❌ | "search" | `"search"` 纯检索 / `"qa"` 检索+问答 |
| `filters.source_module` | string[] | ❌ | null | 按知识库筛选 |
| `filters.source_type` | string[] | ❌ | null | 按文档类型筛选 |
| `filters.file_ext` | string[] | ❌ | null | 按文件扩展名筛选 |
| `generation_options.temperature` | float | ❌ | 0.1 | LLM 温度（qa 模式） |
| `generation_options.max_tokens` | int | ❌ | 1200 | LLM 最大输出 token（qa 模式） |

### 响应体

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "query": "调岗审批流程",
    "mode": "search",
    "answer": "[1] 调岗规则: 调岗申请需要增加二级审批...",
    "answer_status": "grounded",
    "references": [
      {
        "doc_uuid": "abc-123",
        "chunk_uuid": "def-456",
        "title": "调岗规则.pdf",
        "source_module": "hr",
        "snippet": "调岗申请需要增加二级审批...",
        "score": 0.85,
        "page_no": 1,
        "sheet_name": null,
        "section_title": "审批流程",
        "version": "v1",
        "updated_at": "2026-05-28T10:00:00",
        "vector_score": 0.82,
        "text_score": 0.75
      }
    ],
    "filters_applied": {
      "source_module": ["hr"]
    },
    "latency_ms": {
      "retrieval": 45,
      "total": 45
    }
  },
  "trace_id": "trc_xxx"
}
```

### `answer_status` 取值

| 值 | 含义 |
|----|------|
| `grounded` | 回答有引用支撑（qa 模式）或检索到结果（search 模式） |
| `insufficient_evidence` | 未检索到足够依据 |

### `latency_ms` 字段

- `search` 模式：`{ "retrieval": N, "total": N }`
- `qa` 模式：`{ "retrieval": N, "generation": N, "total": N }`

---

## 使用示例

### 纯检索（search）

```bash
curl -X POST http://localhost:18080/api/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "调岗审批流程",
    "top_k": 5,
    "response_mode": "search",
    "filters": {"source_module": ["hr"]}
  }'
```

### 检索+问答（qa）

```bash
curl -X POST http://localhost:18080/api/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "调岗审批流程是什么？",
    "top_k": 5,
    "response_mode": "qa",
    "filters": {"source_module": ["hr"]}
  }'
```

---

## 与 Dify 外部知识库接口的关系

| 接口 | 用途 | 认证方式 |
|------|------|----------|
| `POST /api/v1/knowledge/query` | **通用查询**，支持 search + qa | 无（或未来扩展 API Key） |
| `POST /api/v1/dify/knowledge` | Dify 工作流/HTTP 节点 | Bearer Token（`DIFY_APP_KEY`） |
| `POST /api/v1/dify/retrieval` | Dify 官方 External Knowledge API | Bearer Token（`DIFY_APP_KEY`） |

---

## 错误码

| HTTP 状态码 | code | 含义 |
|------------|------|------|
| 422 | — | 请求参数校验失败 |
| 500 | — | 服务端内部错误 |
