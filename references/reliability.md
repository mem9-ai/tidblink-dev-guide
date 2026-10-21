# Reliability and troubleshooting

English | [简体中文](zh-CN/reliability.md)

Rules for the requests in the [development path](development-path.md). Apply only those relevant to the selected OpenAPI operation.

## Prepare a request

Before constructing or retrying a request, verify:

1. The operation's `security` admits your credential: `OrganizationApiKey` for `/api/v1/org/**`, `UserApiKey` for the End User routes. The wrong credential family returns `403`; a missing, revoked or rotated key returns `401`.
2. Required `Idempotency-Key`, `If-Match`, `Accept` and `Content-Length` headers are present exactly as the operation declares.
3. The body matches the referenced schema. Most schemas reject unknown fields with `400 validation_error`.
4. Path IDs belong to your Organization and, for User API Key routes, to that End User. Foreign, hidden and missing targets return the same `404`.

## Command identity and idempotency

Two client-chosen identities make writes safe to retry (1–128 characters, `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`):

- The **`Idempotency-Key` header** on creates and mutations that declare it (Templates, Skill uploads and publish, Agents, Sessions).
- The **`clientEventId` body field** on `POST /api/v1/user/sessions/{id}/events`. All commands in one Session share this namespace.

Rules:

- Generate one identity per logical action and persist it **before** sending. Retry an uncertain request with the same identity and the same body.
- An identical replay returns the original result. The same identity with a different body returns `409` (`agent_creation_conflict`, `session_creation_conflict`, …).
- Never replace an uncertain request with a new identity — that can duplicate the effect.
- Secrets are not re-delivered: a lost User API Key needs rotation; a lost `connectorKey` needs `POST /api/v1/org/connectors/{id}/credential/rotate` with `expectedCurrentVersion` (while the Connector is inactive).
- End User creation has no idempotency key: recover by listing `GET /api/v1/org/users` and matching `externalId`.

## Versions and ETags

- Template replacement (`PUT /api/v1/org/agent-templates/{templateId}`) needs the exact quoted `ETag` in `If-Match`. Missing → `428 precondition_required`; stale → `412 precondition_failed`. Read the Template again, reapply the change, and use a new `Idempotency-Key`.
- Connector registration changes (`PATCH`, `activate`, `deactivate`) use `expectedConnectorVersion` in the body; on a version conflict, read the Connector and reapply the change with its current version. For `409` with no ready tunnel connection, check transport readiness and replica routing instead; see the [tunnel limitation](protocols/connectors.md#multi-replica-limit). Credential rotation uses `expectedCurrentVersion`, the `currentVersion` from `GET /api/v1/org/connectors/{id}/credential`.
- A receipt is a historical fact, not current state; it never provides a fresh ETag or version.

## Retry decisions

- Retry a connection failure, `429` or `503` only for reads or for writes protected by an idempotency identity. Honor `Retry-After`; otherwise use bounded exponential backoff with jitter.
- `503 service_configuration_unavailable` on a message saved nothing. Retrying the same `clientEventId` is safe, but it is refused again until the operator fixes the configuration (`details.reason`).
- Surface validation, authentication, authorization, conflict and precondition errors immediately with their `error.code`.
- The platform never retries a Connector call. After `timeout` or `result_unknown`, your device server reconciles by `callId` before assuming the effect did not happen.

## Session events (SSE) and recovery

- Submission (`POST …/events`) and observation (`GET …/events?stream=true`) are independent. The POST response never carries execution output.
- Disconnecting, a slow reader or no subscriber never cancels a Turn. Cancel explicitly with `{"type":"InputCancelEvent","clientEventId":"<new-id>","data":{}}`.
- Reconnect with the last SSE `id` as `cursor`. Revoking the key, disabling the End User or the Organization closes the stream without cancelling the Turn.
- After an uncertain POST, replay the same `clientEventId`, or read `GET …/interactions?clientEventId=<id>` (without `limit` / `cursor`) or `GET …/interactions/{clientEventId}`. The receipt's `result.status` is `running`, `succeeded`, `failed` or `interrupted`.
- Read saved replies and tool calls with `GET …/turns/{turnId}`, and text plus voice history in order with `GET …/timeline`. An EOF, an idle Session or an accepted command does not prove success.

## Pagination

Lists return `hasMore` and nullable `nextCursor`; pass `cursor` back with the same credential and filters. `limit` ranges are per operation (commonly 1–200, default 50). Cursors are opaque and scoped; foreign or stale cursors return `400`.

## Turn failures

`agent.session.turn.failed` and the Turn's `failure` carry a `code` and fixed text:

- Configuration: `model_provider_unconfigured`, `sandbox_unconfigured`, `drive9_unconfigured`, `drive9_disabled_for_organization` (an Organization admin enables Drive9 in Console).
- Model provider: `model_provider_failed` with `details.provider` (`category`, `httpStatus`, `errorType`, `errorCode`).
- Others such as `model_context_capacity_exceeded`, or `runtime_error`.

Tool Operations expose fixed text only, with `details.tool` and `details.category`. Connector failures reach the model as `invalid_arguments`, `forbidden`, `provider_unavailable`, `timeout`, `result_unknown` or `remote_tool_error`; see [protocols/connectors.md](protocols/connectors.md#tool-results-and-errors).

## Diagnose an API failure

1. Remove secrets, then record the status, error envelope (`error.code`, `error.message`, `error.details`), method and path, a request/correlation id **if the deployment returns one**, UTC timestamp, response headers and relevant SSE events.
2. Locate the operation, the response status and the `ErrorEnvelope` `code` in `openapi.yaml`.
3. Compare credential family, target ownership, headers, body schema, ETag or version, and idempotency identity.
4. For a Session command, read its receipt and Turn.
5. Give one root cause and the smallest corrective request or code change. If the contract omits an error description, report the omission and rely only on the observed response.

| HTTP | `error.code` | Meaning |
| --- | --- | --- |
| `401` | `authentication_required` | Missing, invalid, revoked or rotated key. |
| `403` | `auth_kind_forbidden`, `user_api_key_required` and similar | Wrong credential family for this operation. |
| `400` | `validation_error`, `idempotency_key_required`, `invalid_idempotency_key` | Request does not match the schema or header rules. |
| `404` | `resource_not_found`, `session_not_found`, … | Missing, foreign or hidden target. |
| `409` | `…_conflict`, `model_provider_unconfigured`, `realtime_not_enabled`, `realtime_connection_live` | Identity reuse with different content, or a state conflict. |
| `412` / `428` | `precondition_failed` / `precondition_required` | Stale or missing `If-Match`. |
| `503` | `service_configuration_unavailable`, `…_unavailable` | Deployment dependency missing or temporarily unavailable. |
