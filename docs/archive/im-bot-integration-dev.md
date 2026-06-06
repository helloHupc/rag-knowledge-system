# IM 机器人对接方案（飞书 / 企业微信）

> 对应 GitHub Issue #1：「对话接口希望可以加上钉钉 飞书 这些机器人 api」。
> 本期范围：**飞书**、**企业微信**。钉钉预留扩展位，本期不实现。
> 状态：**已在 `feat/im-bot-integration` 分支实现，待用户验收后合并**。
> 验收步骤见 [`docs/guides/im-bot-acceptance.md`](im-bot-acceptance.md)。

---

## 1. 背景与目标

当前系统已具备完整的 RAG 能力，并对外暴露了通用查询接口：

- `POST /api/v1/knowledge/query`（`app/api/knowledge.py`）：`search` / `qa` 双模式
- `POST /api/v1/dify/*`（`app/api/dify.py`）：Dify 外部知识库集成

用户希望在 **IM（飞书 / 企业微信）** 中直接向机器人提问，由机器人调用知识库回答。

**目标**：用户在飞书 / 企业微信里 @机器人（群聊）或私聊发消息提问，机器人基于知识库返回答案，全程不需要打开管理后台或自己拼 HTTP 请求。

---

## 2. 核心结论：可以支持，且改动可控

机器人对接**不需要改动检索 / 问答核心逻辑**，只是新增一个「接入适配层」，把各 IM 平台的回调消息翻译成内部查询，再把答案推回去。这与现有的 Dify 集成是同一类工作。

复用的现有能力：

| 复用对象 | 位置 | 作用 |
|---------|------|------|
| `QaService.answer()` | `app/services/qa.py:25` | 检索 + LLM 生成答案（qa 模式） |
| `RetrievalService.search()` | `app/services/retrieval.py` | 混合检索（search 模式） |
| `BackgroundJobRunner` | `app/services/background_jobs.py:16` | 线程池，承载异步推送 |
| `post_json_with_retries()` | `app/integrations/http_client.py:12` | 带重试的 HTTP 调用 |
| `Settings` + `.env` | `app/core/config.py` | 配置注入（参考 `dify_app_key`） |
| `AppError` / `ErrorCode` | `app/core/errors.py` | 统一错误 |

---

## 3. 总体架构

```
┌──────────────┐   webhook 回调    ┌──────────────────────────────────────────┐
│  飞书 / 企微   │ ───────────────▶ │  接入适配层 app/api/{feishu,wecom}.py       │
│   开放平台     │                  │  · URL 验证（challenge / echostr）          │
│              │ ◀─────────────── │  · 验签 + 解密                              │
└──────────────┘   主动推送答案     │  · 解析出纯文本 query                        │
       ▲                          │  · 立即回 200（避免平台超时重试）            │
       │ 调发消息 API              └───────────────┬────────────────────────────┘
       │                                          │ 提交后台任务
┌──────┴───────────────┐         ┌────────────────▼────────────────────────────┐
│ 平台客户端             │         │  BotDispatchService（统一编排）               │
│ app/integrations/     │ ◀────── │  · 调 QaService / RetrievalService            │
│ {feishu,wecom}_client │  推送    │  · 组装答案文本（含引用来源）                  │
│ · token 缓存          │         │  · 调用对应平台客户端推送                       │
│ · 发消息 / 验签 / 解密 │         └───────────────────────────────────────────────┘
└──────────────────────┘                          │
                                                   ▼
                                   ┌──────────────────────────────┐
                                   │ QaService / RetrievalService  │  ← 现有，不改
                                   └──────────────────────────────┘
```

**分层职责**

- `app/api/{feishu,wecom}.py`：**只管协议适配**——URL 验证、验签、解密、解析消息、按平台契约返回响应。
- `app/services/bot_dispatch.py`：**平台无关的编排**——拿到 `(platform, query, reply_target)` 后查询知识库、组装答案、调用平台客户端推送。三个平台共用。
- `app/integrations/{feishu,wecom}_client.py`：**平台 SDK**——access token 获取与缓存、发消息、验签 / 加解密工具。

---

## 4. 关键设计决策

### 4.1 异步主动推送（而非同步被动回复）

RAG 在 qa 模式下要走 LLM，耗时常在数秒到十几秒；而平台对回调响应有硬超时：

- 飞书：**3 秒**未响应即判定失败并重推（最多 3 次）
- 企业微信：**5 秒**未响应即重试

因此采用：**收到回调 → 立即返回成功 → 后台线程查询并通过发消息 API 主动推送答案**。

- 复用 `BackgroundJobRunner`，新增通用提交方法 `submit(fn, *args)`（见 §7.3）。
- 后台任务在独立 DB session 中运行（与现有 `_run_ingest_job` 一致）。

> 备选「被动回复」（在 HTTP 响应里直接返回答案）仅适合 search 模式且响应极快的场景，本期不作为主路径。

### 4.2 回调响应**不套用** `success_response`

平台对响应体格式有自己的契约，必须原样满足，**不能**包成 `{code,message,data,trace_id}`：

- 飞书 URL 验证：返回 `{"challenge": "<原值>"}`
- 飞书事件：返回 HTTP 200，body 任意（建议 `{"code":0}` 或空）
- 企业微信 URL 验证（GET）：返回**解密后的明文 echostr**（纯文本，非 JSON）
- 企业微信消息（POST）：异步模式下返回空串 `""` 或 `success`（平台视为已接收，不重试）

### 4.3 回答模式可配置（默认 qa）

新增 `BOT_RESPONSE_MODE`（`qa` | `search`，默认 `qa`）。

- `qa`：检索 + LLM 生成完整答案（需配置 LLM，体验最佳）。
- `search`：仅返回命中的知识片段列表（不调 LLM，快、零成本）。

> **待你确认**：默认用 qa 是否 OK，是否需要支持按平台 / 按群切换（见 §11）。

### 4.4 Token 缓存

飞书 `tenant_access_token`、企业微信 `access_token` 有效期均为 7200 秒，**严禁每次请求都换取**（有频率限制）。

- 方案 A（本期默认）：**进程内内存缓存**，带过期时间，提前 5 分钟刷新。单进程 uvicorn 足够。
- 方案 B（可选）：存 **Redis**（项目已集成 `redis`），多 worker 部署时共享。

### 4.5 安全：验签 + 解密 + 防重放

- **验签**：每个回调都校验平台签名（飞书 `X-Lark-Signature` / Verification Token；企业微信 `msg_signature` = SHA1 排序拼接）。校验失败返回 401，**不**进入业务逻辑。
- **解密**：飞书（开启 Encrypt Key 时）AES-256-CBC；企业微信强制 AES-256-CBC。
- **防重放 / 去重**：平台可能重推同一消息。用飞书 `event_id` / 企业微信 `MsgId` 做幂等去重（内存 LRU 或 Redis `SETNX` + TTL），重复消息直接丢弃。

---

## 5. 平台对接细节

### 5.1 飞书（自建应用）

**准备工作（用户在飞书开放平台操作）**

1. 创建「企业自建应用」，获取 **App ID**、**App Secret**。
2. 开通权限：`im:message`（收发消息）、`im:message:send_as_bot`。
3. 「事件订阅」：填回调地址 `https://<域名>/api/v1/feishu/events`，记录 **Verification Token**、**Encrypt Key**（建议开启加密）。
4. 在事件订阅页面添加事件 `im.message.receive_v1`（接收消息 v2.0）；只完成 URL Challenge 不会推送消息事件。
5. 发布版本并通过审核（企业内可自助）；权限或事件变更后必须重新发布。

**回调处理流程（`POST /api/v1/feishu/events`）**

```
请求到达
  ├─ 若开启加密：body = {"encrypt": "..."} → AES 解密 → JSON（密文前 16 字节为 IV）
  ├─ type == "url_verification"：返回 {"challenge": <challenge>}     # 配置阶段，不先验签
  ├─ 普通事件验签：X-Lark-Signature == SHA256(timestamp + nonce + encrypt_key + 原始 body)
  ├─ 校验 header.token == Verification Token
  ├─ event_id 去重（重复直接 200 返回）
  ├─ 解析 event.message.content（JSON 字符串）→ text
  │    · chat_type == "p2p"：私聊，直接处理
  │    · chat_type == "group"：仅当机器人被 @（event.message.mentions）才处理
  ├─ 提交后台任务：dispatch(platform=feishu, query=text, reply_target=...)
  └─ 立即返回 200 {"code":0}
```

**主动推送（平台客户端）**

- 换 token：`POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`，body `{app_id, app_secret}` → `tenant_access_token`（缓存）。
- 回复：`POST /open-apis/im/v1/messages/{message_id}/reply`（带引用上下文）或
  `POST /open-apis/im/v1/messages?receive_id_type=chat_id`，
  body `{receive_id, msg_type:"text", content: json.dumps({"text": answer})}`，
  header `Authorization: Bearer <token>`。

**消息体关键字段**

```jsonc
{
  "schema": "2.0",
  "header": { "event_id": "...", "event_type": "im.message.receive_v1", "token": "..." },
  "event": {
    "sender": { "sender_id": { "open_id": "ou_..." } },
    "message": {
      "message_id": "om_...",
      "chat_id": "oc_...",
      "chat_type": "p2p",            // 或 "group"
      "message_type": "text",
      "content": "{\"text\":\"调岗审批流程是什么？\"}",
      "mentions": [ /* 群聊里被@的人 */ ]
    }
  }
}
```

### 5.2 企业微信（自建应用）

**准备工作（用户在企业微信管理后台操作）**

1. 「应用管理」创建自建应用，获取 **AgentId**、**Secret**；企业 **CorpID**（我的企业）。
2. 应用「接收消息」→「设置 API 接收」：填 URL `https://<域名>/api/v1/wecom/callback`，随机生成 **Token**、**EncodingAESKey**。
3. 配置「可信 IP」/ 域名（如需主动发消息）。

**URL 验证（`GET /api/v1/wecom/callback`）** — 配置阶段一次性

```
params: msg_signature, timestamp, nonce, echostr
  ├─ 验签：msg_signature == SHA1(sort(token, timestamp, nonce, echostr))
  ├─ 解密 echostr（AES-256-CBC）→ 明文
  └─ 返回明文（纯文本）
```

**接收消息（`POST /api/v1/wecom/callback`）**

```
params: msg_signature, timestamp, nonce
body:   <xml><ToUserName>..</ToUserName><Encrypt>..</Encrypt><AgentID>..</AgentID></xml>
  ├─ 验签：msg_signature == SHA1(sort(token, timestamp, nonce, encrypt))
  ├─ 解密 Encrypt（AES-256-CBC）→ 明文 XML
  │    · 明文结构：16B random + 4B msg_len + msg(XML) + receiveid
  ├─ 解析明文 XML：FromUserName(userid)、MsgType、Content
  │    · 仅处理 MsgType == "text"
  ├─ MsgId 去重
  ├─ 提交后台任务：dispatch(platform=wecom, query=Content, reply_target=userid)
  └─ 立即返回空串 ""        # 异步模式，平台不重试
```

**主动推送（平台客户端）**

- 换 token：`GET https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=&corpsecret=<Secret>` → `access_token`（缓存）。
- 发消息：`POST /cgi-bin/message/send?access_token=`，
  body `{touser: userid, msgtype:"text", agentid: <AgentId>, text:{content: answer}}`。

**加解密要点**

- `AESKey = base64decode(EncodingAESKey + "=")`（43 字符 → 32 字节）。
- AES-256-CBC，`IV = AESKey[:16]`，PKCS7 去填充。
- 需要加密库（见 §8）。

---

## 6. 统一编排：BotDispatchService

`app/services/bot_dispatch.py`（新增），平台无关。三个平台的回调最终都汇聚到这里。

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.qa import AnswerRequest
from app.schemas.retrieval import SearchRequest, UserContext, RetrievalFilters
from app.services.qa import QaService
from app.services.retrieval import RetrievalService


@dataclass(slots=True)
class BotReplyTarget:
    platform: str                 # "feishu" | "wecom"
    chat_id: str | None = None    # 飞书 chat_id / 企微无
    message_id: str | None = None # 飞书 reply 用
    user_id: str | None = None    # 企微 touser


class BotDispatchService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def answer_query(self, query: str, *, source_module: list[str] | None = None) -> str:
        user_ctx = UserContext(user_id=f"bot:{self.settings.app_name}")
        filters = RetrievalFilters(source_module=source_module) if source_module else None

        if self.settings.bot_response_mode == "qa":
            result = QaService(self.session).answer(
                AnswerRequest(question=query, top_k=self.settings.bot_top_k,
                              filters=filters, user_context=user_ctx),
                authenticated_identity_required=False,
            )
            return self._format_qa(result)

        result = RetrievalService(self.session).search(
            SearchRequest(query=query, top_k=self.settings.bot_top_k,
                          filters=filters, user_context=user_ctx),
            authenticated_identity_required=False,
        )
        return self._format_search(result)

    # _format_qa / _format_search：拼答案 + 引用来源（标题/来源/链接）为纯文本
```

> 编排层产出**纯文本答案**；「推送」由各平台客户端负责（dispatch 在后台任务里先调 `answer_query`，再调对应 client 的 `send`）。

---

## 7. 代码改动清单

### 7.1 新增文件

| 文件 | 作用 |
|------|------|
| `app/api/feishu.py` | 飞书回调路由（challenge / 验签 / 解密 / 解析 / 200） |
| `app/api/wecom.py` | 企业微信回调路由（GET 验证 + POST 接收） |
| `app/schemas/bot.py` | 回调请求 / 事件 Pydantic 模型 |
| `app/services/bot_dispatch.py` | 平台无关编排（§6） |
| `app/integrations/feishu_client.py` | 飞书 token 缓存 / 发消息 / 验签解密 |
| `app/integrations/wecom_client.py` | 企微 token 缓存 / 发消息 / 验签 / AES 加解密 |
| `app/integrations/bot_crypto.py` | AES-256-CBC 工具（两平台共用） |
| `tests/test_feishu_bot.py` | 飞书：challenge / 验签 / 解析 / 去重 |
| `tests/test_wecom_bot.py` | 企微：URL 验证 / 解密 / 解析 |
| `tests/test_bot_dispatch.py` | 编排：qa / search 答案组装 |

### 7.2 修改文件

| 文件 | 改动 |
|------|------|
| `app/core/config.py` | 新增飞书 / 企微 / 通用 bot 配置项（§9） |
| `app/api/router.py` | `include_router(feishu_router)` / `include_router(wecom_router)` |
| `app/services/background_jobs.py` | 新增通用 `submit(fn, *args)`（§7.3） |
| `app/core/errors.py` | 新增错误码（如 `BOT_SIGNATURE_INVALID = 40102`、`BOT_CONFIG_MISSING = 40006`） |
| `requirements.txt` | 新增 `cryptography`（§8） |
| `.env.example` | 新增配置示例 |
| `README.md` / `docs/API.md` | 接入说明 |

### 7.3 BackgroundJobRunner 扩展

```python
@classmethod
def submit(cls, fn, *args, **kwargs) -> None:
    cls._get_executor().submit(fn, *args, **kwargs)
```

后台任务封装（在 `bot_dispatch.py` 或路由内）：

```python
def run_bot_reply(platform: str, query: str, target: BotReplyTarget, settings: Settings) -> None:
    session = get_session_factory()()
    try:
        answer = BotDispatchService(session, settings).answer_query(query)
        if platform == "feishu":
            FeishuClient(settings).reply(target, answer)
        elif platform == "wecom":
            WecomClient(settings).send(target, answer)
    except Exception:
        logger.exception("bot reply failed: platform=%s", platform)
    finally:
        session.close()
```

---

## 8. 依赖变更

`requirements.txt` 当前**无加密库**。企业微信 AES-256-CBC（及飞书加密模式）需要：

```
cryptography>=43,<46
```

> 说明：`cryptography` 可能已作为传递依赖存在，但显式声明更稳妥。如倾向 `pycryptodome` 亦可，二选一即可。

---

## 9. 新增配置项（`.env` / `Settings`）

```bash
# ── IM 机器人通用 ──
BOT_RESPONSE_MODE=qa            # qa | search
BOT_TOP_K=8
BOT_DEDUP_TTL_SECONDS=300       # 消息去重窗口

# ── 飞书 ──
FEISHU_ENABLED=false
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=             # 开启加密时必填
FEISHU_BASE_URL=https://open.feishu.cn

# ── 企业微信 ──
WECOM_ENABLED=false
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_CALLBACK_TOKEN=
WECOM_ENCODING_AES_KEY=
WECOM_BASE_URL=https://qyapi.weixin.qq.com
```

`Settings` 中按现有风格添加字段（参考 `dify_app_key`），并在 `validate_required_config` 里做：当 `*_ENABLED=true` 时校验对应必填项是否齐全。

---

## 10. 测试计划

| 层级 | 用例 |
|------|------|
| 单元 | AES 加解密往返、签名计算（用平台文档给的样例向量验证） |
| 单元 | 飞书 challenge 透传、加密 challenge 解密、Verification Token 校验 |
| 单元 | 企微 URL 验证（echostr 解密）、消息 XML 解析 |
| 单元 | event_id / MsgId 去重幂等 |
| 单元 | `BotDispatchService` qa / search 答案组装（mock QaService / RetrievalService） |
| 集成 | 回调 → 后台任务提交 → mock 平台客户端被调用（mock httpx） |
| 手动 | 真机：私聊提问、群聊 @机器人、错误签名被拒、超时不重复回答 |

沿用现有 `pytest`（`pytest tests/ -x -q`）。

---

## 11. 待你确认的开放问题

1. **回答模式**：默认 `qa` 是否 OK？是否需要按平台 / 按群切换为 `search`？
2. **企业微信回复方式**：确认用「主动应用消息」（异步推送，推荐）而非「被动 XML 回复」？
3. **飞书回复方式**：用 `reply`（带引用原消息）还是直接发新消息？
4. **群聊触发**：群聊里是否**仅 @机器人**才响应（推荐），私聊直接答？
5. **知识库范围**：机器人默认查**全部知识库**，还是按平台 / 群路由到指定 `source_module`？
6. **Token 缓存载体**：进程内内存（默认）还是 Redis（多 worker）？
7. **答案携带引用**：是否在答案末尾附「来源：标题 / 链接」？飞书可用富文本卡片，企微纯文本。
8. **公网可达**：回调需要平台访问到本服务（公网域名 + HTTPS 或内网穿透）。部署侧是否已具备？

---

## 12. 实现步骤（确认后执行）

- [ ] **S1 配置与基础设施**：`Settings` 新增字段 + 校验；`requirements.txt` 加 `cryptography`；`.env.example` 更新。
- [ ] **S2 加解密 / 验签工具**：`bot_crypto.py` + 单测（用平台样例向量）。
- [ ] **S3 编排层**：`bot_dispatch.py` + `BackgroundJobRunner.submit` + 单测。
- [ ] **S4 飞书**：`feishu_client.py` + `api/feishu.py` + 路由挂载 + 单测。
- [ ] **S5 企业微信**：`wecom_client.py` + `api/wecom.py` + 路由挂载 + 单测。
- [ ] **S6 去重**：`event_id` / `MsgId` 幂等（内存或 Redis）。
- [ ] **S7 文档**：README / `docs/API.md` 接入指南（含平台后台配置截图位）。
- [ ] **S8 联调**：本地用 ngrok / 内网穿透真机验证两个平台。

> 建议先做 **S1–S4（飞书打通端到端）** 作为可验证里程碑，再复制到 **S5（企业微信）**。
```
