# 实时语音

[English](../../protocols/realtime-voice.md) | 简体中文

> 翻译基线：英文文档提交 [`a152eb4`](https://github.com/mem9-ai/tidblink-dev-guide/commit/a152eb4abcc08a6241fec90d41efd8e1b3989872)（2026-10-21）。接口定义以共用 OpenAPI 为准。

> 原文来自 TiDB Link 文档（`mem9-ai/agent-stack` 的 `main` @ `4734a32`，`apps/site/src/content/docs/docs/guides/`），做了少量调整：链接指向本工具包，移除了本指南范围之外的平台硬件和计费细节。

使用 Realtime 语音，让终端用户在已有 Session 中与 Agent 交谈。本指南按已实现的 `tidb-link.realtime.v1` 契约介绍浏览器与设备接入。[API 参考](../../openapi.yaml)及[可下载的 OpenAPI](../../openapi.yaml)描述 REST 请求和响应 schema。

Realtime 与文本使用同一个普通 Session。开启 Realtime Connection 不改变 Session 的所有者或 Agent 绑定。一个 Session 最多关联一个存活的 Realtime Connection；同一用户可在多个 Session 中使用语音。WebSocket 是该实时连接的传输通道，所以断开 WebSocket 与结束 Realtime Connection 是两种操作。

开启语音前检查 Session 响应的 `realtimeVoice`。`null` 表示只支持文本，连接准入会返回 `409 realtime_not_enabled`。非空对象将该 Session 的 `language` 固定为 `zh-CN` 或 `en-US`，适用于语音播报及重连，但不保证提供方可用。不支持该语言的提供方会返回 `realtime_language_unsupported`。未设置该字段的历史 Session 使用中文。语言设置影响语音，不影响普通文本；客户端不能通过 `session.update` 覆盖它。

<a id="what-realtime-provides"></a>

## Realtime 提供的能力

| 能力 | 应用可以做什么 |
| --- | --- |
| 同一 Session 中的语音与文本 | 为已有对话接入语音，在 Session 时间线读取已保存的文本和 Realtime 记录。 |
| 流式语音 | 发送麦克风音频，播放回复音频，显示临时或最终转写。 |
| 自由对话或按键说话 | 使用提供方语音检测，或由客户端标记每段话的开始与结束。 |
| Full Agent 任务 | 通过语音请求执行工作，接收与持久化 Turn 关联的任务受理、进度和结果。 |
| 播放打断 | 用户打断时立即停止缓冲音频，并上报最后实际播放的音频块。 |
| 连接恢复 | 为同一个存活连接获取新令牌，通过读取 Session 恢复持久化任务状态。 |

**Realtime Model** 负责语音对话。它委派工作时，**Full Agent** 使用 Session 的固定配置和已启用工具执行 Turn，并将进度和结果返回语音对话。普通 Realtime 聊天不会创建 Full Agent Turn。口头确认或进度播报与已保存的任务结果相互独立。

支持语音的 Session 中，Realtime Model 和 Full Agent 会收到相同的智能体模板指令（Instructions）：业务身份、目标、对话流程和信息来源约束。已有模板无需修改或重新发布 Instructions。涉及工具、Skill 或执行的需求会委派给 Full Agent，语音回复则遵循 Session 固定的 Realtime 语言。

同一 Session 可同时包含文本与 Realtime 交互。共享历史不保证完整恢复提供方上下文，也不保证进程丢失后恢复任务订阅；具体限制见下文。

<a id="1-open-the-realtime-connection-on-your-backend"></a>

## 1. 在后端开启 Realtime Connection

从终端用户拥有的已有 Session 开始，参见 [API 快速接入](../development-path.md#stage-4-text-conversation)。运维人员必须已发布可用的 Realtime 模型；仅连接准入成功不能证明语音提供方可用。

应用后端持有该用户的 API 密钥。浏览器和设备从后端获取短期连接授权，不应将用户 API 密钥存入固件。后端必须验证申请授权的应用请求确实来自该终端用户，并确认其拥有目标 Session，再转发请求到服务。

```sh
curl -X POST 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime' \
  -H 'Authorization: Bearer <user-api-key>'
```

`201` 响应包含状态为 `status: connecting` 的 `realtimeConnection`，以及 `websocketUrl`、`connectToken`、`connectTokenExpiresAt`。将这三个授权字段交给客户端。令牌签发后 60 秒过期，只允许一次 `session.connect`，跨副本也遵循此规则。不要将它放进 URL、日志或客户端持久化存储；每次连接尝试都需要新令牌。

从未建立连接的 Realtime Connection 会在 120 秒后自动过期。仅连接令牌过期不会结束实时连接；只要它仍存活，就应为其签发新令牌，而不是重复开启连接。

音频默认为单声道 PCM16：输入 16 kHz，输出 24 kHz。选择其他格式时可发送 JSON 请求体，例如：

```json
{
  "audio": {
    "input": { "encoding": "pcm16", "sampleRate": 16000, "channels": 1 },
    "output": {
      "encoding": "opus",
      "sampleRate": 24000,
      "channels": 1,
      "packetDurationMs": 20,
      "bitrate": 24000
    }
  }
}
```

发送请求体时携带 `Content-Type: application/json`。未指定的方向采用其 PCM16 默认值。支持的单声道格式如下：

| 方向 | 编码 | `sampleRate`（Hz） | `packetDurationMs` | `bitrate`（bps） |
| --- | --- | --- | --- | --- |
| 输入 | `pcm16` | 8000 或 16000（默认） | 省略 | 省略 |
| 输出 | `pcm16` | 8000、16000 或 24000（默认） | 省略 | 省略 |
| 输入 | `opus` | 16000 | 20（默认）、40 或 60 | 省略 |
| 输出 | `opus` | 24000 | 20 | 16000、24000 或 32000（默认） |

较低采样率的 PCM16 在连接准入时通过 `audio.input.sampleRate` 或 `audio.output.sampleRate` 选择。服务器使用连续低通滤波，将 8 kHz 输入重采样为模型的 16 kHz 输入，将模型的 24 kHz 输出重采样为选定的较低采样率。客户端按 `session.ready` 返回的实际采样率采集和播放。8 kHz 为电话音质，可能降低语音识别准确率；需要更小缓冲区且能接受该取舍时再使用。

PCM16 输出块的长度可能不同，也可能包含较短的滤波器尾部：按协商采样率播放所有载荷样本，并使用提供的块索引上报播放进度。不支持的格式或提供方组合会在连接准入前返回 `400 audio_format_unsupported`。

选择格式时应考虑音频载荷的内存占用。所有格式均为单声道；下表不含 5 字节二进制帧头、WebSocket/网络开销、包管理信息和编解码器工作内存。降低采样率可减少每秒内存与带宽，但无法避免长回复的到达速度快于播放速度时发生缓冲区溢出。

| 方向 | 编码 | 采样率 | 比特率 | 块或包的载荷 | 每秒音频字节数 |
| --- | --- | --- | --- | --- | --- |
| 输入 | PCM16 | 8000 Hz | 128 kbps | 客户端分块；每 20 ms 为 320 字节 | 16000 |
| 输入 | PCM16（默认） | 16000 Hz | 256 kbps | 客户端分块；每 20 ms 为 640 字节 | 32000 |
| 输出 | PCM16 | 8000 Hz | 128 kbps | 可变分块；每 20 ms 为 320 字节 | 16000 |
| 输出 | PCM16 | 16000 Hz | 256 kbps | 可变分块；每 20 ms 为 640 字节 | 32000 |
| 输出 | PCM16（默认） | 24000 Hz | 384 kbps | 提供方分块；每 20 ms 为 960 字节 | 48000 |
| 输入 | Opus | 16000 Hz | 由设备编码器选择，建议 16–32 kbps | 20（默认）、40 或 60 ms | 取决于设备编码器 |
| 输出 | Opus | 24000 Hz | `bitrate: 16000`（16 kbps） | 20 ms；40 字节 | 2000 |
| 输出 | Opus | 24000 Hz | `bitrate: 24000`（24 kbps） | 20 ms；60 字节 | 3000 |
| 输出 | Opus | 24000 Hz | `bitrate: 32000`（32 kbps，Opus 默认） | 20 ms；80 字节 | 4000 |

`audio.output.bitrate` 的单位为比特/秒，只接受 `16000`、`24000` 或 `32000`。新建的 Opus 输出连接使用固定比特率（CBR），省略时默认为 `32000`；替代了之前编解码器包默认的 64000 bps VBR。引入比特率协商前准入的连接可能不包含此字段，并保留原有编解码行为。PCM16 或任何输入格式携带 `bitrate` 都会被以 `audio_format_unsupported` 拒绝；设备自行控制 Opus 输入编码器。

实际输出比特率会出现在 `realtimeConnection.audio.output`、`session.ready.audio.output` 和存活 Session 的 `realtime.audio.output` 中。要获得内存节省，应先缓冲压缩 Opus 包，再解码播放；仅降低比特率不能避免突发传输的长回复导致溢出。

格式在 Realtime Connection 的整个生命周期内固定。更改格式需结束它，再在同一 Session 中开启新连接。`session.update` 当前只改变端点检测；虽然 schema 接受 `audio` 和 `voice`，这些字段不会改变正在运行的连接。

如果开启时返回 `409 realtime_connection_live`，读取 `GET /api/v1/user/sessions/<session-id>/realtime`。使用新的连接授权恢复已有连接，或先明确结束它再开启另一个。`GET` 返回最新连接的 `{ "realtimeConnection": ... }`，包括已结束的连接，但不签发令牌。

<a id="2-connect-the-websocket-and-wait-for-readiness"></a>

## 2. 连接 WebSocket 并等待就绪

使用 WebSocket 子协议 `tidb-link.realtime.v1` 连接返回的 `websocketUrl`。连接打开后立即将以下 JSON 文本帧作为首条消息发送；默认握手时限为 10 秒：

```json
{
  "type": "session.connect",
  "connect_token": "<connectToken>",
  "endpointing": { "mode": "client" }
}
```

授权中的 `connectToken` 在首帧中使用字段名 `connect_token`。保留各事件 schema 的字段名：共享的连接与音频对象仍使用 `sessionId`、`sampleRate` 等字段。身份验证在首帧完成，WebSocket 不携带用户 API 密钥。令牌必须属于 URL 指定的 Session；缺失、过期、复用或不匹配的令牌都会被拒绝。

等待 `session.ready` 后再发送音频或其他客户端事件；与握手并发发送的帧可能被丢弃。就绪事件包含 `realtime_connection`、实际生效的 `audio.input`、`audio.output` 和 `endpointing.mode`，应按这些值配置采集与播放。REST 响应中的 `connecting` 仅表示已准入，`session.ready` 才表示提供方连接已打开。首帧请求了可选 `capabilities` 时，`session.ready` 还会列出接受的能力，参见[按设备播放进度控制输出](#device-paced-output-output_flow_control_v1)。

端点检测（endpointing）决定用户的一段话何时结束：

- `client`：在一段话的音频前发送 `input_audio.activity`（`kind: start`），最后一帧音频后发送 `kind: end`。可由按键说话按钮或本地 VAD 作出判断。在选定的静音窗口结束后及时发送结束事件。
- `server`：持续发送麦克风音频，让提供方检测语音及其结束。此模式下忽略客户端 activity 事件。

首次连接省略 `endpointing` 时，如果配置的模型支持 `client` 就选择它，否则选择 `server`。重连时省略则保留当前模式。请求不支持的模式会返回 `endpointing_unsupported`；需签发新令牌，改用支持的模式或省略选择后重试。被拒绝的握手已经消耗旧令牌。

在已打开的连接上请求切换模式：

```json
{ "type": "session.update", "event_id": "mode-change-1", "endpointing": { "mode": "server" } }
```

只有收到 `session.updated` 确认后才应用模式。存活的提供方连接只能在它支持的模式之间切换。切换被拒绝时，原模式仍可使用；改用其他模式可能需要结束并重新开启 Realtime Connection。仅重连 WebSocket 会保留存活的提供方连接。

服务器每 15 秒发送 WebSocket 协议 ping 帧，30 秒未响应会关闭连接。浏览器 WebSocket 实现会自动响应；设备库必须支持 pong。没有 JSON 心跳事件。

<a id="3-send-microphone-audio-and-play-responses"></a>

## 3. 发送麦克风音频并播放回复

默认输入要求采集或重采样为 16 kHz 单声道，以小端字节序编码有符号 PCM16 样本。一个 20 ms 帧包含 320 个样本，即 640 字节载荷。浏览器麦克风样本通常是其他采样率的浮点数，直接转发原始字节不会得到有效 PCM16，客户端必须转换。浏览器播放还需在用户手势期间解锁 AudioContext。

音频可使用以下任一种承载方式。控制与转写事件始终是 JSON 文本帧。

<a id="binary-audio"></a>

### 二进制音频

二进制帧由 5 字节帧头和编码后的音频组成：

| 字节 | 输入：客户端到服务器 | 输出：服务器到客户端 |
| --- | --- | --- |
| `0` | `0x01` | `0x02` |
| `1..4` | 无符号 32 位帧计数器，大端 | 无符号 32 位 `chunk_index`，大端 |
| `5..` | 协商后的输入音频 | 协商后的输出音频 |

帧头字节序与 PCM16 样本的小端字节序相互独立。载荷最多 64 KiB；PCM16 载荷的字节数必须为偶数。Opus 载荷必须恰好包含一个协商时长的原始 Opus 包，不带 Ogg 或 WebM 容器。Opus 的块索引按包计数。

以下浏览器辅助函数在就绪后发送已编码的输入载荷：

```js
function sendAudioFrame(socket, sequence, payload) {
  const frame = new Uint8Array(5 + payload.byteLength);
  const header = new DataView(frame.buffer);
  header.setUint8(0, 0x01);
  header.setUint32(1, sequence, false);
  frame.set(payload, 5);
  socket.send(frame);
}
```

设置 `socket.binaryType = 'arraybuffer'`，以 ArrayBuffer 接收浏览器二进制消息。读取输出类型 `0x02`，使用 `getUint32(1, false)` 获取块索引，从第 5 字节开始读取音频。将这些块关联到最近的 `response.started.response_id`：二进制音频帧本身没有响应 ID，且一次只传输一个响应。

<a id="json-audio"></a>

### JSON 音频

也可发送 `input_audio.append`，仅对音频载荷做 base64 编码，不包含二进制帧头：

```json
{ "type": "input_audio.append", "audio": "<base64 encoded audio payload>" }
```

服务器随后发送 `response.audio.delta`，包含 `response_id`、从零开始的 `chunk_index` 和 base64 `audio`。按协商的输出格式解码该字段。

服务器最初以二进制发送音频，之后跟随客户端最近一个音频帧的承载方式。重连后重新从二进制开始。即使客户端偏好 JSON 输入，也必须同时处理二进制输出和 `response.audio.delta`。

无论是否启用输出流控，每个 Opus 输出响应都从全新的编码器状态开始。每次 `response.started` 时重置解码器。如果无法准备新的编码器状态，服务器会在发送该响应前以不可恢复的 `provider_unavailable` 错误结束连接。

<a id="utterances-transcripts-and-response-completion"></a>

### 语音片段、转写与响应完成

客户端端点检测模式中，每段话按以下顺序发送：JSON `{ "type": "input_audio.activity", "kind": "start" }`、音频帧、JSON `{ "type": "input_audio.activity", "kind": "end" }`。音频边采集边流式发送，不要先录完再整体上传。服务器端点检测只需音频帧。

使用以下服务器事件更新对话界面：

| 事件 | 客户端操作 |
| --- | --- |
| `transcript.partial` | 更新 `role: user` 或 `assistant` 的临时文本；存在 `response_id` 时用它关联助手文本。 |
| `transcript.final` | 显示最终文本片段。一段话可能包含多个最终片段。 |
| `response.started` | 按 `response_id` 创建输出响应，保留其 `kind` 和可选 `turn_id`。 |
| `response.audio.delta` 或二进制 `0x02` | 按该响应的块顺序解码并将音频加入播放队列。 |
| `response.audio.done` | 标记音频生成完成，继续播完队列中剩余音频。 |
| `response.interrupted` | 停止其 `response_id` 的播放，并丢弃排队音频。 |

音频生成完成不代表用户已听完本地播放队列，必须单独跟踪实际播放进度。响应类型包括普通 `chat`，以及任务确认、进度、澄清和结果；保留未知类型作为标签，避免新增类型破坏基本播放。任务响应通过 `turn_id` 指定 Turn。口头任务确认不代表任务完成，应以 `task.result` 和普通 Session 中持久化的 Turn 结果为准。

<a id="4-report-playback-and-handle-interruption"></a>

## 4. 上报播放进度与处理打断

跟踪每个 `response_id` 最后实际播放的音频块，而非最后收到的块。播放期间上报进度：

```json
{ "type": "playback.progress", "response_id": "<response-id>", "chunk_index": 3 }
```

用户打断或按下停止时，立即停止本地播放并丢弃排队块。如果知道实际播放到的块，则上报停止的响应：

```json
{
  "type": "playback.stopped",
  "response_id": "<response-id>",
  "chunk_index": 3,
  "reason": "user_interrupt"
}
```

播放失败使用 `reason: error`。索引不能为负，协议没有用于“尚未播放任何音频”的负数哨兵值。不知道实际播放位置时，发送 `{ "type": "input_audio.clear" }` 打断输出。当前实现会打断提供方输出，不会清除已保存的 Session 转写。收到 `response.interrupted` 时仍需处理。即使响应已在服务器完成、停止报告被忽略，本地停止的音频也应保持停止。

客户端端点检测模式中，用户说新的一段话时，还应发送 `input_audio.activity` start，再发送新的麦克风音频。服务器端点检测依赖提供方检测语音以实现打断。两种模式都必须控制本地播放，因为客户端可能已缓冲服务器发出的音频。

<a id="device-paced-output-output_flow_control_v1"></a>

### 按设备播放进度控制输出（`output_flow_control_v1`）

没有流控时，服务器按模型生成速度发送回复音频，因此长回答的到达速度可能远快于播放速度。使用 Opus 输出的内存受限设备，可以通过自身容量和播放进度控制音频发送节奏。在首帧请求该能力：

```json
{
  "type": "session.connect",
  "connect_token": "<connectToken>",
  "capabilities": ["output_flow_control_v1"]
}
```

`capabilities` 包含 1–8 个名称，每个最多 64 字符；未知名称会被忽略。首帧带有 `capabilities` 时，`session.ready` 返回接受的子集，可能为空。仅在流控被接受时，还会包含 `"output_flow_control": { "flow_epoch": 12 }`。服务器只对 `opus` 输出连接接受 `output_flow_control_v1`。每个 WebSocket，包括重连，都要重新协商，并使用本次 `session.ready` 的 `flow_epoch`。该值在一个存活运行时内递增，但在其他进程恢复后可能重复。每次连接都应丢弃之前客户端的额度和排空状态，重新授予容量。服务器也会丢弃之前连接的计数器、排队音频和排空状态，不会重放其音频。未请求该能力的客户端仍使用不受设备节奏控制的传输。

早于该能力部署的服务器会拒绝未知的 `capabilities` 字段：首帧返回 `invalid_event` 并关闭连接。先部署服务器，只向确认支持该能力的服务器请求它。

`session.ready` 后，用累计额度报告设备允许接收的输出量。一个 epoch 的首次额度为容量 C，单位为包；后续额度为 `C + released`，其中 `released` 是设备已解码或丢弃的包数：

```json
{ "type": "audio.output.credit", "flow_epoch": 12, "grant_total_frames": 170 }
```

`grant_total_frames` 为 0–2147483647 的整数。重复或乱序额度无害，因为只取最大值；其他 epoch 的额度会被忽略。释放进度变化时发送额度，例如发送频率不超过每 50 ms 一次，不要让排队的麦克风音频延迟它。未开启流控的连接会忽略额度与排空报告。

流控启用时，服务器遵循以下规则发送音频：

- 首次额度到达前不发送响应音频，其他事件照常传递。
- 交给 WebSocket 的累计包数不超过 `grant_total_frames`，包含仍在网络缓冲区中的包。
- 已发送但设备尚未释放的包最多 20 个（400 ms）。没有额度就停止发送；服务器不会仅依据经过的时间推断播放进度。
- 每个响应可一次发送前 6 包，随后平均每 20 ms 一包。
- 一次播放一个响应。下一个 `response.started` 等待前一个响应排空或被打断。`response.audio.done` 紧随响应最后一个包；转写、任务、用量、Session 和错误事件不会被阻塞。

每个响应全部播放完后上报：

```json
{
  "type": "audio.output.drained",
  "flow_epoch": 12,
  "response_id": "<response-id>",
  "last_chunk_index": 149
}
```

在 `response.audio.done` 之后，且该响应的压缩队列、已解码 PCM 和音频输出缓冲区全部清空时发送。没有音频的响应省略 `last_chunk_index`。其他 epoch 或未知响应的排空报告会被忽略。继续使用 `playback.progress` 上报实际播放到的块，包括 `response.audio.done` 之后。

用户打断会取消服务器仍为该连接保留的所有输出，包括已经生成完的响应。触发方式包括 `playback.stopped` 配合 `user_interrupt`、`input_audio.clear` 和提供方检测到的打断。未发送的包会被丢弃。已发送 `response.started` 的响应，会在最后上报块的位置收到 `response.interrupted`；尚未公布的响应被静默丢弃。`playback.stopped` 配合 `reason: error` 只取消指定响应。打断不会重置额度计数器；下次额度报告应把丢弃的包计为已释放。

每个连接最多保留 1500 个未发送包（30 秒）、256 KiB 未发送音频和 8 个响应。生成结果即将超限时，会按播放失败处理并取消该次生成：丢弃未发送音频，若响应已开始则发送 `response.interrupted`，并发送可恢复的 `output_backlog_exceeded` 错误；连接仍可用。音频也可能只因等待设备额度、允许的提前发送窗口或排空报告而停留。如果在这种状态下 5 秒内没有收到额度、排空或 `playback.progress`，服务器会发送不可恢复的 `output_flow_stalled` 错误，以 `session.ended` 的 `reason: server` 结束实时连接。

<a id="5-reconnect-or-end-deliberately"></a>

## 5. 重连或主动结束

WebSocket 意外关闭时，停止本地播放。要恢复连接，让后端为现有存活 Realtime Connection 签发新授权：

```sh
curl -X POST 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime/connect-tokens' \
  -H 'Authorization: Bearer <user-api-key>'
```

`201` 响应包含与初次开启相同的三个授权字段。连接其 `websocketUrl` 并发送新的首帧：

```json
{
  "type": "session.connect",
  "connect_token": "<new-connectToken>",
  "resume_after_event_id": "evt_42"
}
```

使用断连前最后收到的服务器 JSON `event_id`。二进制块不带事件 ID。在 60 秒恢复窗口内采用有上限的退避重试；令牌自身的 60 秒有效期是另一计时，不会延长恢复窗口。同一 Realtime Connection 的新 WebSocket 会取代旧 WebSocket。

当前重放缓冲区仅保留所属进程已捕获的 `task.accepted`、`task.status` 和 `task.result`，保留 60 秒。`session.ready` 后重放的任务事件 ID 可能小于新就绪事件的 ID。应按事件身份去重，同时处理尚未见过的重放事件，不能仅因序号低于就绪事件就丢弃。音频、转写和响应事件仅实时传递。清空本地音频队列，不要重发可能已到达提供方的麦克风音频。

WebSocket 脱离期间，TaskBridge 停止转发任务事件，因此即使重连到同一进程，断连期间产生的通知也可能不在缓冲区中。重连后读取持久化 Session/Turn 状态以恢复任务状态和结果；重放只是补充投递，不是完整的离线恢复。

同一进程内重连会保留提供方对话和运行中的任务。跨进程接管会隔离之前的提供方连接所有者，但目前不会重建进程本地的重放缓冲区或活跃任务订阅。可从 [Session 时间线](../reliability.md#session-events-sse-and-recovery)恢复持久化文本；进程丢失后的完整音频重放与任务恢复不在此基础契约范围内。

要结束而非恢复，在就绪连接上发送 `{ "type": "session.end" }`，或由后端调用：

```sh
curl -X DELETE 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime' \
  -H 'Authorization: Bearer <user-api-key>'
```

`DELETE` 返回已结束的 `realtimeConnection`，对于已经结束的最新连接是幂等的。正常的本地连接结束会发送带原因的 `session.ended`，再以 `1000` 关闭；收到此事件后停止重连。如果 WebSocket 已丢失，或终止发生在另一个副本，应通过 `GET …/realtime` 确认终态，不要依赖收到事件。仅关闭浏览器标签页，连接仍可在恢复窗口内恢复。删除普通 Session 也会结束其 Realtime Connection，并使未使用的连接令牌失效。

<a id="errors-and-compatibility-limits"></a>

## 错误与兼容性限制

REST 失败使用客户接口的 `ErrorEnvelope`；WebSocket 失败使用包含 `code`、`message` 和 `recoverable` 的 JSON `error` 事件。可选客户端 `event_id` 会在关联错误中以 `client_event_id` 返回。握手前错误使用服务器 `event_id: evt_0`。除错误事件外，也必须处理连接关闭，因为已断开的连接无法投递错误。

| 失败 | 恢复方式 |
| --- | --- |
| REST `401 authentication_required` 或 `403 user_api_key_required` | 修正后端凭据；这些路由接受所属用户的 API 密钥，不接受浏览器会话或组织 API 密钥。 |
| REST `404 session_not_found` | 找到实际存在、归属正确且未删除的 Session。 |
| REST `409 session_read_only` | 选择可以继续交互的 Session。 |
| REST `409 realtime_connection_live` | 读取并恢复存活连接，或明确结束后再开启另一个。 |
| 签发令牌时 REST `404 realtime_connection_not_found` 或 `409 realtime_connection_ended` | 读取 Session 状态；如果可用，再开启新的 Realtime Connection。 |
| REST `400 audio_format_unsupported` | 根据 `error.details` 修正相应方向的格式请求。 |
| REST `503 admission_unavailable` | 准入依赖暂时不可用。退避重试；再次开启前先读取连接状态，因为准入可能已成功，只是令牌签发失败。 |
| WS `invalid_connect_token` | 为正确的 Session 获取新授权；绝不能复用被拒绝的令牌。 |
| WS `endpointing_unsupported` | 选择支持的模式；更新被拒绝时保留当前模式。 |
| WS `invalid_event` | 修正事件结构、帧或发送顺序；反复发送无效帧会关闭连接。 |
| WS `output_backlog_exceeded` | 设备消费音频不够快，流控取消了一个回答。连接仍可用；检查额度报告。 |
| WS `output_flow_stalled` | 音频等待期间流控反馈停止，Realtime Connection 已结束。修复额度和排空报告，再开启新连接。 |
| WS 不可恢复错误，例如 `provider_unavailable` 或 `session_expired` | 停止向该连接发送，检查 REST 连接状态，再决定是否重新开启。 |

反复发送无效帧也可能导致标准关闭码 `1008`。可恢复错误表示连接仍可用，不意味着应重放音频或重复任务请求。已进入终态的 Realtime Connection 必须重新开启，不能仅获取新令牌。

本指南覆盖语音传输和 Full Agent 任务委派。设备操作及其他工作使用 `start_task`：Realtime Model 委派给 Full Agent Turn，由它使用 Session 已启用的工具，包括模板引用的 Connector 工具（见 [Connector](connectors.md)）。Realtime 不提供直接设备工具，也不提供命令/结果帧。Session 历史注入、完整的语音/文本任务引导和跨进程恢复目前仍有实现缺口。

在 `tidb-link.realtime.v1` 内，新增事件和可选字段是兼容性扩展；客户端应容忍未知服务器事件类型和字段。移除事件或改变含义需要新子协议版本，但有一项明确的退役例外：取消的设备直连路径在 v1 下移除了 `device.command`、`device.command_result` 和活跃 `device_ack`。已有客户端必须停止发送设备结果，改用 Full Agent 任务委派处理设备工作。持久化历史 `device_ack` 时间线条目仍可读取，但不代表现在可以发送该帧。

<a id="trying-voice-in-console"></a>

## 在 Console 中试用语音

Template Playground 可使用完整冻结的 Test 内容和选定的 Full Agent 模型测试语音。结束通话会保留 Test 打开状态。外部工具、私有文件和状态读取仍不可用。仅有任务进度或发送尝试不能证明实际物理操作已发生。客户应用应通过本指南中的用户 API 密钥路由操作普通 Session。
