# 部署指南

## 1. 环境准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
```

## 2. 配置数据库

```env
DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/knowledge_base
```

## 2.1 配置文件存储

上传原文件会被保存到 `RAW_DATA_DIR`。本地开发建议使用项目内持久目录：

```env
RAW_DATA_DIR=/path/to/data/raw
```

如果不显式配置，代码默认使用项目根目录下的 `data/raw`。

## 3. 数据库迁移

```bash
alembic upgrade head
```

## 4. 启动后端

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 18080
```

## 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 后端：`http://127.0.0.1:18080`
- 前端：`http://127.0.0.1:5173`
- API 文档：`http://127.0.0.1:18080/docs`

## 6. 运行模式

### 开发/演示模式

```env
ALLOW_PROVIDER_FALLBACKS=true
```

适合页面联调、演示、本地开发。

### 验收/生产模式

```env
ALLOW_PROVIDER_FALLBACKS=false
```

适合真实 provider 验收和外部依赖问题定位。

## 7. 文档解析模式

### 同步模式（Sync）

```env
INGESTION_MODE=sync
```

适合开发调试，上传接口会等待解析完成后返回最终结果。

### 异步模式（Async）

```env
INGESTION_MODE=async
```

推荐生产环境。

- 上传/重建索引接口立即返回 `status=pending`。
- 后台线程执行解析。
- 前端通过 `GET /api/v1/jobs/{job_uuid}` 轮询进度。

## 8. 本地文件夹同步

本地文件夹同步默认关闭。开启方式：

```env
ENABLE_FOLDER_SOURCE=true
FOLDER_SOURCE_ALLOWED_ROOTS=/path/to/docs1,/path/to/docs2
```

> **安全提示**：请务必配置 `FOLDER_SOURCE_ALLOWED_ROOTS` 白名单。

## 9. 故障排查

- 查看日志：`tail -f app.log`（如果配置了文件日志）
- 检查健康状态：`GET /api/v1/health`
- 向量库连接：检查 `MILVUS_URI` 是否可达。
