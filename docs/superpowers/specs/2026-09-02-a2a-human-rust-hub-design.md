# a2a-human-rust-hub — Design Spec

Date: 2026-09-02
Status: draft, awaiting operator review
Repo (intended public): `github.com/alphaonedev/a2a-human-rust-hub`
Local path: `/Users/fate/a2a-human-rust-hub`

## Goal

A super-lightweight Rust daemon on this Mac that is the hive’s communications hub:

1. **Agent plane (fast):** any subscribed AI/agent is pushed typed compact frames over a persistent local WebSocket. Agents do not poll. A2A never uses natural language on the wire.
2. **Human plane (Telegram):** biologic humans talk to the hive in English (or any human language) via a Telegram bot ([teloxide](https://github.com/teloxide/teloxide)). The hub translates at the edge.
3. **Orchestration LLM (cold path only):** a cheap OpenRouter model turns human text into typed frames and typed frames into human text. Agent-to-agent traffic never touches a model unless a frame explicitly requests it.

Success for v1: a human in Telegram and two local agents can round-trip a `request`/`reply` in well under 50 ms on the agent plane, while the human sees a readable Telegram message. Disconnects, allowlists, and pairing work without a public IP.

## Locked decisions

Taken during brainstorming, 2026-09-02:

| Decision | Choice |
|---|---|
| Planes | Dual: Telegram for humans, compact push fabric for agents |
| Agent codec | Hub-native compact frames, length-prefixed CBOR |
| Deployment | This Mac, invite-only |
| Telegram transport | Long-polling (no public webhook) |
| Agent transport | WebSocket on `127.0.0.1` |
| LLM | OpenRouter, NL edge only |
| Join model | Telegram user-id allowlist + Ed25519 agent-key allowlist |
| Intended GitHub | `alphaonedev/a2a-human-rust-hub` (create after spec approval) |

## Non-goals (v1)

- Public internet listener, TLS termination, or VPS deploy
- Linux Foundation A2A / JSON-RPC compatibility (possible later gateway)
- Inventing a spoken “AI language” (Lojban, embeddings-as-speech, etc.)
- Multi-tenancy, billing, or a marketplace of agents
- Putting Grok Bot’s cloud computer on this fabric (local agents only)
- Using Telegram as the A2A data plane
- Running OpenRouter on every hop
- Durable disk log of all frames (in-memory + bounded offline queue only)

## Why not natural language for A2A

Natural language is the right interface for humans. It is the wrong **wire format** for agents.

- Generation cost dominates: tens to hundreds of milliseconds per token, plus sampling noise.
- Ambiguity: no typed errors, no schema, no idempotency keys.
- Cannot multiplex, expire, or authorize at the frame level without wrapping it anyway.
- Models are trained on English, not on a made-up compact spoken language — a new “AI tongue” would be **slower** and worse.

What agents actually need is not a language. It is an **envelope**:

- who, to whom, kind, correlation id, schema id, ttl, payload bytes
- a compact codec
- a push socket so the receiver is woken

Linux Foundation [A2A](https://github.com/a2aproject/A2A) is the closest *universal* standard (Agent Cards, tasks, JSON-RPC, now gRPC). It is still heavy for a laptop daemon. v1 speaks a smaller native envelope. An A2A gateway can be added later without changing the hive core.

CBOR (IETF 8949) is the v1 codec: compact, binary, schema-flexible, has Python/JS/Go libraries so a non-Rust agent on this Mac can join. Postcard is faster but Rust-only. Protobuf is more ceremony than v1 needs.

## Architecture

One tokio process. Three faces, one router.

```
 Humans                         This Mac daemon                         Agents
 (Telegram)                     a2a-hub                                 (WS + CBOR)
     |                               |                                      |
     |  Bot API long-poll            |                                      |
     v                               v                                      v
 [teloxide] --> [nl-edge] --> [router / pubsub] <-- [ws-server 127.0.0.1:7422]
                     |                |
                     |                +--> allowlists, pairing, presence
                     v
              OpenRouter (only if the
              inbound is human text
              that is not a slash command)
```

Units (each has one job, a typed interface, and can be tested without Telegram or OpenRouter):

| Unit | Does | Depends on |
|---|---|---|
| `frame` | Envelope types, CBOR encode/decode, length prefix | none |
| `identity` | Ed25519 keys, Telegram ids, allowlists, pairing codes | `frame` ids only |
| `router` | Subscribe, unsubscribe, route, presence, offline queue | `frame`, `identity` |
| `ws_plane` | Accept local WS, handshake, push, drop | `router` |
| `tg_plane` | teloxide long-poll, slash commands, send/receive text | `router`, `nl_edge` |
| `nl_edge` | Slash-parse first; else OpenRouter text↔frame | `frame` |
| `config` | TOML + env, bind addresses, owner id, model name | none |

The daemon **owns** joined-user monitoring, channel membership, and push. Agents hold one WebSocket. When a frame is for them, the hub writes it. That is the notification. There is no inbox polling API in v1.

## Agent-plane protocol

### Transport

- Bind: `127.0.0.1:7422` (configurable).
- Scheme: `ws://127.0.0.1:7422/v1`.
- No TLS in v1 (loopback only).
- One connection per agent identity. Second connect with the same key replaces the first (kick with `error/replaced`).
- Heartbeat: hub sends `ping` every 15 s; no `pong` in 45 s → drop.

### Handshake

1. Client opens WS.
2. Hub sends `kind=challenge` with 32-byte nonce.
3. Client sends `kind=hello` payload: `{ agent_id, pubkey, sig(nonce), subscriptions: [topic] }`.
4. Hub verifies: pubkey on allowlist (or pending pairing), signature valid, `agent_id` matches key.
5. Hub sends `kind=welcome` `{ session_id, server_ts }`.
6. Hub replays offline queue for that agent (bounded, see below).

Unknown keys on the WebSocket are rejected with `error/unauthorized` and the socket is closed. New agents join through the loopback pairing port first (`POST /v1/pending`), then the owner `/pair CODE` in Telegram, then `a2a watch` succeeds.

### Frame

Length-prefixed CBOR. Max frame 64 KiB.

```
u32be body_len | cbor(Frame)
```

```text
Frame {
  v:        u8        // 1
  id:       [u8; 16]  // uuid v7
  corr:     Option<[u8; 16]>
  from:     Addr
  to:       Addr
  kind:     Kind
  schema:   u16       // 0 = empty / well-known kind payload
  ts_ms:    u64       // unix ms
  ttl_ms:   u32       // 0 = no expire
  payload:  bytes     // CBOR of the schema, or empty
}

Addr =
  Agent(agent_id: string)      // "grok-build", "fable", "worker-1"
  Human(telegram_user_id: u64)
  Topic(name: string)          // "hive", "alpha", "ops"
  Hub                          // daemon itself

Kind = challenge | hello | welcome | ping | pong
     | subscribe | unsubscribe
     | notify | request | reply | error
```

Well-known `schema` values in v1:

| schema | meaning | payload |
|---|---|---|
| 0 | none | empty |
| 1 | `text` | CBOR string (only used when an agent *asks* to speak to a human) |
| 2 | `hello` | `{ agent_id, pubkey, sig, subscriptions }` |
| 3 | `error` | `{ code: u16, msg: string }` |
| 4 | `pair_offer` | `{ code: string, agent_id, pubkey }` |

v1 does not ship a large schema catalog. Agents that need richer payloads pick a `schema` id they both know and put CBOR in `payload`. The hub routes bytes; it does not interpret unknown schemas.

### Routing rules

- `to=Agent(id)` → that socket, or offline queue if disconnected.
- `to=Topic(name)` → every subscriber of that topic except `from`.
- `to=Human(uid)` → Telegram send to that user if allowlisted; also copied to topic `human` subscribers as a `notify` with `schema=1` only if the agent set `schema=1`.
- `to=Hub` → daemon consumes (`ping`, `subscribe`, pairing).
- `kind=request` must have `corr` on the `reply`. Hub does not RPC-block; it is a correlation convention.
- Expired `ttl_ms` frames are dropped, never queued.

Default topic every agent is subscribed to after welcome: `hive`.

### Offline queue

Per agent, 32 frames or 5 minutes, whichever first. Drop oldest. Queue is RAM only. Restart of the daemon loses it. That is accepted for v1.

### Agent CLI (same repo)

`a2a` binary (or `a2a-hub` subcommands):

```
a2a keygen                  # writes ~/.a2a-hub/agent.key
a2a pair                    # prints 6-char code; waits until allowlisted
a2a watch [--topics hive]   # holds WS, prints frames as JSON on stdout
a2a send --to hive --kind notify --text '...'
a2a send --to grok-build --kind request --schema 0
```

`watch` is the notification mechanism for any AI that can run a subprocess (Grok Build, Grok Bot local-exec, scripts). Stdout is JSON for easy ingestion; the **wire** stays CBOR.

## Human plane (Telegram)

Library: `teloxide` 0.17, long-polling.

Env: `TELEGRAM_BOT_TOKEN`.

Owner: `config.owner_telegram_id`. First `/start` from any other user is ignored until the owner allowlists them.

### Commands

| Command | Who | Effect |
|---|---|---|
| `/start` | anyone | If allowlisted, hello + presence. Else “ask the owner.” |
| `/who` | allowlisted | List humans and connected agents |
| `/allow <telegram_id>` | owner | Add human |
| `/deny <telegram_id>` | owner | Remove human |
| `/pair <CODE>` | owner | Promote pending agent key to allowlist |
| `/revoke <agent_id>` | owner | Drop allowlist + kick socket |
| `/say <topic> <text>` | allowlisted | Publish `notify` `schema=1` to that topic **without** OpenRouter |
| `/ask <agent_id> <text>` | allowlisted | `request` to one agent, `schema=1` |
| (plain text) | allowlisted | NL edge (OpenRouter) → typed frame |

Plain text that is not a command is the only path that may call OpenRouter.

Replies from the hive to a human are Telegram messages, chunked at 3500 characters.

Telegram is never used to carry CBOR, keys, or raw frames.

## NL edge (OpenRouter)

Env: `OPENROUTER_API_KEY`.

Config: `orchestrator.model` (default `openai/gpt-4o-mini` — cheap, replaceable). `orchestrator.timeout_ms = 15000`.

The model sees a **fixed JSON schema** and must return JSON only:

```json
{
  "to": { "type": "agent|topic|human", "id": "..." },
  "kind": "notify|request",
  "schema": 1,
  "text": "...",
  "say_to_human": "optional short ack to send back on Telegram"
}
```

System prompt (short, in-repo, not a secret): you are a translator, not an agent. Map the human’s sentence onto one frame. Do not answer the question yourself. Do not invent allowlist changes. If the sentence is a greeting or “who is online”, return JSON with `"to":{"type":"topic","id":"hive"}`, `"kind":"notify"`, and a `say_to_human` of a one-line ack — presence itself is still answered by `/who` without the model.

If OpenRouter fails: Telegram “translator unavailable; use /say or /ask.”

Agent → human: if `schema=1`, send `payload` string to Telegram. If `schema≠1`, send a one-line receipt `from={id} kind={kind} schema={n} {n}B` — no model. A human who wants a translation can `/ask` a designated translator agent later. v1 does not auto-LLM agent payloads.

## Identity, pairing, config

### Files

```
~/.a2a-hub/
  config.toml
  owner.key            # optional, hub’s own Ed25519 (for future signed presence)
  allow-humans.json    # [u64]
  allow-agents.json    # [{ agent_id, pubkey_hex }]
  pending-agents.json  # [{ code, agent_id, pubkey_hex, expires_unix }]
  agent.key            # for the CLI when used as an agent
```

`config.toml`:

```toml
bind_ws = "127.0.0.1:7422"
owner_telegram_id = 0          # required
log = "info"

[orchestrator]
model = "openai/gpt-4o-mini"
timeout_ms = 15000
```

Secrets only in env: `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`.

### Pairing an agent

1. `a2a pair` loads or creates `~/.a2a-hub/agent.key`, then `POST http://127.0.0.1:7423/v1/pending` with `{agent_id, pubkey}` → `{code, expires_in_s=600}`.
2. Owner in Telegram: `/pair CODE`.
3. `a2a watch` then completes the WebSocket handshake.

Control port is loopback-only. It does not accept frames. It exists so a process on this Mac can ask to join without already being allowlisted.

### Error codes

| code | meaning |
|---|---|
| 401 | unauthorized |
| 404 | unknown dest |
| 409 | replaced session |
| 410 | expired |
| 413 | frame too large |
| 429 | slow down (per-agent 100 frames/s) |
| 500 | hub internal |

## Data flow (happy paths)

**A2A request:** agent A `request` → router → agent B socket write → B `reply` with `corr=A.id` → A socket write. No Telegram, no OpenRouter.

**Human broadcast:** `/say hive status?` → router `notify` topic `hive` schema 1 → all agent sockets. Telegram ack “sent to hive (N agents).”

**Human NL:** “tell grok-build to summarize the last alpaca screen” → nl-edge → `{to: agent grok-build, kind: request, text: ...}` → grok-build `watch` prints JSON → grok-build (or a wrapper) replies → if schema 1, Telegram gets the text.

**Presence:** router tracks connected agent_ids. `/who` is local.

## Error handling

- Telegram API errors: log, retry send 3× with backoff, then drop that outbound.
- Long-poll drop: teloxide reconnects; hub state unchanged.
- WS client drop: presence offline, start offline queue.
- Hub process crash: systemd/launchd restarts; RAM queues lost; allowlists on disk survive.
- Malformed CBOR: close that socket.
- OpenRouter timeout: user-visible, no retry storm (one retry).

## Security

- Loopback bind only.
- Invite-only allowlists.
- Agent auth is signature of a per-session nonce, not a static bearer token on the wire after hello.
- Private keys never on Telegram.
- Control port 7423 is loopback only.
- Frame cap 64 KiB, 100 frames/s per agent.
- Owner-only for allow/deny/pair/revoke.
- Prompt-injection: OpenRouter output is parsed as JSON schema; unknown fields ignored; `to` must resolve to an allowlisted dest or the frame is dropped. The model cannot grant allowlist changes.
- Telegram channel messages cannot run `/allow` unless sender is owner (teloxide handler checks id).

## Testing

No live Telegram or OpenRouter required for the core.

- `frame`: encode/decode roundtrip, reject >64 KiB, reject unknown `v`.
- `identity`: allowlist add/remove, pairing code expire, signature check.
- `router`: topic fanout excludes sender; offline queue bound 32; ttl drop; unknown dest → error frame to sender.
- `ws_plane`: in-process tungstenite client, handshake fail without allow, kick on second connect.
- `nl_edge`: slash commands never call the HTTP client (inject a panic stub); JSON parse reject.
- Optional `#[ignore]` integration: live Telegram, live OpenRouter, behind env flags.

## Tech stack (v1)

- Rust **1.96.0** (this node’s active toolchain). rust-version = "1.96". Edition 2024.
  - Operator asked for 1.98; it is not installed here (`rustc 1.96.0 (ac68faa20 2026-05-25)`). Do not block on 1.98. Bump `rust-version` when 1.98 is current.
- tokio, tokio-tungstenite, ciborium, serde, uuid (v7), ed25519-dalek, teloxide 0.17, reqwest, toml, tracing
- No Redis, no DB, no extra runtime

## Repo layout (when implementation starts)

```
a2a-human-rust-hub/
  Cargo.toml                 # workspace
  crates/frame/              # types + codec
  crates/hub/                # daemon binary a2a-hub
  crates/a2a/                # CLI client
  docs/superpowers/specs/    # this file
  README.md
  LICENSE                    # Apache-2.0 OR MIT
```

Workspace keeps `frame` reusable by both binaries. One `Cargo.lock`.

## Implementation order (preview; full plan after spec approval)

1. `frame` crate + tests
2. `router` + `identity` in-process tests
3. `ws_plane` + `a2a` CLI `watch`/`send` loopback test
4. `tg_plane` slash commands against a fake bot (teloxide has testing hooks) or a thin trait
5. `nl_edge` with mocked HTTP
6. README, config example, launchd plist optional
7. Public GitHub `alphaonedev/a2a-human-rust-hub`

## Success criteria

- `a2a watch` in two terminals: `send` from one appears in the other without polling.
- Owner `/pair` then third agent joins.
- Non-owner Telegram user cannot `/allow`.
- `/say hive hello` reaches connected agents as schema-1 notify.
- Plain-text Telegram path calls OpenRouter once and produces one frame.
- Agent-to-agent path does not open any HTTP client.
- `cargo test` green with no network.

## Open questions (non-blocking)

None that block v1. Optional later: LF-A2A gateway, QUIC, VPS bind, durable log, Grok Bot plugin.

## Out of scope reminders

Do not put secrets in the repo. Do not scrape Telegram. Do not auto-create the public GitHub repo until the operator accepts this spec.
