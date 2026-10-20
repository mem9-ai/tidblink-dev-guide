# Connectors

> Bundled from the TiDB Link documentation (`mem9-ai/agent-stack` `main` @ `4734a32`, `apps/site/src/content/docs/docs/guides/`). Links point into this kit.

A **Connector** registers a tool server you operate, so Agents built on your Templates can call its tools. Unlike a plain MCP Server registration, every Connector `tools/call` carries a per-call [Call Context](#call-context): your server learns which Session it serves and maps that Session to your own user records. Connectors belong to your Organization and are managed with a User API Key of an active End User; see [authentication](../development-path.md#stage-2-provision-users).

Two transports cover both reachability directions:

| Transport | Who dials whom | Use when |
| --- | --- | --- |
| `streamable_http` | The platform calls your public HTTPS endpoint. | Your server has a public address, or sits behind a public gateway (typical serverless). |
| `tunnel` | Your server dials out to the platform over a persistent WebSocket. | Your server has no public address: behind NAT, inside a corporate network, on a laptop. |

Both transports speak MCP with the roles fixed: the platform is always the MCP client, your Connector is always the MCP server. Implement yours with the official MCP SDK — the [worked examples](#worked-examples) show each transport end to end.

## Register and activate

Register with a User API Key. A `streamable_http` Connector requires `endpointUrl`; a `tunnel` Connector takes none:

```bash
curl -X POST https://<your-agent-service-host>/api/v1/connectors \
  -H "Authorization: Bearer $USER_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"Orders","transport":"streamable_http","endpointUrl":"https://tools.example.com/mcp"}'
```

- The `endpointUrl` must be HTTPS without credentials or a fragment. The platform presents `Authorization: Bearer <connectorKey>` on every request to it, including catalog discovery — verify it on your server before doing any work.
- The `201` response returns the Connector record and its `connectorKey` **exactly once**. No read ever returns it again; store it on receipt and rotate if lost.
- `displayName` is unique within the Organization; a duplicate returns `409`.

Activation discovers your tool catalog and freezes it for use:

```bash
curl -X POST https://<your-agent-service-host>/api/v1/connectors/<connectorId>/activate \
  -H "Authorization: Bearer $USER_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"expectedConnectorVersion":1}'
```

Discovery lists your tools over the declared transport — for `tunnel`, over your first ready tunnel connection, so connect an instance before activating; with none ready, activation is refused with `409`. A catalog holds at most 200 tools and each input schema at most 64 KiB. `expectedConnectorVersion` is optimistic concurrency: every mutation requires the current version and bumps it. After a `409`, read the Connector again and retry with its current version.

While a Connector is **active**, edits (`PATCH`) and every credential mutation are refused with `409`, so live Agents never observe a half-mutated registration. Deactivate to reconfigure:

```bash
curl -X POST https://<your-agent-service-host>/api/v1/connectors/<connectorId>/deactivate \
  -H "Authorization: Bearer $USER_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"expectedConnectorVersion":2}'
```

Deactivation takes the Connector's tools offline: dispatches against runs frozen before re-activation fail with `provider_unavailable`, and new Turns freeze the current registration after you re-activate.

Reference the Connector from a Template exactly like an MCP Server registration, through `tools.mcp`:

```json
{ "tools": { "mcp": [{ "serverId": "conn_…" }] } }
```

Only active Connectors of the same Organization can be referenced; a Template save that names anything else fails with `409 agent_template_dependency_unavailable`. The model calls each tool as `mcp_<server>__<tool>`, both parts derived from the discovered server and tool names (lowercased, non-alphanumerics collapsed to `_`) — the same naming partition as MCP Server tools.

## Call Context

Every Connector `tools/call` — on both transports — carries this block in `params._meta`:

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

| Field | Meaning |
| --- | --- |
| `callId` | The platform's Operation id for this call — globally unique. Use it as your idempotency key: deduplicate effects by it. |
| `sessionId` | The Session the calling Agent is serving. Map it to your own user or business records. |
| `organizationId` | The Organization that owns both the Session and the Connector. |
| `deadline` | ISO 8601 instant when the platform stops waiting (300 seconds from dispatch under the current execution policy). Abandon work after it passes. |
| `attempt` | Always `1`: the platform never retries a call automatically, so a side effect you applied is never re-executed. |

The Call Context is platform-written only: the same `_meta` key in your results is dropped, so it cannot be forged downstream. There is no `endUserId`, and tool schemas must not ask the model for identity fields — the platform validates the model's arguments against the schema it froze at activation before dispatch, and identity never passes through the model.

### Authorize from your own session mapping — hard requirement

Derive the end-user identity for a call from **your own `sessionId` mapping**, recorded by your backend when it created that Session — never from unverified fields in the call. `sessionId` and `organizationId` tell you which of your platform Sessions this is; your own records say which of your users it serves. Anything the model could influence — arguments, free text — is not an identity assertion. This mirrors the MCP specification's server-side authorization rule.

## Tool results and errors

Return ordinary MCP results. Keep content to `text` blocks and `resource_link` references: image, audio and embedded-resource payloads are rejected by the platform's result projection, as are results over the limits (1 MiB of text, 10,000 content entries, 32 levels of structure). A rejected result reaches the model as a `result_*` or `unsupported_binary_result` tool error, so fix the tool rather than the Agent.

Report a business failure — unknown order, declined payment — as a normal result with `isError: true` and explanatory text:

```json
{
  "content": [
    { "type": "text", "text": "Order 4711 has already shipped and cannot be cancelled." }
  ],
  "isError": true
}
```

The model receives your text as the tool error (`remote_tool_error`) and can explain the failure or retry with corrected arguments.

Failures before or around dispatch reach the model as structured tool errors:

| Code | Meaning | Did your server see the call? |
| --- | --- | --- |
| `invalid_arguments` | The model's arguments failed the frozen schema. | No — never dispatched. |
| `forbidden` | The Session's Organization did not match the Connector's; the platform also raises a security alert. | No. |
| `provider_unavailable` | Your endpoint was unreachable, no ready tunnel instance existed, the live catalog no longer matched the frozen one, or the per-Connector concurrency bound was full. Nothing is queued; the failure is immediate. | No. |
| `timeout` | The call's `deadline` passed before a result arrived. | Possibly — indeterminate once dispatch started. |
| `result_unknown` | Dispatch started and the result was lost in transit. | Possibly — indeterminate. |
| `remote_tool_error` | Your tool returned `isError: true`; the model sees your error text. | Yes. |

The platform never retries automatically. After `timeout` or `result_unknown`, reconcile by `callId` before assuming the effect did not happen — and make side-effecting tools idempotent around it.

## Credential rotation and revocation

`GET /api/v1/connectors/<connectorId>/credential` returns credential metadata only (`credentialBindingId`, `currentVersion`, `active`) — never the key.

- **Rotate**: `POST …/credential/rotate` with `{"expectedCurrentVersion":<n>}` returns the new key exactly once and advances `currentVersion`. The old key stops working immediately.
- **Revoke**: `DELETE …/credential` returns `204`, including when no credential exists.
- **Reissue**: `PUT …/credential` with `{}` returns a fresh key exactly once when none is active — the path back from revocation. It is `409` while an active credential exists; rotate instead.

Every credential mutation requires the Connector **inactive** and is additionally refused with `409` while a running Turn still references it, so a rotated or revoked key can never strand a live dispatch. Rotation never re-binds the credential to a changed endpoint: after editing `endpointUrl`, revoke and reissue before activating.

A `tunnel` Connector accepts tunnel connections while inactive, so you can rotate without a deployment race: deactivate, rotate, start your instances with the new key, then activate — discovery runs over a ready connection.

## Tunnel operations

Open the tunnel as a WebSocket client:

```
wss://<your-agent-service-host>/api/v1/connectors/ws
Sec-WebSocket-Protocol: tidb-link.connector.v1
Authorization: Bearer <connectorKey>
X-Ti-Connector-Instance: <your-instance-id>
```

The instance id is your own non-empty string of at most 128 bytes without control characters, naming this instance of your server. On the socket the platform is the MCP client: it drives `initialize`, then `tools/list` and `tools/call`, and your SDK server answers. Each text frame carries exactly one raw JSON-RPC 2.0 message — no envelope, no batching; binary frames are a protocol error.

Your side of the socket may send **notifications only**:

- `notifications/tools/list_changed` asks the platform to rediscover your catalog: the platform re-lists your tools over a ready connection and persists the refreshed catalog for new Turns while the Connector is active.
- `notifications/progress` is accepted but never extends the announced call deadline.

Requests initiated by your side close the socket. The close codes:

| Code   | Meaning                                                                          |
| ------ | -------------------------------------------------------------------------------- |
| `1000` | Normal closure.                                                                  |
| `1001` | Heartbeat timeout — two consecutive platform pings went unanswered.              |
| `4001` | Authentication failed: the key is missing, malformed, unknown, revoked or stale. |
| `4003` | The authenticated Connector is not a `tunnel` Connector.                         |
| `4008` | A reconnecting instance with the same `X-Ti-Connector-Instance` took over.       |
| `4009` | Protocol error: invalid frames, or a request from your side.                     |

The platform pings every 20 seconds and disconnects after two missed pongs; the `ws` library answers pings automatically, so a healthy process needs no heartbeat code. Reconnect with backoff after any close. A `4008` means another process connected with your instance id — usually a deliberate second deployment; back off rather than fighting it in a tight loop. Refusals before the upgrade are plain HTTP: `400` for a malformed upgrade, `426` for a non-WebSocket request, `429` while the replica is at its admission limit, `503` while the gateway is stopping.

Run as many instances as you need: calls ride any ready connection, and a reconnecting instance atomically replaces its own stale connection, so deploys and crashes converge in seconds. With **no** ready instance, calls fail immediately with `provider_unavailable` — nothing is queued platform-side.

## Worked examples

Both examples use the official MCP TypeScript SDK v2 (`@modelcontextprotocol/server`) and implement one tool, `list_orders`, that authorizes from the Call Context. In the SDK, the tool handler's context carries the request's `_meta` at `ctx.mcpReq._meta`.

### streamable_http

A stateless server on `node:http` via the SDK's Node adapter (`@modelcontextprotocol/node`), checking the Connector Key before handing the request to MCP:

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

### tunnel

The same MCP server, attached to a custom `Transport` over one WebSocket the server dials out. The platform pings; `ws` pongs for you:

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

When your tools change, call `server.sendToolListChanged()` and the platform rediscovers the catalog over a ready connection.

## Names on the wire

This contract uses the platform's protocol namespace throughout, exactly as implemented: the Call Context key is `tidb-link/context`, the tunnel subprotocol is `tidb-link.connector.v1`, and the instance header is `X-Ti-Connector-Instance`. Use all three verbatim.

Full request and response schemas for the management routes live in the [API reference](../openapi.yaml); the tunnel endpoint is documented there as `GET /api/v1/connectors/ws`.
