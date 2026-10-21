# 中文翻译维护说明

中文入口：[README.zh-CN.md](../../README.zh-CN.md)。本仓库保留一个 [Skill 入口](../../SKILL.md)；中文请求优先读取中文指南，所有接口判断仍使用共用的 [OpenAPI](../openapi.yaml)。完整 [HTML API 参考](../api-reference.html)目前为英文。

## 翻译基线

首版对应英文提交 [`a152eb4abcc08a6241fec90d41efd8e1b3989872`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。该版包含腾讯云接入阻断说明，以及同步到 agent-stack `a32727a` 的 OpenAPI。

翻译涉及 README、六篇参考文档（五篇接入指南及新增的上游说明）和两张 SVG 图。本次还为英文文档加入语言切换，并修正英文架构图中旧的“Console 仅用于准备阶段”文字，使其与正文中的模板 Connector 关联要求一致。

[translation-sources.json](translation-sources.json) 记录翻译基线及每个英文来源的 SHA-256。哈希对应加入导航及上述图示修正后的配对文件，用于发现后续待同步变更，并非声称这些文件逐字节等同于基线提交。

## 术语与保留内容

| 英文 | 中文约定 |
| --- | --- |
| Organization | 组织 |
| Agent Template | 智能体模板；上下文明确时简称模板 |
| End User | 终端用户，区别于 Console 账号 |
| Agent | 智能体；对象关联链中保留 Agent |
| Session | 会话；协议与步骤中保留 Session |
| Turn | 执行轮次；后文保留 Turn，避免误解为一问一答 |
| Connector | 连接器；后文保留 Connector |
| Call Context | 调用上下文 |
| Organization API Key | 组织 API 密钥 |
| User API Key | 用户 API 密钥 |
| Realtime Connection | 实时连接；需要区别于 WebSocket 时保留英文 |
| endpointing | 端点检测，即一段话的结束判定 |
| Done when | 完成标准 |

保留全部代码块，包括示例注释和字符串，便于逐字比较。API 路径、HTTP 方法、字段、错误码、事件名、枚举值、环境变量、版本与协议标识不翻译。中文标题附带稳定的英文锚点；同语言导航优先指向对应译文，契约链接指向共用文件。

SVG 保持源图的结构和连接关系，翻译可见标签并补充中文字体回退；协议标识原样保留。文字需适配实际容器宽度，不能仅替换字符串而不检查渲染。

## 同步流程

1. 修改英文内容时，运行 `python3 scripts/check_translations.py` 查看受影响的译文。源文件哈希变化会使检查失败。
2. 对照英文变更更新中文。特别复核凭据、路由、状态字段、时间限制、Console 前提、多副本限制，以及“请求被接受”和“执行成功”的区别。
3. 只有人工核对完成后，才更新清单中对应的 `source_sha256`（可用 `sha256sum <英文文件>` 获取），并更新该译文顶部的基线提交与日期。不要仅刷新哈希来消除检查失败。
4. 再次运行检查脚本和 `git diff --check`。脚本检查来源漂移、代码块一致性、章节数量、英文锚点、SVG 标签数量及本地 Markdown 链接；它不能替代翻译审校。
5. SVG 有变化时，用浏览器实际打开，检查中文字体、文字宽度和裁切。协议未变时不需要调用线上服务验证翻译；文档检查不能作为新的端到端接入成功证据。

不要另行维护一套中文 OpenAPI。若以后要提供中文 API 参考，应以原始契约与中文文案映射生成，保留接口结构，并与上游版本一起更新。
