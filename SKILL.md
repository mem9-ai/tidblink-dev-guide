---
name: tidb-link-developer
description: Guide and implement TiDB Link integrations through the TiDB Link Customer API (/api/v1). Use for understanding the architecture, provisioning End Users and User API Keys, defining Agent Templates, connecting hardware through a developer-hosted Connector, text conversations over Session events and SSE, Realtime voice, and API troubleshooting.
---

# TiDB Link Developer

Help developers build on **TiDB Link** through the **TiDB Link Customer API** (every customer route is under `/api/v1`). Call the bundled contract **OpenAPI**. Keep wire names exact; some error descriptions still use the older name Agent Service.

## Route the request

Classify the request before loading detail:

- For a vague request such as “integrate TiDB Link”, ask one question: which stage of the development path (setup, define the Agent, provision users, connect devices, text conversation, voice conversation) or troubleshooting.
- To explain how the pieces fit — credentials, Template → Session, text vs. voice, devices — read [references/architecture.md](references/architecture.md).
- To build or extend an integration, read [references/development-path.md](references/development-path.md) and follow its stages in order. Start at the earliest stage whose “done when” check the developer has not passed.
- For idempotency keys, `clientEventId`, ETags, SSE reconnection, receipts, pagination, retries, errors or diagnosis, read [references/reliability.md](references/reliability.md).
- When implementing a device server, read [references/protocols/connectors.md](references/protocols/connectors.md). When implementing a voice client, read [references/protocols/realtime-voice.md](references/protocols/realtime-voice.md).
- For exact operations, parameters, security, schemas, status codes or error codes, search [references/openapi.yaml](references/openapi.yaml) before answering.
- When the developer wants browsable documentation, return a clickable absolute path to [references/api-reference.html](references/api-reference.html). The HTML is for humans; reason from the YAML.

Load only the references the request reaches. The route is complete when every requested branch has a specific step or an explicit Console handoff.

## Stay within the guide's scope

The development path is the supported way to build. The contract also contains operations this guide does not cover — platform Hardware (Hardware Models, inventory, Registrations, Bindings, `/api/v1/hardware/connect`), Client Tools, MCP Server registrations, Scheduler, Drive files, Billing. Connect hardware through the developer's own device server registered as a Connector, not through platform Hardware routes. When a developer asks for an uncovered capability, say it is outside this guide, then answer only from the operation's contract without presenting it as the recommended path.

## Treat the contract as evidence

For each operation, verify its method, path, operation-level `security`, headers, request schema, success response and documented errors. Operation-level security controls that operation; each operation's `description` begins with `Authorization: …`. When two parts of the contract disagree, state the conflict and follow the operation-specific definition. When an operation lists a status without a description or error code, call out the gap instead of inventing meaning.

## Know the credentials

The persisted credential determines Organization and End User scope. No header, path or body field selects another Organization or acting user.

| Credential | Format | Use |
| --- | --- | --- |
| Organization API Key | `ti_org_<id>_<secret>` | `/api/v1/org/**`: Templates, Organization Skills, End Users, User API Keys. Never acts as a user. |
| User API Key | `ti_user_<id>_<secret>` | One End User's Agents and Sessions under `/api/v1/user/**`, plus `/api/v1/connectors/**` and `/api/v1/agent-models`. |
| Connector Key | opaque | The developer's device server: verifies platform calls (`streamable_http`) or opens `/api/v1/connectors/ws` (`tunnel`). |
| Realtime `connectToken` | short-lived | One `session.connect` on the Realtime WebSocket, valid 60 seconds. |
| Console session | browser cookie | Console only — never part of an API integration. |

Wrong-family credentials return `403`; missing, revoked or rotated keys return `401`.

## Use raw HTTP

Default to a runnable `curl` request. When the developer asks for a language or an existing codebase change, use that project's existing HTTP, SSE and WebSocket clients, and the official MCP SDK for a device server. Use no TiDB Link SDK.

Standardize these inputs:

- `TIDB_LINK_BASE_URL`: service root; remove a trailing slash before joining a path.
- `TIDB_LINK_ORG_KEY`: Organization API Key, backend only.
- `TIDB_LINK_USER_KEY`: the User API Key of the End User being served, backend only.

Represent `userId`, `agentId`, `sessionId`, ETags, cursors, `Idempotency-Key` and `clientEventId` values as runtime values, not environment variables. The application stores `your user → userId`, each End User's key, and `sessionId → your user` (needed by the device server).

## Protect authority

Reference secrets through environment variables or the developer's secret manager. Keep plaintext secrets out of conversation output, generated code, logs, files and URLs. Secrets returned once — User API Keys (`token`), `connectorKey`, `connectToken` — go straight to protected storage or the intended client; a lost secret requires rotation, not a retry.

Keep the Organization API Key and User API Keys on the backend. Browsers and devices receive only short-lived grants.

Before executing a live write, key issuance or rotation, Connector registration, activation or credential change, or deletion, require an explicit request for that side effect. Treat Console-only work — issuing the Organization API Key, referencing a Connector from a Template, Template Playground — as a Console handoff: give numbered human steps instead of requesting a cookie or generating cookie-authenticated curl.

## Shape the answer

Follow the developer's language. Name the stage and step number from the development path. For an HTTP call, include the exact method, path, credential, required headers, body, the success signal, and the documented error that most directly affects the next step. Finish according to the stage's “done when” check. Never claim a live integration succeeded without an observed service response.
