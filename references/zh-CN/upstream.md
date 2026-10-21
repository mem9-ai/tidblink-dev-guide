# 上游契约与兼容性

[English](../upstream.md) | 简体中文

> 翻译基线：英文文档提交 [`a152eb4`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。接口定义以共用 OpenAPI 为准。

[openapi.yaml](../openapi.yaml) 是 [`mem9-ai/agent-stack/docs/openapi.yaml`](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/docs/openapi.yaml) 的未修改副本，于 2026-10-21 从 `main` 获取。

- 上游提交：`a32727a543c1b62a569efc177994a97bf6a7fbed`
- YAML SHA-256：`6dc8aed7a29fa87916fe57919e754498b2763b6963da06e59365a39f9e19daf3`
- [api-reference.html](../api-reference.html) 使用原有内嵌 ReDoc 渲染器，嵌入相同契约的解析结果，运行时不会获取另一份契约。

契约描述的是该上游版本，不代表每个环境实际部署的版本。操作行为不一致时，请向运维人员确认部署版本。更新时保持上游 YAML 原样不变；在同一次变更中将 HTML 的 `const spec` JSON 替换为 YAML 的解析结果，校验 OpenAPI，并更新此处版本与哈希。

<a id="stage-3-boundaries-checked-against-upstream"></a>

## 已对照上游核查的阶段 3 边界

| 问题 | 当前行为 | 来源 |
| --- | --- | --- |
| Connector 管理 | `/api/v1/org/connectors/**` 要求组织 API 密钥。WebSocket 仍为 `/api/v1/connectors/ws`，使用 Connector Key。 | [Customer OpenAPI](../openapi.yaml) |
| 模板关联 | 组织模板 schema 不包含 `tools`；必须通过具有模板编辑权限的 Console 账号关联 Connector。 | [组织模板 schema](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/src/agent-templates/organization-agent-template.dto.ts) |
| Tunnel 路由 | 就绪连接只对持有它的平台副本可见。其他副本上的激活和调用可能失败。使用 `streamable_http`，或由运维人员保障部署位置与路由。 | [运行时归属清单](https://github.com/mem9-ai/agent-stack/blob/a32727a543c1b62a569efc177994a97bf6a7fbed/docs/architecture/multi-replica-runtime-ownership.md#pod-local-state) |

这些文档变更没有新增模板工具引用的 Customer API，也没有修复后端 tunnel 路由。此前腾讯云验证完成了文本和语音，但因缺少 Console 权限，未完成设备工具调用。更新工具包并不代表阶段 3 已通过新的在线验证；满足前提条件后，应创建新 Session 验证实际设备调用。
