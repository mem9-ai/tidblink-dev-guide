# 连接器（Connector）

[English](../../protocols/connectors.md) | 简体中文

> 翻译基线：英文文档提交 [`a152eb4`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。接口定义以共用 OpenAPI 为准。

> 改编自 TiDB Link 文档，并已按[上游版本说明](../upstream.md)中记录的契约和实现核对。

**Connector** 用于注册你运行的工具服务器，让基于模板创建的 Agent 调用其工具。与普通 MCP Server 注册不同，每次 Connector `tools/call` 都携带[调用上下文（Call Context）](#call-context)：服务器由此得知当前服务的 Session，并将其映射到你自己的用户记录。Connector 属于组织，使用**组织 API 密钥**管理，参见[准备阶段](../development-path.md#stage-0-setup)。用户 API 密钥不能管理 Connector（`403`）。旧的 `/api/v1/connectors` 管理路由已移除（`404`）；只有使用 Connector Key 的 WebSocket 仍位于 `/api/v1/connectors/ws`。

两种传输方式覆盖不同的网络可达方向：

| 传输方式 | 连接方向 | 适用情况 |
| --- | --- | --- |
| `streamable_http` | 平台调用你的公网 HTTPS 端点。 | 服务器有公网地址，或位于公网网关之后（常见于 serverless）。 |
| `tunnel` | 服务器通过持久 WebSocket 主动连接平台。 | 服务器没有公网地址，例如位于 NAT 后、企业内网或笔记本电脑上。 |

两种方式都使用 MCP，角色固定：平台始终是 MCP 客户端，你的 Connector 始终是 MCP 服务器。使用官方 MCP SDK 实现；[完整示例](#worked-examples)展示了两种传输方式的端到端接入。

<a id="register-and-activate"></a>

## 注册与激活

使用组织 API 密钥注册。`streamable_http` Connector 必须提供 `endpointUrl`；`tunnel` 不传该字段：

```bash
curl -X POST "$TIDB_LINK_BASE_URL/api/v1/org/connectors" \
  -H "Authorization: Bearer $TIDB_LINK_ORG_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Orders","transport":"streamable_http","endpointUrl":"https://tools.example.com/mcp"}'
```

- `endpointUrl` 必须使用 HTTPS，不能包含凭据或片段。平台每次请求（包括目录发现）都会携带 `Authorization: Bearer <connectorKey>`；服务器开始工作前必须验证它。
- `201` 响应返回 Connector 记录及其 `connectorKey`，密钥**只返回一次**。之后任何读取都不会再次返回密钥；收到时立即保存，丢失后轮换。
- `displayName` 在组织内唯一，重复返回 `409`。

激活会发现工具目录并将其冻结，供后续使用：

```bash
curl -X POST "$TIDB_LINK_BASE_URL/api/v1/org/connectors/<connectorId>/activate" \
  -H "Authorization: Bearer $TIDB_LINK_ORG_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"expectedConnectorVersion":1}'
```

发现通过声明的传输方式列出工具。对 `tunnel`，会使用第一个就绪的 tunnel 连接，所以激活前应先连接一个实例；没有就绪连接时以 `409` 拒绝激活。目录最多包含 200 个工具，每个输入 schema 最多 64 KiB。`expectedConnectorVersion` 用于注册信息变更的乐观并发控制：`PATCH`、`activate` 和 `deactivate` 都要求当前版本，并会递增版本。版本冲突时，重新读取 Connector，按当前版本重新应用变更。若 `409` 表示没有就绪的 tunnel 连接，必须先修复就绪状态或路由，修改版本号无法解决。凭据轮换使用凭据自己的计数器，见下文。

Connector **激活期间**，编辑（`PATCH`）和所有凭据变更都会被以 `409` 拒绝，避免运行中的 Agent 看到只修改了一半的注册信息。重新配置前先停用：

```bash
curl -X POST "$TIDB_LINK_BASE_URL/api/v1/org/connectors/<connectorId>/deactivate" \
  -H "Authorization: Bearer $TIDB_LINK_ORG_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"expectedConnectorVersion":2}'
```

停用会使 Connector 工具下线：重新激活之前已冻结配置的执行，其工具调用会以 `provider_unavailable` 失败；重新激活后，新的 Turn 冻结当前注册信息。

在 Console 模板编辑器的 **MCP & Connectors** 中引用 Connector，按[步骤 12](../development-path.md#stage-3-connect-devices)操作。这要求 Console 账号有同一组织的模板编辑权限，MSP 开通流程不会自动创建该成员关系。

内部引用格式为 `tools.mcp: [{serverId: "conn_…"}]`，但组织模板 API **不接受**它。该 API 对 `content.tools` 返回 `400 validation_error`，读取时隐藏该字段，`PUT` 时保留已有的 Console 管理引用。不要把此内部结构复制进组织 API 请求。

只能引用同一组织内已激活的 Connector；模板保存时引用其他对象会返回 `409 agent_template_dependency_unavailable`。模型使用 `mcp_<server>__<tool>` 调用工具，两部分来自发现的服务器名和工具名（转为小写，连续非字母数字字符合并成 `_`），与 MCP Server 工具共用相同的命名分区。

<a id="call-context"></a>

## 调用上下文（Call Context）

两种传输方式中的每次 Connector `tools/call`，都会在 `params._meta` 中携带以下内容：

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "list_orders",
    "arguments": { "status": "open" },
    "_meta": {
      "tidb-link/context": {
        "callId": "op_01JAB…",
        "sessionId": "sess_…",
        "organizationId": "org_…",
        "deadline": "2026-10-17T08:30:05.123Z",
        "attempt": 1
      }
    }
  }
}
```

| 字段 | 含义 |
| --- | --- |
| `callId` | 平台为此次调用生成的 Operation ID，全局唯一。将其作为幂等键，对副作用去重。 |
| `sessionId` | 调用方 Agent 正在服务的 Session。将其映射到自己的用户或业务记录。 |
| `organizationId` | 同时拥有该 Session 和 Connector 的组织。 |
| `deadline` | 平台停止等待的 ISO 8601 时间点（当前执行策略为调用发出后 300 秒）。过期后应停止工作。 |
| `attempt` | 始终为 `1`：平台不会自动重试调用，因此不会因平台重试而重复执行已产生的副作用。 |

调用上下文只能由平台写入：工具结果中相同的 `_meta` 键会被丢弃，不能从下游伪造。没有 `endUserId` 字段，工具 schema 也不能要求模型提供身份字段。平台在发送调用前，按激活时冻结的 schema 校验模型参数；身份信息不经由模型传递。

<a id="authorize-from-your-own-session-mapping--hard-requirement"></a>

### 必须依据自己的 Session 映射授权

调用对应的终端用户身份必须来自**你自己的 `sessionId` 映射**，该映射由后端创建 Session 时记录，绝不能来自调用中未经验证的字段。`sessionId` 和 `organizationId` 标识你的哪个平台 Session 正在被服务；具体对应哪个应用用户由自己的记录决定。模型可以影响的内容，例如参数和自由文本，都不能作为身份声明。这与 MCP 规范的服务器端授权规则一致。

<a id="tool-results-and-errors"></a>

## 工具结果与错误

返回普通 MCP 结果。内容仅限 `text` 块和 `resource_link` 引用：平台的结果投影会拒绝图像、音频和嵌入资源，也会拒绝超过限制的结果（文本 1 MiB、10,000 个内容条目、32 层结构）。被拒绝的结果会作为 `result_*` 或 `unsupported_binary_result` 工具错误呈现给模型，因此应修正工具。

业务失败，例如订单不存在或付款被拒绝，应作为普通结果返回，设置 `isError: true` 并附说明文字：

```json
{
  "content": [
    { "type": "text", "text": "Order 4711 has already shipped and cannot be cancelled." }
  ],
  "isError": true
}
```

模型会将你的文本作为工具错误（`remote_tool_error`）接收，并可解释失败或修正参数后重试。

发送调用前或调用过程中的失败会作为结构化工具错误呈现给模型：

| 错误码 | 含义 | 服务器是否收到调用？ |
| --- | --- | --- |
| `invalid_arguments` | 模型参数未通过冻结的 schema 校验。 | 否，未发出调用。 |
| `forbidden` | Session 与 Connector 所属组织不一致；平台还会发出安全警报。 | 否。 |
| `provider_unavailable` | 端点不可达、没有就绪的 tunnel 实例、实时目录与冻结目录不一致，或单个 Connector 的并发额度已满。不排队，立即失败。 | 否。 |
| `timeout` | 结果到达前已超过调用的 `deadline`。 | 可能，开始发送后就无法确定。 |
| `result_unknown` | 已开始发送调用，结果在传输中丢失。 | 可能，无法确定。 |
| `remote_tool_error` | 工具返回 `isError: true`，模型看到你的错误文本。 | 是。 |

平台不会自动重试。发生 `timeout` 或 `result_unknown` 后，先按 `callId` 核实结果，再判断副作用是否发生；有副作用的工具必须围绕该标识实现幂等。

<a id="credential-rotation-and-revocation"></a>

## 凭据轮换与撤销

`GET /api/v1/org/connectors/<connectorId>/credential` 只返回凭据元数据（`credentialBindingId`、`currentVersion`、`active`），不返回密钥。

- **轮换**：`POST …/credential/rotate`，请求体为 `{"expectedCurrentVersion":<n>}`，其中 `<n>` 来自凭据 `GET` 的 `currentVersion`。新密钥只返回一次，`currentVersion` 随之递增，旧密钥立即失效。
- **撤销**：`DELETE …/credential` 返回 `204`，即使凭据不存在也如此。
- **重新签发**：没有激活凭据时，`PUT …/credential` 配合 `{}` 返回新密钥，且只返回一次，用于撤销后的恢复。存在激活凭据时返回 `409`，应改用轮换。

每次凭据变更都要求 Connector **已停用**；若仍有运行中的 Turn 引用它，也会返回 `409`，避免轮换或撤销使正在进行的调用失去凭据。轮换不会将凭据重新绑定到变更后的端点：编辑 `endpointUrl` 后，激活前必须撤销并重新签发凭据。

`tunnel` Connector 在停用期间仍接受 tunnel 连接，因此可以避免部署竞态：先停用、轮换，使用新密钥启动实例，再激活；目录发现会通过就绪连接进行。

<a id="tunnel-operations"></a>

## Tunnel 操作

作为 WebSocket 客户端建立 tunnel：

```
wss://<your-agent-service-host>/api/v1/connectors/ws
Sec-WebSocket-Protocol: tidb-link.connector.v1
Authorization: Bearer <connectorKey>
X-Ti-Connector-Instance: <your-instance-id>
```

实例 ID 是你定义的非空字符串，最多 128 字节，不含控制字符，用于标识服务器实例。在该连接上，平台是 MCP 客户端：它发起 `initialize`，随后发起 `tools/list` 和 `tools/call`，由 SDK 服务器响应。每个文本帧必须恰好包含一条原始 JSON-RPC 2.0 消息，不加外层信封，不支持批处理；二进制帧属于协议错误。

你的服务器一侧只能主动发送**通知**：

- `notifications/tools/list_changed` 请求平台重新发现目录：平台通过就绪连接重新列出工具，并在 Connector 激活期间持久化刷新后的目录，供新 Turn 使用。
- `notifications/progress` 会被接受，但不会延长已声明的调用截止时间。

你的服务器主动发起请求会导致连接关闭。关闭码如下：

| 关闭码 | 含义 |
| --- | --- |
| `1000` | 正常关闭。 |
| `1001` | 心跳超时，连续两次未响应平台 ping。 |
| `4001` | 身份验证失败：密钥缺失、格式错误、未知、已撤销或过期。 |
| `4003` | 通过身份验证的 Connector 不是 `tunnel` Connector。 |
| `4008` | 使用相同 `X-Ti-Connector-Instance` 重连的实例接管了连接。 |
| `4009` | 协议错误：帧无效，或服务器一侧主动发起请求。 |

平台每 20 秒发送 ping，连续两次未收到 pong 后断开。`ws` 库会自动响应，因此正常进程无需额外心跳代码。每次关闭后都应退避重连。`4008` 表示另一个进程使用相同实例 ID 连接，通常是有意启动的第二次部署；应退避，不要紧密循环争抢连接。升级前的拒绝是普通 HTTP 响应：升级请求格式错误为 `400`，非 WebSocket 请求为 `426`，副本达到连接准入上限为 `429`，网关停止中为 `503`。

<a id="multi-replica-limit"></a>

### 多副本限制

Tunnel 连接**仅对接受它的平台副本可见**。激活和工具调用只能使用执行该工作副本上的就绪连接。相同实例重连也只会替换该副本内的旧连接。

多个 API 副本的部署中，仅有一个已连接的设备服务器实例并不足够：激活请求路由到其他副本时，可能返回 `409` 和 `Connector has no ready tunnel connection`；工具调用也可能以 `provider_unavailable` 失败。腾讯云验证中，tunnel 持续连接时，10 次激活尝试出现 3 次失败；由于缺少 Console 权限，无法关联模板，因此未测试工具调用。该比例只是一次观察结果，不是平台保证。

本指南建议多副本部署优先使用 **`streamable_http`**。必须使用 tunnel 时，请运维人员提供单副本测试环境，或确保目录发现和实际工具执行都到达持有就绪连接的副本。仅有 HTTP 会话亲和性不能保证 worker/Turn 路由。建立多个随机负载均衡的连接，或不断重试激活直到成功，都不能保证可靠性。参见固定版本的[运行时归属清单](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/docs/architecture/multi-replica-runtime-ownership.md#pod-local-state)。

执行副本没有就绪连接时，调用立即失败，平台侧不排队。

<a id="worked-examples"></a>

## 完整示例

两个示例都使用官方 MCP TypeScript SDK v2（`@modelcontextprotocol/server`），实现一个依据调用上下文授权的 `list_orders` 工具。在 SDK 中，工具处理器上下文通过 `ctx.mcpReq._meta` 提供请求的 `_meta`。

在 Node.js 项目中安装 SDK 和示例依赖：

```bash
npm install @modelcontextprotocol/server@2.3.1 @modelcontextprotocol/node@2.1.1 ws zod
npm install --save-dev typescript tsx @types/node @types/ws
```

将选用的示例保存为 `.ts` 文件，通过密钥管理系统或环境变量提供 `CONNECTOR_KEY` 后，运行 `npx tsx <file>.ts`。这些示例是集成骨架：需要基于你的后端记录实现 `yourAccounts.lookupBySessionId` 和 `yourOrders.listRecent`。tunnel 示例复用 HTTP 示例的 `buildServer`；使用共享服务器定义，但不要启动 HTTP 监听器。在 HTTP 示例的 8080 端口前配置 TLS 终止，以提供所需的公网 HTTPS 端点。

<a id="streamable_http"></a>

### streamable_http

通过 SDK Node 适配器（`@modelcontextprotocol/node`）在 `node:http` 上运行无状态服务器；将请求交给 MCP 前先校验 Connector Key：

```ts
import { createServer } from 'node:http';
import { McpServer } from '@modelcontextprotocol/server';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';
import { z } from 'zod';

const CONNECTOR_KEY = process.env.CONNECTOR_KEY!;
const CALL_CONTEXT_KEY = 'tidb-link/context';

interface CallContext {
  callId: string;
  sessionId: string;
  organizationId: string;
  deadline: string;
  attempt: number;
}

const callContext = (meta: unknown): CallContext => {
  const context = (meta as Record<string, unknown> | undefined)?.[CALL_CONTEXT_KEY];
  if (!context) throw new Error('Missing Call Context — is this request from the platform?');
  return context as CallContext;
};

const buildServer = (): McpServer => {
  const server = new McpServer({ name: 'orders', version: '1.0.0' });
  server.registerTool(
    'list_orders',
    {
      description: 'List recent orders for the calling user.',
      inputSchema: z.object({ status: z.string().optional() }),
    },
    async (args, ctx) => {
      const { sessionId, callId, deadline } = callContext(ctx.mcpReq._meta);
      // Hard rule: your own records, never call fields, decide who this is.
      const account = await yourAccounts.lookupBySessionId(sessionId);
      if (!account) {
        return { content: [{ type: 'text', text: 'Unknown session.' }], isError: true };
      }
      const orders = await yourOrders.listRecent(account, {
        status: args.status,
        idempotencyKey: callId,
        notAfter: new Date(deadline),
      });
      return { content: [{ type: 'text', text: JSON.stringify(orders) }] };
    },
  );
  return server;
};

createServer(async (req, res) => {
  if (req.headers.authorization !== `Bearer ${CONNECTOR_KEY}`) {
    res.writeHead(401).end();
    return;
  }
  // Stateless: one server and transport per request, no session tracking.
  const server = buildServer();
  const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined });
  res.on('close', () => {
    void transport.close();
    void server.close();
  });
  await server.connect(transport);
  await transport.handleRequest(req, res);
}).listen(8080);
```

<a id="tunnel"></a>

### tunnel

同一个 MCP 服务器，通过自定义 `Transport` 接入服务器主动建立的 WebSocket。平台发送 ping，`ws` 自动回复 pong：

```ts
import { McpServer, type JSONRPCMessage, type Transport } from '@modelcontextprotocol/server';
import WebSocket from 'ws';

class TunnelTransport implements Transport {
  onclose?: () => void;
  onerror?: (error: Error) => void;
  onmessage?: (message: JSONRPCMessage) => void;

  constructor(private readonly socket: WebSocket) {}

  start(): Promise<void> {
    this.socket.on('message', (data, binary) => {
      if (binary) return; // binary frames are a protocol error platform-side; never send them
      this.onmessage?.(JSON.parse(data.toString('utf8')));
    });
    this.socket.on('close', () => this.onclose?.());
    this.socket.on('error', (error) => this.onerror?.(error));
    return Promise.resolve();
  }

  send(message: JSONRPCMessage): Promise<void> {
    return new Promise((resolve, reject) =>
      this.socket.send(JSON.stringify(message), (error) => (error ? reject(error) : resolve())),
    );
  }

  async close(): Promise<void> {
    this.socket.close();
  }
}

const connect = (): void => {
  const ws = new WebSocket(
    'wss://<your-agent-service-host>/api/v1/connectors/ws',
    'tidb-link.connector.v1', // the subprotocol is required
    {
      headers: {
        authorization: `Bearer ${process.env.CONNECTOR_KEY}`,
        'x-ti-connector-instance': process.env.INSTANCE_ID ?? 'instance-1',
      },
    },
  );
  ws.on('open', async () => {
    const server = buildServer(); // the same McpServer as above
    await server.connect(new TunnelTransport(ws));
  });
  ws.on('close', (code) => {
    // 4001: check the key. 4008: another same-named instance took over — back off.
    setTimeout(connect, 1000 + Math.random() * 4000);
  });
};

connect();
```

工具变化时调用 `server.sendToolListChanged()`，平台会通过就绪连接重新发现目录。

<a id="names-on-the-wire"></a>

## 协议标识

契约始终使用实现中的平台协议命名空间：调用上下文键为 `tidb-link/context`，tunnel 子协议为 `tidb-link.connector.v1`，实例请求头为 `X-Ti-Connector-Instance`。三者都必须原样使用。

管理路由的完整请求与响应 schema 见 [API 参考](../../openapi.yaml)；其中也将 tunnel 端点记录为 `GET /api/v1/connectors/ws`。
