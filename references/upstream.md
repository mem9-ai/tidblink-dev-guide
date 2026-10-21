# Upstream contract and compatibility

English | [简体中文](zh-CN/upstream.md)

`openapi.yaml` is an unmodified copy of [`mem9-ai/agent-stack/docs/openapi.yaml`](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/docs/openapi.yaml), taken from `main` on 2026-10-21.

- Upstream commit: `a32727a543c1b62a569efc177994a97bf6a7fbed`
- YAML SHA-256: `6dc8aed7a29fa87916fe57919e754498b2763b6963da06e59365a39f9e19daf3`
- `api-reference.html` embeds the same parsed contract, with its existing bundled Redoc renderer. It does not fetch another contract at runtime.

The contract describes this upstream revision, not the deployed version of every environment. Confirm the deployment's release with its operator when an operation differs. Preserve upstream YAML verbatim when updating; replace the HTML's `const spec` JSON with the parsed YAML in the same change, validate OpenAPI, and update this revision and hash.

## Stage 3 boundaries checked against upstream

| Concern | Current behavior | Source |
| --- | --- | --- |
| Connector management | `/api/v1/org/connectors/**` requires an Organization API Key. The WebSocket remains `/api/v1/connectors/ws` with a Connector Key. | [Customer OpenAPI](openapi.yaml) |
| Template attachment | The Organization Template schema omits `tools`; a Console account with Template edit permission must attach the Connector. | [Organization Template schema](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/src/agent-templates/organization-agent-template.dto.ts) |
| Tunnel routing | A ready socket is visible only to the platform replica holding it. Activation and dispatch can fail on other replicas. Use `streamable_http`, or an operator-supported placement/routing arrangement. | [Runtime ownership inventory](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/docs/architecture/multi-replica-runtime-ownership.md#pod-local-state) |

These documentation changes do not add a Customer API for Template tool references or repair backend tunnel routing. The earlier Tencent validation completed text and voice, but did not complete device tool dispatch because Console access was missing. Updating this kit is not evidence of a new live Stage 3 success; verify the actual device call with a newly created Session after completing the prerequisites.
