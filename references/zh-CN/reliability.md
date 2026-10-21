# 可靠性与故障排查

[English](../reliability.md) | 简体中文

> 翻译基线：英文文档提交 [`a152eb4`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。接口定义以共用 OpenAPI 为准。

本页说明[接入流程](development-path.md)中各项请求的规则。仅应用与所选 OpenAPI 操作相关的规则。

<a id="prepare-a-request"></a>

## 准备请求

构造或重试请求前，确认：

1. 操作的 `security` 允许所用凭据：`/api/v1/org/**` 使用 `OrganizationApiKey`，终端用户路由使用 `UserApiKey`。凭据类型错误返回 `403`；密钥缺失、已撤销或已轮换返回 `401`。
2. 严格按操作声明携带必需的 `Idempotency-Key`、`If-Match`、`Accept` 和 `Content-Length` 请求头。
3. 请求体符合引用的 schema。多数 schema 对未知字段返回 `400 validation_error`。
4. 路径中的 ID 属于你的组织；用户 API 密钥路由的目标还必须属于该终端用户。外部、隐藏和不存在的目标均返回相同的 `404`。

<a id="command-identity-and-idempotency"></a>

## 命令标识与幂等性

两种由客户端指定的标识支持安全重试写入（1–128 个字符，符合 `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`）：

- 在声明需要它的创建和变更操作中，使用 **`Idempotency-Key` 请求头**（模板、Skill 上传和发布、Agent、Session）。
- 在 `POST /api/v1/user/sessions/{id}/events` 中使用请求体字段 **`clientEventId`**。同一 Session 的所有命令共用此命名空间。

规则：

- 每个逻辑操作生成一个标识，在发送**前**持久化。结果不确定时，使用相同标识和相同请求体重试。
- 完全相同的重放返回原结果。相同标识配合不同请求体返回 `409`（`agent_creation_conflict`、`session_creation_conflict` 等）。
- 绝不能用新标识替换结果不确定的请求，否则可能重复执行副作用。
- 机密值不会再次返回：用户 API 密钥丢失后需轮换；`connectorKey` 丢失后需在 Connector 停用期间调用 `POST /api/v1/org/connectors/{id}/credential/rotate`，携带 `expectedCurrentVersion`。
- 创建终端用户不支持幂等键：通过 `GET /api/v1/org/users` 列表匹配 `externalId` 恢复状态。

<a id="versions-and-etags"></a>

## 版本与 ETag

- 替换模板（`PUT /api/v1/org/agent-templates/{templateId}`）时，需要在 `If-Match` 中原样提供带引号的 `ETag`。缺失返回 `428 precondition_required`；过期返回 `412 precondition_failed`。重新读取模板，重新应用变更，并使用新的 `Idempotency-Key`。
- Connector 注册信息变更（`PATCH`、`activate`、`deactivate`）在请求体中使用 `expectedConnectorVersion`；版本冲突时，重新读取 Connector，使用当前版本重新应用变更。如果 `409` 表示没有就绪的 tunnel 连接，应检查传输就绪状态与副本路由，参见 [tunnel 限制](protocols/connectors.md#multi-replica-limit)。凭据轮换使用 `expectedCurrentVersion`，即 `GET /api/v1/org/connectors/{id}/credential` 返回的 `currentVersion`。
- 回执反映历史事实，不代表当前状态，也不会提供最新 ETag 或版本。

<a id="retry-decisions"></a>

## 重试决策

- 连接失败、`429` 或 `503` 仅可对读请求或有幂等标识保护的写请求重试。遵循 `Retry-After`；否则使用带随机抖动、有上限的指数退避。
- 消息返回 `503 service_configuration_unavailable` 时没有保存任何内容。使用相同 `clientEventId` 重试是安全的，但在运维人员修复配置（`details.reason`）前仍会被拒绝。
- 校验、身份验证、授权、冲突和前提条件错误应立即呈现，并附带 `error.code`。
- 平台不会重试 Connector 调用。出现 `timeout` 或 `result_unknown` 后，设备服务器必须按 `callId` 核实状态，再判断副作用是否发生。

<a id="session-events-sse-and-recovery"></a>

## Session 事件（SSE）与恢复

- 提交（`POST …/events`）和观察（`GET …/events?stream=true`）相互独立。POST 响应不包含执行输出。
- 断连、读取缓慢或没有订阅者都不会取消 Turn。需显式发送 `{"type":"InputCancelEvent","clientEventId":"<new-id>","data":{}}` 取消。
- 重连时将最后一个 SSE `id` 作为 `cursor`。撤销密钥、停用终端用户或组织会关闭流，但不会取消 Turn。
- POST 结果不确定时，重放相同的 `clientEventId`，或读取 `GET …/interactions?clientEventId=<id>`（不带 `limit` / `cursor`）或 `GET …/interactions/{clientEventId}`。回执的 `result.status` 为 `running`、`succeeded`、`failed` 或 `interrupted`。
- 使用 `GET …/turns/{turnId}` 读取已保存的回复和工具调用；使用 `GET …/timeline` 按顺序读取文本与语音历史。EOF、空闲 Session 或命令被接受都不能证明执行成功。

<a id="pagination"></a>

## 分页

列表返回 `hasMore` 和可为空的 `nextCursor`；继续请求时，以相同凭据和过滤条件传回 `cursor`。`limit` 的范围按操作定义（通常为 1–200，默认 50）。游标是不透明且有作用域的；外部或失效游标返回 `400`。

<a id="turn-failures"></a>

## Turn 失败

`agent.session.turn.failed` 和 Turn 的 `failure` 包含 `code` 及固定说明文本：

- 配置问题：`model_provider_unconfigured`、`sandbox_unconfigured`、`drive9_unconfigured`、`drive9_disabled_for_organization`（由组织管理员在 Console 启用 Drive9）。
- 模型提供方问题：`model_provider_failed`，附带 `details.provider`（`category`、`httpStatus`、`errorType`、`errorCode`）。
- 其他问题，例如 `model_context_capacity_exceeded` 或 `runtime_error`。

工具操作只暴露固定文本，以及 `details.tool` 和 `details.category`。Connector 失败以 `invalid_arguments`、`forbidden`、`provider_unavailable`、`timeout`、`result_unknown` 或 `remote_tool_error` 呈现给模型；参见 [Connector 协议](protocols/connectors.md#tool-results-and-errors)。

<a id="diagnose-an-api-failure"></a>

## 排查 API 失败

1. 移除机密信息后，记录状态码、错误信封（`error.code`、`error.message`、`error.details`）、方法与路径、请求或关联 ID（**仅当部署返回时**）、UTC 时间戳、响应头和相关 SSE 事件。
2. 在 [openapi.yaml](../openapi.yaml) 中找到操作、响应状态和 `ErrorEnvelope` 的 `code`。
3. 对比凭据类型、目标归属、请求头、请求体 schema、ETag 或版本，以及幂等标识。
4. 对 Session 命令，读取其回执和 Turn。
5. 给出一个根因及最小修正请求或代码变更。若契约缺少错误说明，应指出缺失，仅依据实际观察到的响应判断。

| HTTP | `error.code` | 含义 |
| --- | --- | --- |
| `401` | `authentication_required` | 密钥缺失、无效、已撤销或已轮换。 |
| `403` | `auth_kind_forbidden`、`user_api_key_required` 等 | 该操作所用的凭据类型错误。 |
| `400` | `validation_error`、`idempotency_key_required`、`invalid_idempotency_key` | 请求不符合 schema 或请求头规则。 |
| `404` | `resource_not_found`、`session_not_found` 等 | 目标不存在、属于外部或被隐藏。 |
| `409` | `…_conflict`、`model_provider_unconfigured`、`realtime_not_enabled`、`realtime_connection_live` | 相同标识用于不同内容，或存在状态冲突。 |
| `412` / `428` | `precondition_failed` / `precondition_required` | `If-Match` 过期或缺失。 |
| `503` | `service_configuration_unavailable`、`…_unavailable` | 部署依赖缺失或暂时不可用。 |
