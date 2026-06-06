# 飞书机器人接入说明

本文面向需要把本系统接入飞书的用户。接入完成后，员工可以在飞书中私聊机器人，或在群聊中 @ 机器人提问；系统会调用知识库检索 / 问答能力，并由机器人异步返回答案和来源。

## 1. 前置条件

- 本系统后端已部署并可访问，默认端口 `18080`。
- 后端有公网 HTTPS 地址。飞书事件订阅不接受普通内网地址。
  - 生产环境建议使用正式域名和 HTTPS 证书。
  - 本地联调可用 Cloudflare Tunnel、ngrok 等工具。
- 知识库已有文档和索引。
- 如使用 `BOT_RESPONSE_MODE=qa`，需配置可用 LLM；如只想先验证通路，可先用 `search`。

回调地址格式：

```text
https://<你的域名>/api/v1/feishu/events
```

## 2. 后端配置

编辑项目根目录 `.env`：

```bash
# 机器人回答模式：qa = 检索+LLM问答；search = 只返回检索片段
BOT_RESPONSE_MODE=qa
BOT_TOP_K=8
BOT_DEDUP_TTL_SECONDS=300

# 飞书配置
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
FEISHU_ENCRYPT_KEY=xxx
FEISHU_BASE_URL=https://open.feishu.cn
```

字段说明：

| 配置项 | 必填 | 说明 |
|---|---:|---|
| `FEISHU_ENABLED` | 是 | 启用飞书机器人配置校验，生产建议设为 `true` |
| `FEISHU_APP_ID` | 是 | 飞书开放平台应用的 App ID |
| `FEISHU_APP_SECRET` | 是 | 飞书开放平台应用的 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 是 | 事件订阅页面的 Verification Token |
| `FEISHU_ENCRYPT_KEY` | 建议 | 事件订阅页面的 Encrypt Key。若飞书开启加密，必须填写 |
| `BOT_RESPONSE_MODE` | 否 | `qa` 或 `search`，默认 `qa` |
| `BOT_TOP_K` | 否 | 每次检索的片段数，默认 `8` |

修改 `.env` 后重启后端：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 18080
```

## 3. 飞书开放平台配置

### 3.1 创建企业自建应用

1. 打开飞书开放平台。
2. 创建「企业自建应用」。
3. 进入应用详情，记录：
   - App ID
   - App Secret

填入 `.env`：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

### 3.2 开启机器人能力

在应用能力中开启「机器人」。

建议确认机器人名称、头像、可用范围。用户后续会在飞书客户端中搜索这个机器人并发消息。

### 3.3 配置事件订阅地址

进入：

```text
应用详情 → 事件与回调 / 事件订阅
```

填写请求地址：

```text
https://<你的域名>/api/v1/feishu/events
```

复制页面中的：

- Verification Token → `FEISHU_VERIFICATION_TOKEN`
- Encrypt Key → `FEISHU_ENCRYPT_KEY`

> 建议开启 Encrypt Key。系统已支持飞书加密 Challenge 和加密事件。

保存前，请先确保后端已重启并读取最新 `.env`。

### 3.4 添加消息事件

在事件订阅页面添加事件：

```text
im.message.receive_v1
```

中文页面通常叫：

```text
接收消息 v2.0
```

注意：只通过 URL Challenge 不代表消息事件已订阅。必须手动添加该事件，否则用户给机器人发消息时，后端不会收到任何请求。

### 3.5 开通权限

在权限管理中搜索并开通消息相关权限，至少需要：

```text
im:message
im:message:send_as_bot
```

中文名称可能类似：

- 获取与发送单聊、群组消息
- 读取用户发给机器人的单聊消息
- 接收群聊中 @ 机器人消息事件
- 以应用身份发送消息

实际权限名称会随飞书后台版本变化，以页面提示为准。

### 3.6 发布应用版本

权限、事件、机器人能力变更后，必须发布新版本：

```text
版本管理与发布 → 创建版本 → 发布
```

未发布时，飞书客户端消息可能不会触发事件。

## 4. 验证 URL Challenge

在飞书事件订阅页面点击保存 / 重新校验。

后端日志应出现：

```text
POST /api/v1/feishu/events HTTP/1.1" 200 OK
```

飞书页面应提示校验成功。

如需先验证公网链路，可用明文模式本地 curl（仅适合未开启 Encrypt Key 或后端临时清空 `FEISHU_ENCRYPT_KEY`）：

```bash
curl -i -X POST https://<你的域名>/api/v1/feishu/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"url_verification","token":"你的VerificationToken","challenge":"ping"}'
```

预期：

```json
{"challenge":"ping"}
```

若飞书已开启 Encrypt Key，明文 curl 返回 401 是正常的，请以飞书后台校验为准。

## 5. 发送消息测试

### 5.1 私聊测试

在飞书客户端搜索应用机器人，打开会话，发送：

```text
调岗审批流程是什么？
```

预期：

- 后端收到 `POST /api/v1/feishu/events` 并返回 200。
- 后端后台执行 embedding / 检索 / LLM。
- 系统调用飞书 `messages/{message_id}/reply`。
- 机器人回复答案，并附带「来源」。

### 5.2 群聊测试

把机器人拉入群聊，发送：

```text
@机器人 调岗审批流程是什么？
```

预期：机器人回复。

群聊不 @ 机器人时，系统默认不回复，避免干扰群聊。

## 6. 常见问题

### 6.1 Challenge 提示未返回

检查：

1. 回调 URL 是否为：`https://<域名>/api/v1/feishu/events`
2. 公网域名是否能访问当前后端。
3. `.env` 中 `FEISHU_VERIFICATION_TOKEN` 是否和飞书页面一致。
4. 如果开启 Encrypt Key，`FEISHU_ENCRYPT_KEY` 是否和飞书页面完全一致。
5. 修改 `.env` 后是否已重启后端。

### 6.2 后端日志是 `invalid feishu signature`

通常是 Encrypt Key 不一致：

- 飞书页面开启了 Encrypt Key，但 `.env` 未填或填错。
- `.env` 改了但后端没重启。
- 多个后端进程中，公网流量打到了旧进程。

### 6.3 给机器人发消息，后端完全没请求

检查：

1. 事件订阅页面是否已添加 `im.message.receive_v1`。
2. 权限是否已开通。
3. 权限 / 事件变更后是否发布新版本。
4. 是否真的给「应用机器人」发消息。
5. 群聊是否 @ 机器人。
6. 飞书开放平台「事件日志检索」是否有推送记录。

### 6.4 后端收到 200，但机器人没回复

检查：

1. `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 是否正确。
2. 是否开通 `im:message:send_as_bot`。
3. 应用是否已发布。
4. 后端日志中飞书 `tenant_access_token` 或 `messages/{message_id}/reply` 是否报错。
5. `BOT_RESPONSE_MODE=qa` 时，LLM 配置是否可用。

## 7. 成功日志参考

真实链路成功时，后端会出现类似日志：

```text
POST /api/v1/feishu/events HTTP/1.1" 200 OK
POST https://api-inference.modelscope.cn/v1/embeddings "HTTP/1.1 200 OK"
POST https://api.deepseek.com/v1/chat/completions "HTTP/1.1 200 OK"
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal "HTTP/1.1 200 OK"
POST https://open.feishu.cn/open-apis/im/v1/messages/<message_id>/reply "HTTP/1.1 200 OK"
```

## 8. 安全建议

- 生产环境使用 HTTPS 正式域名。
- 建议开启飞书 Encrypt Key。
- 不要把 App Secret、Encrypt Key、Verification Token 提交到代码仓库。
- 定期轮换平台密钥。
