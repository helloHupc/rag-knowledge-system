# 企业微信机器人接入说明

本文面向需要把本系统接入企业微信自建应用的用户。接入完成后，员工可以给企业微信自建应用发送问题；系统会调用知识库检索 / 问答能力，并由应用异步推送答案和来源。

> 注意：本文说的是「企业微信自建应用 API 接收消息」，不是「群机器人 Webhook」。群机器人 Webhook 只能向群里推送消息，不能把用户问题回调到本系统。

## 1. 前置条件

- 本系统后端已部署并可访问，默认端口 `18080`。
- 后端有公网 HTTPS 地址。企业微信后台需要能访问该地址。
  - 生产环境建议使用正式域名和 HTTPS 证书。
  - 本地联调可用 Cloudflare Tunnel、ngrok 等工具。
- 知识库已有文档和索引。
- 如使用 `BOT_RESPONSE_MODE=qa`，需配置可用 LLM；如只想先验证通路，可先用 `search`。
- 企业微信管理员权限，用于创建自建应用并配置 API 接收消息。

回调地址格式：

```text
https://<你的域名>/api/v1/wecom/callback
```

## 2. 后端配置

编辑项目根目录 `.env`：

```bash
# 机器人回答模式：qa = 检索+LLM问答；search = 只返回检索片段
BOT_RESPONSE_MODE=qa
BOT_TOP_K=8
BOT_DEDUP_TTL_SECONDS=300

# 企业微信配置
WECOM_ENABLED=true
WECOM_CORP_ID=ww_xxx
WECOM_AGENT_ID=1000001
WECOM_SECRET=xxx
WECOM_CALLBACK_TOKEN=xxx
WECOM_ENCODING_AES_KEY=xxx
WECOM_BASE_URL=https://qyapi.weixin.qq.com
```

字段说明：

| 配置项 | 必填 | 说明 |
|---|---:|---|
| `WECOM_ENABLED` | 是 | 启用企业微信机器人配置校验，生产建议设为 `true` |
| `WECOM_CORP_ID` | 是 | 企业 ID，在「我的企业」页面查看 |
| `WECOM_AGENT_ID` | 是 | 自建应用 AgentId |
| `WECOM_SECRET` | 是 | 自建应用 Secret |
| `WECOM_CALLBACK_TOKEN` | 是 | API 接收消息页面配置的 Token |
| `WECOM_ENCODING_AES_KEY` | 是 | API 接收消息页面配置的 EncodingAESKey，必须为 43 字符 |
| `BOT_RESPONSE_MODE` | 否 | `qa` 或 `search`，默认 `qa` |
| `BOT_TOP_K` | 否 | 每次检索的片段数，默认 `8` |

修改 `.env` 后重启后端：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 18080
```

## 3. 企业微信后台配置

### 3.1 创建自建应用

进入企业微信管理后台：

```text
应用管理 → 自建 → 创建应用
```

记录：

- AgentId → `WECOM_AGENT_ID`
- Secret → `WECOM_SECRET`

进入：

```text
我的企业 → 企业信息
```

记录：

- 企业 ID / CorpID → `WECOM_CORP_ID`

### 3.2 设置应用可见范围

在自建应用页面设置可见范围，确保测试用户在可见范围内。否则用户在企业微信客户端中看不到应用，或无法发送消息。

### 3.3 配置 API 接收消息

进入自建应用页面：

```text
接收消息 → 设置 API 接收
```

填写 URL：

```text
https://<你的域名>/api/v1/wecom/callback
```

填写或生成：

- Token → `WECOM_CALLBACK_TOKEN`
- EncodingAESKey → `WECOM_ENCODING_AES_KEY`

保存前，请先确保后端已重启并读取最新 `.env`。

保存时，企业微信会请求：

```text
GET /api/v1/wecom/callback?msg_signature=...&timestamp=...&nonce=...&echostr=...
```

系统会验签、解密 `echostr`，并返回明文。

### 3.4 配置可信 IP / 域名

企业微信主动发送应用消息可能要求配置可信 IP 或企业可信域名。若 URL 验证通过但回复失败，请在企业微信后台检查：

- 企业可信 IP
- 企业可信域名
- 应用 Secret 是否可用
- 应用可见范围

不同企业微信版本入口略有差异，以后台提示为准。

## 4. 验证 URL

在企业微信「设置 API 接收」页面保存配置。

后端日志应出现：

```text
GET /api/v1/wecom/callback HTTP/1.1" 200 OK
```

企业微信页面应提示保存成功。

如果返回 401，通常是：

- `WECOM_CALLBACK_TOKEN` 和后台 Token 不一致。
- `WECOM_ENCODING_AES_KEY` 填错。
- `.env` 改了但后端没重启。
- 公网域名没有打到当前后端。

## 5. 发送消息测试

在企业微信客户端中找到自建应用，发送：

```text
调岗审批流程是什么？
```

预期：

- 后端收到 `POST /api/v1/wecom/callback` 并返回 200 空串。
- 后端后台执行 embedding / 检索 / LLM。
- 系统调用企业微信 `cgi-bin/gettoken` 获取 `access_token`。
- 系统调用企业微信 `cgi-bin/message/send` 主动发送应用消息。
- 用户收到答案，并附带「来源」。

## 6. 本地模拟测试

企业微信消息是加密 XML，手工 curl 构造较麻烦。建议先跑自动化测试：

```bash
pytest tests/test_wecom_bot.py tests/test_bot_crypto.py tests/test_bot_dispatch.py -q
```

预期：

```text
10 passed
```

该测试覆盖：

- URL 验证签名校验和 `echostr` 解密。
- 加密 XML 文本消息解密。
- 后台回复任务提交。
- `MsgId` 去重。
- 企业微信 API `errcode` 检查。

## 7. 常见问题

### 7.1 URL 验证失败

检查：

1. 回调 URL 是否为：`https://<域名>/api/v1/wecom/callback`
2. `WECOM_CALLBACK_TOKEN` 是否和企业微信后台 Token 一致。
3. `WECOM_ENCODING_AES_KEY` 是否为 43 字符，且和后台一致。
4. `.env` 修改后是否已重启后端。
5. 公网域名是否能访问当前后端。

### 7.2 后端收到 POST，但没有回复

检查后端日志。常见原因：

1. `WECOM_CORP_ID`、`WECOM_AGENT_ID`、`WECOM_SECRET` 填错。
2. 应用可见范围不包含当前用户。
3. 企业微信要求可信 IP / 域名，但未配置。
4. `BOT_RESPONSE_MODE=qa` 时 LLM 配置不可用。
5. 消息类型不是文本。当前只处理 `MsgType=text`。

### 7.3 企业微信 API 返回 HTTP 200，但实际失败

企业微信 API 常用 `errcode` 表示业务失败。系统会检查 `errcode`：

- `errcode=0`：成功。
- `errcode!=0`：记录并抛出错误，后台任务日志会出现 `wecom gettoken failed` 或 `wecom message/send failed`。

常见 `errcode` 方向：

- IP 不在白名单 / 可信 IP。
- Secret 错误或过期。
- AgentId 错误。
- 用户不在应用可见范围。

### 7.4 重复回复

企业微信可能重试同一消息。系统按 `MsgId` 去重，默认缓存时间：

```bash
BOT_DEDUP_TTL_SECONDS=300
```

## 8. 安全建议

- 生产环境使用 HTTPS 正式域名。
- 不要把 CorpID、Secret、Token、EncodingAESKey 提交到代码仓库。
- 定期轮换企业微信密钥。
- 合理配置应用可见范围和可信 IP。
