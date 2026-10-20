# TiDB Link Developer Kit

Everything you need to build on **TiDB Link** — AI agents for your application's users, reachable by text and voice and able to drive your hardware — through the **TiDB Link Customer API** (`/api/v1`).

This kit works two ways:

1. **With an AI coding assistant (recommended).** The kit is packaged as a skill: point your assistant at `SKILL.md` and ask it to integrate TiDB Link into your project. It follows the development path, treats the bundled OpenAPI contract as the source of truth, and produces runnable raw-HTTP calls — no SDK required.
2. **As documentation.** Start with `references/architecture.md` and `references/development-path.md`. Open `references/api-reference.html` in a browser for every operation, or read `references/openapi.yaml` for exact wire-level detail.

## Architecture

![TiDB Link architecture](references/diagrams/architecture.svg)

Your backend holds the keys; clients get short-lived grants; your hardware talks only to your own device server, which the platform calls as a Connector. See [architecture.md](references/architecture.md).

## Development path

![TiDB Link development path](references/diagrams/development-path.svg)

| Stage | What you do | Credential |
| --- | --- | --- |
| 0. Setup | Issue the Organization API Key; confirm the deployment is ready | Console |
| 1. Define the Agent | Publish Skills (optional); create the Agent Template | Organization API Key |
| 2. Provision users | Map your users; create End Users; issue User API Keys | Organization API Key |
| 3. Connect devices | Build your device server; register, connect and activate it as a Connector; reference it from the Template | User API Key · Console |
| 4. Text conversation | Create an Agent and Session; subscribe to SSE; send messages; render events | User API Key |
| 5. Voice conversation | Open Realtime; connect the client WebSocket; stream audio | User API Key |

Stage 3 is skipped when you have no hardware. Details: [development-path.md](references/development-path.md).

## What's inside

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Entry point for AI assistants: routing, credentials, scope, security rules. |
| `references/architecture.md` | The architecture developers need to understand. |
| `references/development-path.md` | Stages 0–5 with every request and its “done when” check. |
| `references/reliability.md` | Idempotency, ETags, SSE recovery, retries, error diagnosis. |
| `references/protocols/connectors.md` | Building a Connector (device server): Call Context, transports, errors, worked examples. |
| `references/protocols/realtime-voice.md` | The `tidb-link.realtime.v1` voice protocol. |
| `references/openapi.yaml` | The complete TiDB Link Customer API contract — the source of truth. |
| `references/api-reference.html` | The same contract rendered for humans. |
| `references/diagrams/` | Architecture and development-path diagrams (SVG). |
| `agents/openai.yaml` | Skill interface metadata. |

## Prerequisites

- **`TIDB_LINK_BASE_URL`** — the service root of your TiDB Link deployment.
- **`TIDB_LINK_ORG_KEY`** — an Organization API Key (`ti_org_…`), issued by an Organization Owner in Console.
- **`TIDB_LINK_USER_KEY`** — a User API Key (`ti_user_…`) for one End User, issued with the Organization API Key in stage 2.

Treat every key as secret material: keep it in a secret manager on your backend, never in code, logs, URLs, browsers, firmware or chat.

## Security model in one paragraph

Operation-level `security` in the OpenAPI contract is authoritative and the stored key decides scope: the Organization API Key configures and provisions but never acts as a user; a User API Key reaches only its own End User's resources; a Connector Key only authenticates your device server's channel; a realtime `connectToken` opens one voice connection for 60 seconds. Secrets are delivered once — store them immediately and rotate rather than re-request. Nothing in this kit requires pasting a secret into a conversation.
