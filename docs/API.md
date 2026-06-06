# API 接口文档

项目启动后自动生成交互式 API 文档：

- **Swagger UI**：http://localhost:18080/docs
- **ReDoc**：http://localhost:18080/redoc

---

## 接口总览

### 知识库查询

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/knowledge/query` | 知识库查询（search / qa） |
| POST | `/api/v1/qa/answer` | 检索+LLM 问答 |

### 文档管理

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents` | 文档列表（支持分页、筛选） |
| GET | `/api/v1/documents/{doc_uuid}` | 文档详情 |
| PATCH | `/api/v1/documents/{doc_uuid}` | 更新文档元数据 |
| DELETE | `/api/v1/documents/{doc_uuid}` | 删除文档 |
| POST | `/api/v1/documents/batch/delete` | 批量删除 |
| GET | `/api/v1/documents/{doc_uuid}/download` | 下载原文件 |
| POST | `/api/v1/documents/{doc_uuid}/reindex` | 重建索引 |
| POST | `/api/v1/documents/batch/reindex` | 批量重建索引 |

### 检索测试

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/retrieval/search` | 检索测试 |
| POST | `/api/v1/retrieval/debug-search` | 检索调试（含两路召回明细） |
| GET | `/api/v1/retrieval/strategies` | 可用检索策略列表 |

### 切分策略

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/v1/chunking/strategies` | 可用切分策略列表 |
| POST | `/api/v1/chunking/preview` | 文本切分预览 |
| POST | `/api/v1/chunking/documents/{doc_uuid}/preview` | 真实文件切分预览 |
| GET | `/api/v1/chunking/documents/{doc_uuid}/preview-text` | 文档原始文本预览 |

### 任务管理

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/v1/jobs` | 任务列表 |
| GET | `/api/v1/jobs/{job_uuid}` | 任务详情（含进度） |

### 评测工作台

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/evaluation/datasets` | 创建评测集 |
| GET | `/api/v1/evaluation/datasets` | 评测集列表 |
| GET | `/api/v1/evaluation/datasets/{dataset_uuid}` | 评测集详情 |
| DELETE | `/api/v1/evaluation/datasets/{dataset_uuid}` | 删除评测集 |
| POST | `/api/v1/evaluation/runs` | 发起评测运行 |
| GET | `/api/v1/evaluation/runs` | 评测运行列表 |
| GET | `/api/v1/evaluation/runs/{run_uuid}` | 评测运行详情 |
| DELETE | `/api/v1/evaluation/runs/{run_uuid}` | 删除评测运行 |

### Dify 对接

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/dify/knowledge` | Dify 外部知识库接口（HTTP 节点） |
| POST | `/api/v1/dify/retrieval` | Dify External Knowledge API |

### IM 机器人对接

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/feishu/events` | 飞书事件订阅回调（URL 验证、接收文本消息、异步回复） |
| GET | `/api/v1/wecom/callback` | 企业微信 API 接收 URL 验证 |
| POST | `/api/v1/wecom/callback` | 企业微信接收消息回调（接收文本消息、异步回复） |

### 数据源

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/v1/sources/folder/sync` | 文件夹同步 |
| GET | `/api/v1/sources/sync-runs` | 同步历史列表 |
| GET | `/api/v1/sources/sync-runs/{run_uuid}` | 同步批次详情 |

### 配置管理

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/v1/configs` | 平台配置（切分策略、检索策略、知识库分类等） |

### 健康检查

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查（数据库、Redis、向量存储、LLM 状态） |

---

## 通用查询接口

`POST /api/v1/knowledge/query`

详见 [`docs/contracts/knowledge-api.md`](contracts/knowledge-api.md)

---

## IM 机器人接口说明

详见 [`docs/guides/im-bot-integration.md`](guides/im-bot-integration.md)，验收步骤见 [`docs/guides/im-bot-acceptance.md`](guides/im-bot-acceptance.md)。

### 飞书

- 回调地址：`https://<域名>/api/v1/feishu/events`
- 支持 `url_verification` challenge 透传。
- 支持 `im.message.receive_v1` 文本消息事件。
- 私聊直接响应；群聊仅在消息包含 `mentions` 时响应。
- 后台异步调用知识库问答后，通过飞书 `messages/{message_id}/reply` 主动回复。

### 企业微信

- 回调地址：`https://<域名>/api/v1/wecom/callback`
- `GET` 用于 API 接收 URL 验证，返回解密后的明文 `echostr`。
- `POST` 接收加密 XML 文本消息，立即返回空串避免平台重试。
- 后台异步调用知识库问答后，通过企业微信应用消息主动推送。

### 相关配置

```bash
BOT_RESPONSE_MODE=qa            # qa | search
BOT_TOP_K=8
BOT_DEDUP_TTL_SECONDS=300

FEISHU_ENABLED=false
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
FEISHU_BASE_URL=https://open.feishu.cn

WECOM_ENABLED=false
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_CALLBACK_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_BASE_URL=https://qyapi.weixin.qq.com
```

---

## 响应格式

所有接口统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": { },
  "trace_id": "trc_xxx"
}
```

`code=0` 表示成功，非 0 表示错误。

---

## 认证

默认无需认证。可通过实现 `PermissionChecker` 接口对接企业认证系统。