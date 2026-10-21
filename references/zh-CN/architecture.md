# 架构

[English](../architecture.md) | 简体中文

> 翻译基线：英文文档提交 [`a152eb4`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。接口定义以共用 OpenAPI 为准。

发送第一个请求前，需要了解谁持有哪些凭据、模板如何变成会话，以及文本、语音和设备如何与智能体交互。

![TiDB Link 架构](diagrams/architecture.svg)

<a id="three-columns"></a>

## 三个部分

**你的系统**：由你构建和运维的所有组件。

- **控制台（Console，手动操作）**：组织所有者在此签发组织 API 密钥。关联 Connector（阶段 3）还需要有模板编辑权限的 Console 账号；终端用户不等于 Console 成员。
- **应用后端**：唯一存放长期密钥的位置。保存组织 API 密钥和各终端用户的用户 API 密钥，将应用用户映射到 `userId`，记录每个 `sessionId` 属于哪个应用用户，发送消息、向客户端转发 SSE 事件，并获取语音 `connectToken`。
- **客户端（浏览器、应用或设备）**：不持有 API 密钥。文本请求经过你的后端；语音通过短期 `connectToken` 建立 WebSocket 连接。
- **设备服务器（你的 Connector）**：由你运行的 MCP 服务器。硬件使用你自己的协议连接它，绝不直接连接 TiDB Link。它也可以和应用后端是同一个服务。

**TiDB Link API**：所有客户接口路径都位于 `/api/v1` 下，可访问的范围由凭据决定。

| 入口 | 凭据 | 用途 |
| --- | --- | --- |
| `/api/v1/org/**` | 组织 API 密钥（`ti_org_…`） | 模板、终端用户、用户 API 密钥、Connector 管理 |
| `/api/v1/user/**`、`/api/v1/agent-models`、`/api/v1/realtime-models` | 用户 API 密钥（`ti_user_…`） | Agent、Session、消息命令、SSE 事件、开启语音、模型目录 |
| Realtime WebSocket（`tidb-link.realtime.v1`） | 一次性 `connectToken` | 双向音频 |
| Connector 传输通道 | Connector Key（`connectorKey`） | 平台调用你的设备服务器（`streamable_http`），或由服务器连接 `/api/v1/connectors/ws`（`tunnel`） |

**TiDB Link 平台**：以下对象位于同一个组织（Organization）内。

- **智能体模板（Agent Template，组织内共享）**：包含指令、Sandbox、Skill、实时语音语言和 Connector 引用。保存立即生效，但仅影响之后创建的 Session。
- **End User → Agent → Session → Turn（终端用户私有）**：
  - **终端用户（End User）**是组织内对应你的应用用户的对象，不是 Console 账号。
  - **智能体（Agent）**是一个终端用户与一个模板的关联。
  - **会话（Session）**是私有对话，创建时冻结模板内容，由文本和语音共用。
  - **执行轮次（Turn）**是一次执行，其事件会持久化并通过 SSE 传递。
- **Full Agent（LLM）**：使用 Session 冻结的配置执行 Turn，并调用已启用的工具，包括 Connector 工具。
- **实时连接（Realtime Connection）**：关联到已有 Session。Realtime Model 负责听和说；无法自行完成的工作会作为普通 Turn 委派给 Full Agent。转写文本会加入 Session 时间线。
- **连接器（Connector，开发者托管的工具）**：使用组织 API 密钥注册并激活；激活时发现并冻结工具目录。每次调用都携带调用上下文（Call Context）：`callId`、`sessionId`、`organizationId`、`deadline`、`attempt`。

<a id="rules-that-follow-from-the-architecture"></a>

## 由架构决定的规则

1. **凭据决定权限范围。** 组织 API 密钥负责资源开通和配置，不能以用户身份操作。用户 API 密钥只能访问其所属终端用户的资源。客户端仅获得短期授权。路径中的 ID 用于选择目标，不会授予访问权限。
2. **Session 冻结配置。** Session 始终使用创建时的模板内容。修改模板后，包括新增 Connector 引用，需创建新 Session 才能看到变化。
3. **发送与观察相互独立。** `POST …/events` 返回回执；执行结果只能从 SSE 流和 Turn 历史获取。关闭流不会取消 Turn。
4. **文本与语音共用一个 Session。** 语音不会创建 Session；语音委派的工作会成为普通 Turn。
5. **设备由你管理。** 平台不了解你的设备。设备服务器负责维护 `sessionId → 应用用户 → 设备` 映射，依据该映射授权每次调用，并按 `callId` 对副作用去重。平台不会重试调用。

接下来阅读[接入流程](development-path.md)。
