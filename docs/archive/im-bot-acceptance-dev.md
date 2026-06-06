# 飞书 / 企业微信机器人验收步骤

本文件用于验收 `feat/im-bot-integration` 分支上的 IM 机器人接入功能。验收通过后再合并到 `main`。

## 1. 确认分支

```bash
git status
git branch --show-current
```

预期当前分支为:

```text
feat/im-bot-integration
```

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

本功能新增依赖:

```text
cryptography>=43,<46
```

## 3. 自动化验收

### 3.1 机器人相关测试

```bash
pytest tests/test_config.py tests/test_bot_crypto.py tests/test_bot_dispatch.py tests/test_feishu_bot.py tests/test_wecom_bot.py -q
```

预期:

```text
18 passed
```

### 3.2 Python 编译检查

```bash
python3 -m compileall app tests/test_bot_crypto.py tests/test_bot_dispatch.py tests/test_feishu_bot.py tests/test_wecom_bot.py -q
```

预期:无输出且退出码为 0。

### 3.3 前端构建检查

```bash
cd frontend
npm run build
cd ..
```

预期输出包含:

```text
✓ built
```

### 3.4 全量测试说明

可执行:

```bash
pytest tests/ -x -q
```

当前已知全量测试可能失败在既有 QA 用例:

```text
tests/test_retrieval_qa.py::test_qa_answer_returns_insufficient_evidence_for_high_threshold
expected: insufficient_evidence
actual: grounded
```

该失败与本次 IM 机器人接入无直接修改关系。机器人功能验收以 3.1、3.2 和真机验收为主。

## 4. 配置检查

`.env.example` 应包含:

```bash
BOT_RESPONSE_MODE=qa
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

## 5. 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 18080
```

访问:

```text
http://127.0.0.1:18080/docs
```

应能看到:

```text
POST /api/v1/feishu/events
GET  /api/v1/wecom/callback
POST /api/v1/wecom/callback
```

## 6. 本地接口模拟验收

### 6.1 飞书 URL verification

`.env` 示例:

```bash
FEISHU_VERIFICATION_TOKEN=test-token
```

请求:

```bash
curl -X POST http://127.0.0.1:18080/api/v1/feishu/events \
  -H "Content-Type: application/json" \
  -d '{
    "type": "url_verification",
    "token": "test-token",
    "challenge": "hello-challenge"
  }'
```

预期返回:

```json
{"challenge":"hello-challenge"}
```

### 6.2 飞书文本事件模拟

```bash
curl -X POST http://127.0.0.1:18080/api/v1/feishu/events \
  -H "Content-Type: application/json" \
  -d '{
    "schema": "2.0",
    "header": {
      "event_id": "evt-local-001",
      "event_type": "im.message.receive_v1",
      "token": "test-token"
    },
    "event": {
      "message": {
        "message_id": "om_local_001",
        "chat_id": "oc_local_001",
        "chat_type": "p2p",
        "message_type": "text",
        "content": "{\"text\":\"调岗审批流程是什么?\"}"
      }
    }
  }'
```

预期返回:

```json
{"code":0}
```

如果未配置真实飞书 `APP_ID` / `APP_SECRET`,后台主动推送失败是正常的;该步骤主要验证回调接收与解析。

## 7. 飞书真机验收

1. 准备公网 HTTPS 地址,例如:

   ```bash
   ngrok http 18080
   ```

2. 飞书事件订阅回调地址填写:

   ```text
   https://<公网域名>/api/v1/feishu/events
   ```

3. 飞书开放平台配置：
   - 创建企业自建应用。
   - 获取 `App ID`、`App Secret`。
   - 配置事件订阅 `Verification Token`、`Encrypt Key`。
   - 在事件订阅页面添加事件 `im.message.receive_v1`（接收消息 v2.0）。仅通过 URL Challenge 不会推送消息。
   - 开通权限 `im:message`、`im:message:send_as_bot`。
   - 创建并发布新版本；事件或权限变更后必须重新发布。

4. `.env` 配置:

   ```bash
   FEISHU_ENABLED=true
   FEISHU_APP_ID=cli_xxx
   FEISHU_APP_SECRET=xxx
   FEISHU_VERIFICATION_TOKEN=xxx
   FEISHU_ENCRYPT_KEY=xxx
   FEISHU_BASE_URL=https://open.feishu.cn
   BOT_RESPONSE_MODE=qa
   BOT_TOP_K=8
   ```

5. 重启后端，在飞书后台保存 / 验证 URL。开启 Encrypt Key 时，飞书 Challenge 请求体为 `{"encrypt":"..."}`，后端会先解密再返回 `challenge`。

6. 私聊机器人发送:

   ```text
   调岗审批流程是什么?
   ```

   预期:机器人异步回复答案,并带来源。

7. 群聊中发送:

   ```text
   @机器人 调岗审批流程是什么?
   ```

   预期:机器人回复;不 @ 机器人时不回复。

## 8. 企业微信真机验收

1. 企业微信管理后台创建自建应用,获取:
   - `CorpID`
   - `AgentId`
   - `Secret`

2. 应用 API 接收回调地址填写:

   ```text
   https://<公网域名>/api/v1/wecom/callback
   ```

3. 生成:
   - `Token`
   - `EncodingAESKey`

4. `.env` 配置:

   ```bash
   WECOM_ENABLED=true
   WECOM_CORP_ID=ww_xxx
   WECOM_AGENT_ID=1000001
   WECOM_SECRET=xxx
   WECOM_CALLBACK_TOKEN=xxx
   WECOM_ENCODING_AES_KEY=xxx
   WECOM_BASE_URL=https://qyapi.weixin.qq.com
   BOT_RESPONSE_MODE=qa
   BOT_TOP_K=8
   ```

5. 重启后端,在企业微信后台保存 API 接收配置。

6. 给自建应用发送:

   ```text
   调岗审批流程是什么?
   ```

   预期:应用异步推送答案,并带来源。

## 9. 验收通过标准

```text
[ ] 当前在 feat/im-bot-integration 分支
[ ] 机器人相关测试 18 passed
[ ] Python 编译检查通过
[ ] 前端构建通过
[ ] 后端能正常启动
[ ] Swagger 能看到 3 个新增机器人接口
[ ] 飞书 URL verification 成功
[ ] 飞书私聊机器人能收到答案
[ ] 飞书群聊仅 @ 机器人时回复
[ ] 企业微信 URL 验证成功
[ ] 企业微信给应用发消息能收到答案
[ ] 答案包含知识库来源
[ ] 无重复回复
[ ] main 分支尚未 merge
```

验收通过后回复:

```text
验收通过,可以 merge
```
