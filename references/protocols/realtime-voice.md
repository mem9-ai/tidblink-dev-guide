# Realtime voice

> Bundled from the TiDB Link documentation (`mem9-ai/agent-stack` `main` @ `4734a32`, `apps/site/src/content/docs/docs/guides/`). Lightly adapted: links point into this kit, and platform-hardware details outside this guide's scope were removed.

Use Realtime voice to let an End User speak with an Agent in an existing Session. This guide covers browser and device integration under the implemented `tidb-link.realtime.v1` contract. The [API reference](../openapi.yaml) and [downloadable OpenAPI](../openapi.yaml) describe the REST request and response schemas.

Realtime and text interact with the same ordinary Session. Opening a Realtime Connection preserves the Session's owner and Agent binding. At most one live Realtime Connection can attach to a Session; the same User may speak on several Sessions. A socket is the transport for that connection, so dropping the socket and ending the Realtime Connection are different operations.

Check the Session response's `realtimeVoice` before opening voice. `null` means text only and admission returns `409 realtime_not_enabled`. An object fixes `language` to `zh-CN` or `en-US` for this Session, including narration and reconnects; it does not guarantee provider availability. A provider that cannot serve it returns `realtime_language_unsupported`. Historical Sessions without a setting use Chinese. Language affects speech, not ordinary text, and clients cannot override it with `session.update`.

## What Realtime provides

| Capability | What your application can do |
| --- | --- |
| Voice and text in one Session | Attach voice to an existing conversation and read its saved text and Realtime facts in the Session Timeline. |
| Streamed speech | Send microphone audio, play response audio and show partial or final transcripts. |
| Free conversation or push-to-talk | Use provider speech detection, or have your client mark the start and end of an utterance. |
| Full Agent tasks | Ask for work through speech and receive task acceptance, progress and results associated with a durable Turn. |
| Playback interruption | Stop buffered audio immediately when the user interrupts and report the last audible chunk. |
| Connection recovery | Obtain a fresh token for the same live connection and recover durable task state through Session reads. |

The **Realtime Model** handles the spoken conversation. When it delegates work, the **Full Agent** executes a Turn using the Session's fixed configuration and enabled tools. Progress and results return to the voice conversation. Ordinary Realtime chat does not create a Full Agent Turn. A spoken acknowledgement or progress message is separate from the task's saved outcome.

For a voice-enabled Session, the Realtime Model and Full Agent receive the same configured Agent Template Instructions: business identity, goals, conversation flow and information-source constraints. Existing Templates need no Instructions edit or republication. Requirements involving tools, Skills or execution delegate to the Full Agent, while spoken replies follow the Session's fixed Realtime language.

The same Session can contain both text and Realtime interaction. Shared history does not promise complete provider context restoration or recovery of a task subscription after process loss; the recovery limits below apply.

## 1. Open the Realtime Connection on your backend

Start with an existing Session owned by the End User, following the [API quick start](../development-path.md#stage-4-text-conversation). An operator must have published a usable Realtime model; admitting a connection alone does not prove the speech provider is available.

Your customer backend holds the owning User API Key. Browsers and devices receive a short-lived connect grant from your backend rather than storing that key in firmware. Authenticate your application's request for a grant as that End User, and resolve the Session they own before forwarding it to the service.

```sh
curl -X POST 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime' \
  -H 'Authorization: Bearer <user-api-key>'
```

The `201` response contains `realtimeConnection` with `status: connecting`, plus `websocketUrl`, `connectToken` and `connectTokenExpiresAt`. Hand those three grant fields to the client. The token expires 60 seconds after minting and authorizes exactly one `session.connect`, including across replicas. Keep it out of URLs, logs and persistent client storage; each connection attempt needs a fresh token.

A connection that never connects is subject to automatic expiry after 120 seconds. An expired connect token alone does not end the connection; while it remains live, mint a new token for it rather than opening a duplicate.

Audio defaults to mono PCM16: 16 kHz input, 24 kHz output. To choose formats, send an optional JSON body, for example:

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

Include `Content-Type: application/json` when sending a body. An omitted direction uses its PCM16 default. Supported mono formats are:

| Direction | Encoding | `sampleRate` (Hz) | `packetDurationMs` | `bitrate` (bps) |
| --- | --- | --- | --- | --- |
| Input | `pcm16` | 8000 or 16000 (default) | Omit | Omit |
| Output | `pcm16` | 8000, 16000 or 24000 (default) | Omit | Omit |
| Input | `opus` | 16000 | 20 (default), 40 or 60 | Omit |
| Output | `opus` | 24000 | 20 | 16000, 24000 or 32000 (default) |

For lower-rate PCM16, choose the rate in `audio.input.sampleRate` or `audio.output.sampleRate` at admission. The server resamples 8 kHz input to the model's 16 kHz input and its 24 kHz output to the selected lower rate with continuous low-pass filtering. Your client captures and plays at the effective rates echoed by `session.ready`. 8 kHz provides telephone quality and can reduce speech recognition accuracy; use it when the smaller buffers are worth that trade-off.

PCM16 output chunks can have different lengths, including a short final filter tail: play all payload samples at the negotiated rate and use the supplied chunk indexes for playback reports. The server refuses an unsupported format or provider combination with `400 audio_format_unsupported`, before admitting the connection.

Choose a format by the audio payload memory it needs. All formats are mono; values below exclude the 5-byte binary frame header, WebSocket/network overhead, packet bookkeeping and codec working memory. Lower rates reduce memory and bandwidth per second; they do not prevent buffer overflow when a long response arrives faster than playback.

| Direction | Encoding | Sample rate | Bitrate | Chunk or packet payload | Audio bytes per second |
| --- | --- | --- | --- | --- | --- |
| Input | PCM16 | 8000 Hz | 128 kbps | Client chunks; 320 bytes per 20 ms | 16000 |
| Input | PCM16 (default) | 16000 Hz | 256 kbps | Client chunks; 640 bytes per 20 ms | 32000 |
| Output | PCM16 | 8000 Hz | 128 kbps | Variable chunks; 320 bytes per 20 ms | 16000 |
| Output | PCM16 | 16000 Hz | 256 kbps | Variable chunks; 640 bytes per 20 ms | 32000 |
| Output | PCM16 (default) | 24000 Hz | 384 kbps | Provider chunks; 960 bytes per 20 ms | 48000 |
| Input | Opus | 16000 Hz | Device encoder chooses; 16–32 kbps recommended | 20 (default), 40 or 60 ms | Depends on device encoder |
| Output | Opus | 24000 Hz | `bitrate: 16000` (16 kbps) | 20 ms; 40 bytes | 2000 |
| Output | Opus | 24000 Hz | `bitrate: 24000` (24 kbps) | 20 ms; 60 bytes | 3000 |
| Output | Opus | 24000 Hz | `bitrate: 32000` (32 kbps, default for Opus) | 20 ms; 80 bytes | 4000 |

`audio.output.bitrate` is in bits per second and accepts only `16000`, `24000` or `32000`. New Opus output connections use constant bitrate (CBR), defaulting to `32000` when omitted; this replaces the previous codec package default of 64000 bps with VBR. Connections admitted before bitrate negotiation may omit the field and retain their previous codec behavior. `bitrate` on PCM16 or any input format is refused with `audio_format_unsupported`; the device controls its own Opus input encoder.

The effective output bitrate is echoed in `realtimeConnection.audio.output`, `session.ready.audio.output` and the live Session's `realtime.audio.output`. Buffer compressed Opus packets and decode them for playback to obtain the memory savings; lower bitrate alone cannot prevent overflow from long replies delivered in bursts.

Formats stay fixed for the lifetime of the Realtime Connection. To change them, end it and open another on the same Session. `session.update` currently changes only endpointing; although its schema accepts `audio` and `voice`, those fields do not change the running connection.

If opening answers `409 realtime_connection_live`, read `GET /api/v1/user/sessions/<session-id>/realtime`. Resume the existing connection using a new connect grant, or explicitly end it before opening another. `GET` returns `{ "realtimeConnection": ... }` for the newest connection, including an ended one; it does not issue a token.

## 2. Connect the WebSocket and wait for readiness

Open the returned `websocketUrl` using the WebSocket subprotocol `tidb-link.realtime.v1`. Send this JSON text frame as the first message, promptly after the socket opens; the default handshake deadline is 10 seconds:

```json
{
  "type": "session.connect",
  "connect_token": "<connectToken>",
  "endpointing": { "mode": "client" }
}
```

The grant's `connectToken` becomes `connect_token` in this first frame. Preserve each event schema's field names: shared connection and audio objects retain fields such as `sessionId` and `sampleRate`. Authentication happens in the first frame, with no User Key on the socket. The token must belong to the Session named by the URL. A missing, expired, reused or mismatched token is refused.

Wait for `session.ready` before sending audio or other client events. Frames racing the handshake may be dropped. The readiness event carries `realtime_connection`, effective `audio.input` and `audio.output`, and `endpointing.mode`; use those values to configure capture and playback. `connecting` in the REST response is admission, while `session.ready` means the provider is open. When the first frame requested optional `capabilities`, `session.ready` also lists the accepted ones; see [Device-paced output](#device-paced-output-output_flow_control_v1).

Endpointing decides when the user's utterance ends:

- `client`: send `input_audio.activity` with `kind: start` before the utterance's audio and `kind: end` after its last audio frame. A push-to-talk button or local VAD can make these decisions. Send the end event promptly after your chosen silence window.
- `server`: stream microphone audio and let the provider detect speech and its end. Client activity events are ignored in this mode.

Omitting `endpointing` on the first connect selects `client` when the configured model can serve it, otherwise `server`. On reconnect, omission keeps the current mode. A requested unsupported mode answers `endpointing_unsupported`; mint a new token and retry with a supported mode or omit the selection. The refused handshake has consumed the old token.

To request a mode change on an open socket:

```json
{ "type": "session.update", "event_id": "mode-change-1", "endpointing": { "mode": "server" } }
```

Apply the mode only after `session.updated` confirms it. A live provider connection can switch only between modes it serves. If switching is refused, the existing mode remains usable; using the other mode may require ending and opening a new Realtime Connection. Reconnecting the socket alone keeps the live provider connection.

The server sends WebSocket protocol ping frames every 15 seconds and closes a socket that has not answered for 30 seconds. Browser WebSocket implementations answer automatically; device libraries must support pong replies. There is no JSON heartbeat event.

## 3. Send microphone audio and play responses

For the default input, capture or resample to 16 kHz mono and encode signed PCM16 samples in little-endian byte order. A 20 ms frame contains 320 samples, or 640 payload bytes. Browser microphone samples are commonly floating point at another rate, so forwarding their raw bytes does not produce valid PCM16. Your client must perform that conversion. For browser playback, unlock the AudioContext during a user gesture.

Use either carrier for audio. Control and transcript events are always JSON text frames.

### Binary audio

Binary frames contain a five-byte header followed by the encoded audio:

| Bytes  | Input: client to server                   | Output: server to client                  |
| ------ | ----------------------------------------- | ----------------------------------------- |
| `0`    | `0x01`                                    | `0x02`                                    |
| `1..4` | Unsigned 32-bit frame counter, big-endian | Unsigned 32-bit `chunk_index`, big-endian |
| `5..`  | Negotiated input audio                    | Negotiated output audio                   |

The header's byte order is independent of PCM16's little-endian sample order. Payloads are at most 64 KiB; PCM16 payloads have an even byte length. An Opus payload contains exactly one raw Opus packet of the negotiated duration, without an Ogg or WebM container. Opus chunk indexes count packets.

This browser helper sends an already encoded input payload after readiness:

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

Set `socket.binaryType = 'arraybuffer'` to receive browser binary messages as ArrayBuffers. Read output type `0x02`, its chunk index with `getUint32(1, false)`, and audio from byte 5 onward. Associate these chunks with the latest `response.started.response_id`: a binary audio frame has no response ID of its own, and one response streams at a time.

### JSON audio

Alternatively, send `input_audio.append` with base64 of the audio payload alone, without the binary header:

```json
{ "type": "input_audio.append", "audio": "<base64 encoded audio payload>" }
```

The server then sends `response.audio.delta` with `response_id`, zero-based `chunk_index` and base64 `audio`. Decode that field according to the negotiated output format.

The server initially sends audio as binary, and follows the carrier of the client's most recent audio frame thereafter. A reconnect starts with binary again. Handle both binary output and `response.audio.delta`, even when your client prefers JSON input.

Every Opus output response starts from fresh encoder state, whether or not output flow control is enabled. Reset your decoder at every `response.started`. If fresh encoder state cannot be prepared, the server ends the connection with a nonrecoverable `provider_unavailable` error before sending that response.

### Utterances, transcripts and response completion

In client endpointing mode, send this sequence for each utterance: JSON `{ "type": "input_audio.activity", "kind": "start" }`, its audio frames, then JSON `{ "type": "input_audio.activity", "kind": "end" }`. Audio is streamed as captured, rather than uploaded as a complete recording. Server endpointing needs only the audio frames.

Use these server events to drive the conversation UI:

| Event | Client action |
| --- | --- |
| `transcript.partial` | Update provisional text for `role: user` or `assistant`; associate assistant text using `response_id` when present. |
| `transcript.final` | Display the finalized text segment. One utterance can have several final segments. |
| `response.started` | Start an output response keyed by `response_id`. Retain its `kind` and optional `turn_id`. |
| `response.audio.delta` or binary `0x02` | Decode and queue audio in chunk order for that response. |
| `response.audio.done` | Mark audio production complete; finish playing any queued audio. |
| `response.interrupted` | Stop playback and discard queued audio for its `response_id`. |

Audio production finishing does not mean the user has heard the local playback queue. Track audible progress separately. Response kinds include ordinary `chat` and task acknowledgements, progress, clarification and results; preserve unknown kinds as labels so an added kind does not break basic playback. A task response names its Turn with `turn_id`. Spoken task acknowledgements are not proof of task completion; use `task.result` and the ordinary Session's durable Turn result for that.

## 4. Report playback and handle interruption

Track the last audible chunk of each `response_id`, rather than the last received chunk. Report progress while audio plays:

```json
{ "type": "playback.progress", "response_id": "<response-id>", "chunk_index": 3 }
```

When the user interrupts or presses Stop, silence local playback and discard its queued chunks immediately. If an audible chunk is known, report the stopped response:

```json
{
  "type": "playback.stopped",
  "response_id": "<response-id>",
  "chunk_index": 3,
  "reason": "user_interrupt"
}
```

Use `reason: error` for a playback failure. Indexes are nonnegative; the protocol has no negative sentinel for audio that has never played. For an output interruption without a known audible position, send `{ "type": "input_audio.clear" }`. Its current implementation interrupts provider output; it does not erase saved Session transcripts. Continue handling `response.interrupted` if it arrives. Locally stopped audio stays stopped even if the response had already finished on the server and the report is ignored.

In client endpointing mode, also send `input_audio.activity` start and then the new microphone audio for a user's new utterance. Server endpointing uses provider-detected speech for barge-in. Local playback control is necessary in both modes because the client may have buffered audio the server has already sent.

### Device-paced output (`output_flow_control_v1`)

Without flow control, the server sends response audio as fast as the model produces it, so a long answer can arrive much faster than it plays. A memory-constrained device with Opus output can instead let its own capacity and playback pace the audio. Request the capability in the first frame:

```json
{
  "type": "session.connect",
  "connect_token": "<connectToken>",
  "capabilities": ["output_flow_control_v1"]
}
```

`capabilities` lists 1 to 8 names of at most 64 characters; unknown names are ignored. When the first frame carries `capabilities`, `session.ready` echoes the accepted subset, possibly empty. Only when flow control is accepted does it also carry `"output_flow_control": { "flow_epoch": 12 }`. The server accepts `output_flow_control_v1` only for a connection with `opus` output. Every socket, including a reconnect, negotiates again and uses the `flow_epoch` from its own `session.ready`. Values increase within one live runtime but may repeat after recovery in another process. On every connection, discard previous client credits and drain state and grant capacity again. The server also discards counters, queued audio and drain state of an earlier socket; its audio is not replayed. Clients that do not request the capability retain unpaced delivery.

A server deployed before this capability refuses the unknown `capabilities` field: the first frame fails with `invalid_event` and the socket closes. Deploy the server first, and request the capability only from servers known to support it.

After `session.ready`, report the device's output allowance with cumulative credits. The first credit of an epoch is the capacity C, in packets; later credits send `C + released`, where `released` counts packets the device has decoded or discarded:

```json
{ "type": "audio.output.credit", "flow_epoch": 12, "grant_total_frames": 170 }
```

`grant_total_frames` is an integer from 0 to 2147483647. A repeated or reordered credit is harmless because the largest value counts; a credit for another epoch is ignored. Send a credit whenever release progress changes, for example at most every 50 ms, and do not let queued microphone audio delay it. On a socket without flow control, credits and drains are ignored.

While flow control is active, the server sends audio according to these rules:

- No response audio goes out before the first credit. Other events still flow.
- Packets handed to the socket never exceed `grant_total_frames`, counting packets still in network buffers.
- At most 20 packets (400 ms) are sent beyond what the device has released. Missing credits stop further sending; the server never assumes playback from elapsed time alone.
- Each response may send its first 6 packets at once, then averages one packet per 20 ms.
- One response plays at a time. The next `response.started` waits until the previous response is drained or interrupted. `response.audio.done` follows the response's last packet. Transcript, task, usage, session and error events are not held back.

Report each response that has fully played:

```json
{
  "type": "audio.output.drained",
  "flow_epoch": 12,
  "response_id": "<response-id>",
  "last_chunk_index": 149
}
```

Send it after `response.audio.done`, once that response's compressed queue, decoded PCM and audio output buffer are all empty. Omit `last_chunk_index` for a response without audio. A drain for another epoch or an unknown response is ignored. Keep reporting the actually played chunk with `playback.progress`, including after `response.audio.done`.

A user interruption cancels all output the server still holds for the socket, including responses whose generation has already finished. This covers `playback.stopped` with `user_interrupt`, `input_audio.clear` and provider-detected barge-in. Unsent packets are dropped. A response whose `response.started` went out receives `response.interrupted` at its last reported chunk; a response never announced is dropped silently. `playback.stopped` with `reason: error` cancels only the named response. Interruption never resets the credit counters: count the discarded packets as released in your next credit.

The server holds at most 1500 unsent packets (30 seconds), 256 KiB of unsent audio and 8 responses per connection. A generation that would exceed a bound is cancelled as if its playback failed. Its unsent audio is dropped, `response.interrupted` follows if the response started, and a recoverable `output_backlog_exceeded` error is sent; the connection stays usable. Audio may also wait only on the device: for a credit, for the lead window or for a drain. If no credit, drain or `playback.progress` arrives for 5 seconds in that state, the server sends a non-recoverable `output_flow_stalled` error and ends the Realtime Connection with `session.ended` reason `server`.

## 5. Reconnect or end deliberately

On an unexpected socket close, stop local playback. To resume, have your backend mint a new grant for the existing live Realtime Connection:

```sh
curl -X POST 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime/connect-tokens' \
  -H 'Authorization: Bearer <user-api-key>'
```

The `201` response carries the same three grant fields as the initial open. Connect to its `websocketUrl` and send a new first frame:

```json
{
  "type": "session.connect",
  "connect_token": "<new-connectToken>",
  "resume_after_event_id": "evt_42"
}
```

Use the last server JSON `event_id` received before the drop. Binary chunks carry no event ID. Retry with bounded backoff within the 60-second resume window; a token's 60-second expiry is a separate clock and does not extend that window. A newer socket supersedes the previous socket for the same Realtime Connection.

The current replay buffer retains only `task.accepted`, `task.status` and `task.result` already captured by the owning process, for 60 seconds. After `session.ready`, replayed task events can have lower event IDs than that new ready event. Deduplicate by event identity, but still process unseen replayed events; do not reject them simply because their sequence is lower than readiness. Audio, transcripts and response events are live-only. Clear local audio queues and do not resend microphone audio that might already have reached the provider.

TaskBridge stops forwarding task events while the socket is detached, so notifications produced during disconnection may be absent from that buffer even on a same-process reconnect. After reconnecting, read durable Session/Turn state to recover task status and results; replay is supplementary delivery, not complete offline recovery.

A same-process reconnect retains the provider conversation and running task. Cross-process takeover fences the previous provider owner, but does not currently reconstruct the process-local replay buffer or an active task subscription. Recover durable text from the [Session Timeline](../reliability.md#session-events-sse-and-recovery); complete audio replay and task recovery across process loss are outside this basic contract.

To finish rather than resume, send `{ "type": "session.end" }` on the ready socket, or have your backend call:

```sh
curl -X DELETE 'https://<your-agent-service-host>/api/v1/user/sessions/<session-id>/realtime' \
  -H 'Authorization: Bearer <user-api-key>'
```

`DELETE` returns the ended `realtimeConnection` and is idempotent for an already-ended newest connection. A normal local socket end sends `session.ended` with a reason, then closes with code `1000`; stop reconnecting on this event. If the socket is lost or termination is performed on another replica, confirm terminal state through `GET …/realtime` instead of depending on receiving the event. Closing a browser tab alone leaves the connection available for the resume window. Deleting the ordinary Session also ends its Realtime Connection and invalidates outstanding connect tokens.

## Errors and compatibility limits

REST failures use the customer `ErrorEnvelope`; WebSocket failures use a JSON `error` event with `code`, `message` and `recoverable`. An optional client `event_id` is echoed as `client_event_id` on correlated errors. Pre-handshake errors use server `event_id: evt_0`. Handle socket close as well as error events, since a disconnected socket cannot deliver an error.

| Failure | Recovery |
| --- | --- |
| REST `401 authentication_required` or `403 user_api_key_required` | Correct backend credentials; these routes accept the owning User Key rather than a browser session or Organization Key. |
| REST `404 session_not_found` | Resolve an existing, owned, undeleted Session. |
| REST `409 session_read_only` | Select a Session that can be continued. |
| REST `409 realtime_connection_live` | Read and resume the live connection, or explicitly end it before opening another. |
| REST `404 realtime_connection_not_found` or `409 realtime_connection_ended` on token minting | Read Session state, then open a new Realtime Connection if the Session is usable. |
| REST `400 audio_format_unsupported` | Correct the requested direction using `error.details`. |
| REST `503 admission_unavailable` | Admission dependencies are temporarily unavailable. Retry with backoff; before repeating an open, read connection state because admission may have succeeded before token minting failed. |
| WS `invalid_connect_token` | Obtain a new grant for the correct Session; never reuse the refused token. |
| WS `endpointing_unsupported` | Select a supported mode, keeping the current mode on a refused update. |
| WS `invalid_event` | Correct the event shape, frame or send order; repeated invalid frames close the socket. |
| WS `output_backlog_exceeded` | Flow control cancelled one answer because the device did not consume audio fast enough. The socket stays usable; check credit reporting. |
| WS `output_flow_stalled` | Flow-control feedback stopped while audio waited, and the Realtime Connection ended. Fix credit and drain reporting, then open a new connection. |
| WS non-recoverable error, such as `provider_unavailable` or `session_expired` | Stop sending on that socket, inspect REST connection state and decide whether to reopen. |

Repeated invalid frames can also close the socket with standard code `1008`. A recoverable error keeps the socket usable; it is not an instruction to replay audio or repeat task requests. A terminal Realtime Connection needs a new open, not merely another token.

This guide covers speech transport and Full Agent task delegation. Device actions and other work use `start_task`: the Realtime Model delegates to a Full Agent Turn, which runs with the Session's enabled tools — including tools of Connectors the Template references (see [Connectors](connectors.md)). Realtime exposes no direct device tool or command/result frame. Session history seeding, complete voice/text task steering and cross-process recovery still have implementation gaps.

Within `tidb-link.realtime.v1`, added events and optional fields are compatible additions; clients should tolerate unknown server event types and fields. Removing an event or changing its meaning requires a new subprotocol version, with one explicit retirement exception: the canceled direct device path removes `device.command`, `device.command_result` and active `device_ack` under v1. Existing clients must stop sending device results and use Full Agent task delegation for device work. Persisted historical `device_ack` timeline entries remain readable; they do not authorize an active frame.

## Usage and trying voice in Console

An ended Realtime Connection produces one usage fact with `requestPurpose: voice_realtime`, `sessionId`, `realtimeConnectionId` and a null `turnId`. The Organization backend reads it through `GET /api/v1/org/users/{userId}/billing/usage/details`. Voice rates and cost are currently unknown (`no_rate_authority`); unknown cost is not zero.

Template Playground can test voice against the complete frozen Test content and selected Full Agent model. Ending the call keeps the Test open. External tools, private files and state reads remain unavailable. Task progress or a send attempt alone does not prove a physical action. Customer applications use the User-Key routes in this guide for their ordinary Sessions.
