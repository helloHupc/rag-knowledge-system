# RAG KNOWLEDGE SYSTEM

通用知识库管理平台，用于自建 RAG 知识库场景。支持多种文档解析、灵活切分策略、混合检索，可对接 Dify、自建页面、HTTP 调用等多种前端入口。

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/react-19-blue.svg)](https://react.dev/)

## ✨ 特性

### 📄 文档处理
- **多种格式支持**：PDF、Word、Excel、Markdown、HTML、CSV、邮件、聊天记录
- **图片知识库**：JPG / PNG / GIF / BMP / TIFF / WebP 上传和识别
- **图片识别**：PaddleOCR 文字识别 + 多模态大模型描述，支持表格检测
- **PDF 图片提取**：自动提取 PDF 中嵌入的图片并识别

### ✂️ 智能切分
- **6 种切分策略**：固定长度、按结构、表格感知、父子分层、语义、聊天记录
- **策略预览**：上传前可预览不同策略的切分效果
- **灵活配置**：每种策略支持独立参数调整

### 🔍 检索模式
- **稠密检索（dense）**：纯向量语义检索
- **混合检索（hybrid）**：BM25 + 向量双路召回，alpha 加权融合
- **Rerank 支持**：搜索结果二次排序，提升准确率
- **可调权重**：融合权重 alpha 自由配置
- **评测工作台**：批量评测检索质量（Hit@1、MRR 等指标）

### 🔌 第三方对接
- **Dify 集成**：一键生成 Dify 外部知识库 API 地址，支持多知识库组合
- **通用查询接口**：HTTP POST 接口，任意平台可调用
- **search / qa 双模式**：纯检索或检索+LLM 问答

### 🛡️ 企业落地
- **知识库分类**：通过 source_module 字段分类管理知识库
- **可插拔权限**：实现 PermissionChecker 接口即可对接企业权限系统
- **异步处理**：文档异步解析，上传即返回

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 (React 19)                    │
│              管理后台 · 检索测试 · 评测工作台           │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP / REST API
┌─────────────────▼───────────────────────────────────┐
│                 后端 (FastAPI)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 文档管理  │ │  检索服务  │ │  切分引擎  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 图片识别  │ │  权限系统  │ │  评测服务  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────┬───────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌───────┐  ┌──────────┐  ┌──────────┐
│PostgreSQL│  │ Milvus/Zilliz│  │  Redis   │
│  元数据  │  │  向量存储    │  │  缓存    │
└───────┘  └──────────┘  └──────────┘
```

## 🚀 快速开始

### 前置要求

- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Milvus 2.4+ 或 Zilliz Cloud
- Node.js 18+

### 1. 克隆项目

```bash
git clone https://github.com/helloHupc/rag-knowledge-system.git
cd rag-knowledge-system
```

### 2. 后端配置

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 复制配置文件
cp .env.example .env
```

编辑 `.env` 配置数据库和向量存储：

```bash
# ── 数据库 ──
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/knowledge_base

# ── 向量存储 ──
VECTOR_STORE_PROVIDER=zilliz         # local | zilliz
ZILLIZ_URI=https://your-zilliz-endpoint
ZILLIZ_TOKEN=your-zilliz-token
ZILLIZ_COLLECTION=your-collection-name

# ── 图片识别（可选）──
PADDLE_OCR_TOKEN=your_token          # PaddleOCR API Token
MULTIMODAL_API_BASE=                 # 多模态 API 地址
MULTIMODAL_API_KEY=                  # 多模态 API Key
MULTIMODAL_MODEL=                    # 模型名称

# ── 运行模式 ──
INGESTION_MODE=async                 # async | sync
```

### 3. 数据库初始化

```bash
alembic upgrade head
```

### 4. 启动后端

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 18080
```

后端启动后访问：
- API 文档：http://localhost:18080/docs
- 健康检查：http://localhost:18080/api/v1/health

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端启动后访问：http://localhost:5173

> 详细部署说明见 [`docs/guides/runtime.md`](docs/guides/runtime.md)，包含文件夹同步、对象存储、生产模式等高级配置。

## 📡 API 文档

项目基于 FastAPI 构建，启动后端后自动生成交互式 API 文档：

- **Swagger UI**：http://localhost:18080/docs
- **ReDoc**：http://localhost:18080/redoc

所有接口均可在线测试。完整接口列表见 [`docs/API.md`](docs/API.md)。

### 通用查询接口

```bash
# 纯检索（指定知识库）
curl -X POST http://localhost:18080/api/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query": "调岗审批流程", "top_k": 5, "response_mode": "search", "filters": {"source_module": ["oa"]}}'

# 纯检索（全部知识库）
curl -X POST http://localhost:18080/api/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query": "调岗审批流程", "top_k": 5, "response_mode": "search"}'

# 检索+问答
curl -X POST http://localhost:18080/api/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query": "调岗审批流程是什么？", "top_k": 5, "response_mode": "qa"}'
```

通用查询接口详细文档见 [`docs/contracts/knowledge-api.md`](docs/contracts/knowledge-api.md)。

### Dify 外部知识库配置

在 Dify 中创建外部知识库时：

- **API 端点**：`http://host.docker.internal:18080/api/v1/dify`（不含 `/retrieval`，Dify 会自动拼接）
- **API 密钥**：`.env` 中的 `DIFY_APP_KEY`
- **知识库 ID**：
  - 单知识库：`oa`
  - 多知识库组合：`oa,kf`（逗号分隔多个 source_module）

> ⚠️ Dify 容器内访问宿主机必须用 `host.docker.internal`，不能用 `127.0.0.1`

## 📖 配置参考

### 完整环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | — | PostgreSQL 连接串（必填） |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `VECTOR_STORE_PROVIDER` | `local` | 向量存储类型（local | zilliz） |
| `ZILLIZ_URI` | — | Zilliz 连接地址 |
| `ZILLIZ_TOKEN` | — | Zilliz 连接 Token |
| `ZILLIZ_COLLECTION` | `oa_rag_chunks` | Zilliz 集合名称 |
| `INGESTION_MODE` | `sync` | 文档解析模式 |
| `PADDLE_OCR_TOKEN` | — | PaddleOCR API Token |
| `MULTIMODAL_API_BASE` | — | 多模态 API 地址 |
| `MULTIMODAL_API_KEY` | — | 多模态 API Key |
| `MULTIMODAL_MODEL` | — | 多模态模型名称 |
| `LLM_PROVIDER` | `openai` | LLM 提供者 |
| `LLM_API_BASE` | — | LLM API 地址 |
| `LLM_API_KEY` | — | LLM API Key |
| `LLM_MODEL` | — | LLM 模型名称 |
| `PERMISSION_MODE` | `none` | 权限模式 |
| `DIFY_APP_KEY` | — | Dify 接入密钥 |
| `DIFY_BASE_URL` | — | Dify 服务地址（用于 QA 模式调用 Dify） |

### 图片识别模式

系统根据配置自动选择识别方式：

| 配置情况 | 自动模式 | 效果 |
|----------|----------|------|
| PaddleOCR + 多模态 | 混合 | OCR 文字 + 多模态描述 |
| 仅 PaddleOCR | OCR | 识别图片中文字 |
| 仅多模态 | 描述 | 生成图片内容描述 |
| 都没配 | — | 上传图片时报错 |

## 📂 项目结构

```
.
├── app/
│   ├── api/            # FastAPI 路由（14 个模块）
│   ├── core/           # 配置、错误处理、中间件、日志
│   ├── db/             # SQLAlchemy 基础、会话管理
│   ├── ingestion/      # 解析器注册（10 种）+ 切分引擎（6 种策略）
│   ├── integrations/   # Embedding、LLM、向量存储、图片识别、Rerank
│   ├── models/         # SQLAlchemy 数据模型
│   ├── permissions/    # 权限检查器接口
│   ├── repositories/   # 数据访问层
│   ├── retrieval/      # 混合检索、BM25、评分
│   ├── schemas/        # Pydantic 请求/响应模型
│   ├── services/       # 业务逻辑层
│   └── sources/        # 数据源连接器
├── frontend/           # React 19 + Vite + TypeScript 管理后台
├── docs/
│   ├── contracts/      # 接口契约文档
│   ├── feature_list.json  # 功能清单
│   └── reference/      # 参考文档
├── tests/              # 测试用例（173+）
├── requirements.txt
└── .env.example
```

## 🧪 测试

```bash
# 全量测试
pytest tests/ -x -q

# 切分策略专项
pytest tests/test_chunking_strategies.py -v

# 图片识别专项
pytest tests/test_image_recognition.py -v
```

## 🤝 致谢

学AI，上L站

感谢 [linux.do](https://linux.do) 社区各位佬的公益站！

---
