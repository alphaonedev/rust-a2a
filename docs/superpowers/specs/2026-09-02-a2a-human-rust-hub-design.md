# a2a-human-rust-hub — Design Spec

Date: 2026-09-02
Status: draft, awaiting operator review (rev 4: universal join, TLS, signed join/depart, A2A wake)
Repo (intended public): `github.com/alphaonedev/a2a-human-rust-hub`
Local path: `/Users/fate/a2a-human-rust-hub`

## Goal

A super-lightweight Rust daemon on this Mac that is the hive’s communications hub:

1. **Agent plane (fast, universal):** any AI or agent that can spawn a process (or speak JSON lines) can join. The hub has **no vendor types**. Join is `a2a pair --id <any-name>` then `a2a watch`. Transport is TLS (WSS) even on loopback. Recipients are **always pushed** a wake when they have a new frame — they never poll. A2A never uses natural language on the wire.
2. **Human plane (Telegram, 1:1 and groups):** biologic humans talk to the hive in natural language via a Telegram bot ([teloxide](https://github.com/teloxide/teloxide)). A DM is 1:1 with one human. A Telegram group is a named hive topic so several humans and the whole agent roster share one bidirectional room. English (or any human language) lives **in the payload**. The hub does not interpret it. The destination agent already is an LLM; it does the understanding.

There is **no OpenRouter (or any other) model inside the hub**. Slash commands pick the destination. Plain text uses a deterministic default. A2A never touches a model.

Success for v1: two unnamed processes round-trip a `request`/`reply` over WSS in well under 50 ms; a third process with a different `--id` joins the same way; disconnect vs depart are distinct; an offline recipient is woken on reconnect with a `wake` then queued frames; a human in a Telegram DM and in a bound group both reach the hive. Only secret: `TELEGRAM_BOT_TOKEN`. Hub TLS material is local files, not a vendor CA.

## Locked decisions

Taken during brainstorming, 2026-09-02:

| Decision | Choice |
|---|---|
| Planes | Dual: Telegram for humans, compact push fabric for agents |
| Agent codec | Hub-native compact frames, length-prefixed CBOR |
| Deployment | This Mac, invite-only |
| Telegram transport | Long-polling (no public webhook) |
| Agent transport | **WSS** (`wss://127.0.0.1:7422/v1`), rustls, hub-issued cert, TOFU pin |
| LLM | **None in v1.** |
| Join / leave | Signed `join` (pending code + owner `/pair`) and signed `depart` (membership gone). Disconnect ≠ depart. |
| A2A notify | Push + mandatory `wake` to the recipient. No polling. Offline queue then `wake` on reconnect. |
| Join model | Telegram user-id allowlist + Ed25519 agent-key allowlist. **No agent-type registry.** |
| Human rooms | Telegram DM = 1:1; Telegram group = bound hive topic |
| Agent types | None in the protocol. Any name. One sidecar: JSON lines. |
| Intended GitHub | `alphaonedev/a2a-human-rust-hub` (create after spec approval) |

## Non-goals (v1)

- Public internet bind or VPS (still loopback). TLS **is** in v1, on localhost.
- Linux Foundation A2A / JSON-RPC compatibility (possible later gateway)
- Inventing a spoken “AI language” (Lojban, embeddings-as-speech, etc.)
- Multi-tenancy, billing, or a marketplace of agents
- Vendor SDKs or an `agent_kind` enum inside the daemon
- Using Telegram as the A2A data plane (Telegram is human-only)
- Any LLM, OpenRouter, or “orchestrator” process in the daemon
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
 Humans (Telegram)              This Mac daemon                         Agents
  DM 1:1  \                     a2a-hub                                 (any type)
  group   /-- long-poll --> [teloxide] --> [commands] --> [router]
                                                              |
                                                              +-- [wss://127.0.0.1:7422] -- any process
                                                                                  (`a2a pair --id NAME`
                                                                                   `a2a watch`)
```

Units (each has one job, a typed interface, and can be tested without Telegram):

| Unit | Does | Depends on |
|---|---|---|
| `frame` | Envelope types, CBOR encode/decode, length prefix | none |
| `identity` | Ed25519 keys, Telegram ids, allowlists, pairing codes | `frame` ids only |
| `router` | Subscribe, unsubscribe, route, presence, offline queue | `frame`, `identity` |
| `ws_plane` | Accept local **WSS**, TLS pin, join/depart, push+wake, drop | `router` |
| `tg_plane` | teloxide long-poll, slash commands, send/receive text | `router`, `commands` |
| `commands` | Parse `/ask` `/say` `/who` `/group` and plain-text defaults | `frame` |
| `config` | TOML + env, bind addresses, owner id | none |

The daemon **owns** membership, TLS, routing, and push. Agents hold one WSS socket. When a frame is for them, the hub writes it **and** a `wake`. Recipients never poll.

## Universal join (any AI)

The hub has no vendor types and no roster. Grok, Claude, Hermes, OpenClaw, IronClaw, Codex, a Python script, and a future unknown agent all join the same way:

```
a2a pair --id <any-unique-name>
# prints a 6-char code; owner in Telegram DM: /pair CODE
a2a watch --id <same-name>
```

If it can run a binary, it can join. `--id` is just a string.

Sidecar ↔ agent is JSON lines (universal). Sidecar ↔ hub is TLS + CBOR (fast).

Each inbound A2A frame is **two** stdout lines so the recipient cannot miss new mail:

```json
{"t":"wake","id":"...","from":"alice","kind":"request","pending":1}
{"t":"frame","id":"...","from":"alice","to":"bob","kind":"request","schema":1,"text":"..."}
```

Send on stdin:

```json
{"to":"alice","kind":"reply","corr":"...","text":"ok"}
```

Optional: `a2a-mcp` (`a2a_send`, `a2a_who`) for MCP runtimes. Push still requires `a2a watch`. Native WSS+CBOR is allowed; same join/depart/wake rules.

Rules: one live socket per `agent_id` (second connect kicks the first). Agents never join via Telegram. No vendor keys in the hub.

## Agent-plane protocol

### Transport

- Bind: `127.0.0.1:7422` (configurable). **Loopback only.**
- Scheme: `wss://127.0.0.1:7422/v1` (TLS 1.3, rustls).
- First hub start writes `~/.a2a-hub/tls/` (local CA + server cert). Clients store `~/.a2a-hub/hub.pin` (SHA-256 of the server cert) on first connect (TOFU). Pin mismatch is a hard fail.
- No plaintext HTTP port. Join and depart are signed frames on this WSS.
- One connection per `agent_id`. Second connect replaces the first (`error/replaced`).
- Heartbeat: hub `ping` every 15 s; no `pong` in 45 s → drop (session leave, **not** depart).

### Handshake, join, depart

**Session (already a member):**

1. Client opens WSS (pin check).
2. Hub sends `kind=challenge` with 32-byte nonce.
3. Client sends `kind=hello` `{ agent_id, pubkey, sig(nonce), subscriptions }`.
4. Hub verifies allowlist + signature. Else `error/unauthorized` and close.
5. Hub sends `kind=welcome` `{ session_id, server_ts }`.
6. If the offline queue is non-empty, hub first sends `kind=wake` `{ pending: N }`, then replays queued frames, each preceded by a `wake`.

**Secure join (not yet a member):**

1. `a2a pair --id NAME` opens WSS (TOFU pin), then `kind=join` `{ agent_id, pubkey }` signed by that key.
2. Hub stores pending `{ code, agent_id, pubkey, expires }`, replies `kind=join_pending` `{ code, expires_in_s=600 }`.
3. Owner Telegram DM: `/pair CODE`. Hub moves pending → allow-agents.
4. If that socket is still up, hub sends `welcome`; otherwise the agent runs `a2a watch`.

**Session leave** (temporary): drop the socket or omit pong. Presence offline. Offline queue kept. Reconnect with `hello` — no new `/pair`.

**Secure depart** (membership ends):

1. `a2a depart --id NAME` on a live session sends `kind=depart` signed over the latest nonce.
2. Hub deletes allow-agents row, flushes queue, replies `kind=departed`, closes TLS.
3. Owner `/revoke NAME` is the same action from the human side.
4. Rejoin requires a new `a2a pair` and `/pair CODE`.

### A2A wake (always notify the recipient)

The A2A plane never silently accepts a frame.

- Every frame routed to an online agent is pushed immediately. Immediately before that frame the hub sends `kind=wake` `{ id, from, kind, pending: 1 }`. The sidecar prints the wake JSON line first, then the frame line.
- Every frame routed to an offline agent is enqueued (bound 32 / 5 min). No poll. On next `welcome` they get `wake { pending: N }` then the queue.
- `request`, `reply`, and `notify` always generate a wake. `ping`/`pong` do not.
- Dropping a frame (ttl, unauthorized, too large, unknown dest) sends `kind=error` to the **sender**, never a fake success.
- Recipients do not call an inbox API. Holding `a2a watch` **is** being notified.

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
  Agent(agent_id: string)      // any unique name the joiner chose
  Human(telegram_user_id: u64)
  Topic(name: string)          // "hive", "alpha", "ops"
  Hub                          // daemon itself

Kind = challenge | hello | welcome | ping | pong
     | join | join_pending | depart | departed | wake
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
| 4 | `join` / `join_pending` | `{ agent_id, pubkey }` / `{ code, expires_in_s }` |
| 5 | `wake` | `{ id, from, kind, pending }` |

v1 does not ship a large schema catalog. Agents that need richer payloads pick a `schema` id they both know and put CBOR in `payload`. The hub routes bytes; it does not interpret unknown schemas.

### Routing rules

- `to=Agent(id)` → `wake` then frame on that socket, or offline queue if disconnected.
- `to=Topic(name)` → every subscriber except `from` gets `wake` then frame.
- `to=Human(uid)` → Telegram to that user if allowlisted; schema-1 copies to topic `human` subscribers (each gets a wake).
- `to=Hub` → daemon consumes (`ping`, `join`, `depart`, `subscribe`).
- `kind=request` must have `corr` on the `reply`. Hub does not RPC-block; it is a correlation convention.
- Expired `ttl_ms` frames are dropped, never queued.

Default topic every agent is subscribed to after welcome: `hive`.

### Offline queue

Per agent, 32 frames or 5 minutes, whichever first. Drop oldest. Queue is RAM only. Restart of the daemon loses it. That is accepted for v1.

### Agent CLI (same repo)

`a2a` binary:

```
a2a pair --id NAME          # TOFU pin + signed join; prints CODE
a2a watch --id NAME         # holds WSS; prints wake then frame JSON lines
a2a send --id NAME --to DEST --kind notify --text '...'
a2a depart --id NAME        # signed depart; must re-pair to return
```

`watch` **is** A2A notification. Any AI that can spawn it is in the hive. Wire stays CBOR+TLS; the process sees JSON.

## Human plane (Telegram 1:1 and groups)

Library: `teloxide` 0.17, long-polling.

Env: `TELEGRAM_BOT_TOKEN`.

Owner: `config.owner_telegram_id`. First `/start` from any other user is ignored until the owner allowlists them.

Two human rooms, both bidirectional:

| Room | Telegram | Hub `Addr` | Who hears replies |
|---|---|---|---|
| 1:1 | DM with the bot | `Human(telegram_user_id)` | Only that user |
| Group | Bot is a member of an allowlisted group | `Topic(name)` bound to that `chat_id` | The group (and any agent subscribed to that topic) |

### 1:1 (DM)

Allowlisted human DMs the bot. Slash commands work. Plain text → `dm_default_topic`. Agent `to=Human(uid)` delivers only to that DM.

### Groups

A Telegram group is **not** automatically the hive. The owner must bind it.

1. Add the bot to the group.
2. Owner, **in that group**: `/group bind <topic>` e.g. `/group bind ops`.
3. Hub stores `{ chat_id, topic, require_mention: true }`.
4. Inbound group messages become `notify`/`request` with `from=Human(uid)` and `to=Topic(topic)` if the sender is allowlisted.
5. Outbound: any frame `to=Topic(topic)` with `schema=1` is also posted into that Telegram group (chunked). Binary/unknown schema: one-line receipt, same as DM.

Default `require_mention = true`: the bot only consumes group messages that `@mention` it or that reply to it. This is the prompt-injection / noise control. Owner can `/group mention off` in that group.

Unallowlisted group members are ignored even if they mention the bot. Owner `/allow <id>` from a DM (not from the group, to avoid “approve me” social engineering in public text).

One Telegram group ↔ one topic. Two groups cannot bind the same topic. Unbind: `/group unbind` in the group.

`/say ops hello` from a DM still publishes to topic `ops` and therefore to the bound group. Agents subscribed to `ops` get the CBOR frame. Humans in the group see the English line.

The special topic `hive` may be bound to a “war room” group. It is also the default agent subscription, so that group sees hive-wide schema-1 traffic. Do not bind `hive` to a large noisy group.

### Commands

| Command | Where | Who | Effect |
|---|---|---|---|
| `/start` | DM | anyone | If allowlisted, hello + presence. Else “ask the owner.” |
| `/who` | DM or group | allowlisted | List humans, groups, connected agents |
| `/allow <telegram_id>` | DM only | owner | Add human |
| `/deny <telegram_id>` | DM only | owner | Remove human |
| `/pair <CODE>` | DM only | owner | Promote pending agent key to allowlist |
| `/revoke <agent_id>` | DM only | owner | Drop allowlist + kick socket |
| `/group bind <topic>` | that group | owner | Bind group ↔ topic, mention-required |
| `/group unbind` | that group | owner | Drop binding |
| `/group mention on\|off` | that group | owner | Toggle require-mention |
| `/say <topic> <text>` | DM or group | allowlisted | Publish `notify` `schema=1` to that topic |
| `/ask <agent_id> <text>` | DM or group | allowlisted | `request` to one agent, `schema=1`; reply comes back to the same room |
| (plain text) | DM | allowlisted | `notify` `schema=1` to `dm_default_topic` (default `hive`) |
| (plain text) | group, mention rules pass | allowlisted | `notify` `schema=1` to the group’s bound topic |

`corr` on `/ask` from a group stores `reply_to = group chat_id` so the agent’s `reply` lands in the group, not in the owner’s DM.

The hub never parses the English. `/ask grok-build summarize the alpaca screen` sets `to=Agent(grok-build)` and puts the rest of the line in `payload`. Grok Build’s own model does the work.

Replies to humans: if `schema=1`, send `payload` as Telegram text (chunked at 3500). If `schema≠1`, send a one-line receipt `from={id} kind={kind} schema={n} {n}B`. No model.

Telegram is never used to carry CBOR, keys, or raw frames. Agents never get a Telegram identity.

## Identity, pairing, config

### Files

```
~/.a2a-hub/
  config.toml
  tls/                 # hub CA + server cert (created on first start)
  hub.pin              # SHA-256 of server cert; written by first successful client TOFU
  allow-humans.json
  allow-agents.json    # [{ agent_id, pubkey_hex }]
  pending-agents.json  # [{ code, agent_id, pubkey_hex, expires_unix }]
  groups.json
  keys/<agent_id>.key  # sidecar private key per --id
```

`config.toml`:

```toml
bind_ws = "127.0.0.1:7422"
owner_telegram_id = 0          # required
dm_default_topic = "hive"
log = "info"
```

Secrets only in env: `TELEGRAM_BOT_TOKEN`. TLS material is local files. No model API key.

### Pairing an agent

See **Handshake, join, depart** above. There is no HTTP control port.

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

**A2A request:** agent A `request` → router → B gets `wake` then the frame → B `reply` (`corr=A.id`) → A gets `wake` then the reply. TLS the whole way. No Telegram, no model.

**A2A depart:** `a2a depart --id bob` → signed `depart` → allowlist row gone, queue flushed, socket closed. `a2a watch --id bob` then fails until a new `/pair`.

**Human 1:1:** `/ask grok-build status` from a DM → `request` to `grok-build` → reply `schema=1` → that DM.

**Human group:** allowlisted human in bound group `ops` mentions the bot with `/ask hermes show the log line` → `request` to `hermes` → reply returns to **that group**. Bare mentioned text becomes `notify` on `ops` (no agent targeting without `/ask`).

**Human broadcast:** `/say hive status?` → topic `hive` → all agent sockets + the Telegram group bound to `hive` if any.

**A2A any-to-any:** `--id openclaw` `request` to `--id claude-code` is one CBOR frame on WSS. The hub does not know those names. No Telegram, no model, no vendor SDK.

**Presence:** router tracks connected agent_ids and bound groups. `/who` is local.

## Error handling

- Telegram API errors: log, retry send 3× with backoff, then drop that outbound.
- Long-poll drop: teloxide reconnects; hub state unchanged.
- WSS client drop: presence offline, start offline queue (leave, not depart).
- TLS pin mismatch: client refuses to connect; log a clear error.
- Signed `depart` with a bad sig: `error/unauthorized`, membership unchanged.
- Hub process crash: systemd/launchd restarts; RAM queues lost; allowlists on disk survive.
- Malformed CBOR: close that socket.
- Unknown `/ask` dest: Telegram “no such agent” (from presence/allowlist), no network call.

## Security

- Loopback bind only.
- TLS 1.3 on the agent plane; TOFU cert pin; pin mismatch fails closed.
- Invite-only allowlists. Join is signed; depart is signed; owner `/revoke` matches depart.
- Agent auth is signature of a per-session nonce, not a static bearer token.
- Private keys and TLS keys never on Telegram.
- Frame cap 64 KiB, 100 frames/s per agent.
- Owner-only for allow/deny/pair/revoke. Those commands are **DM-only** so a group member cannot social-engineer `/allow`.
- Groups default to require-mention. Unallowlisted senders are dropped.
- No LLM in-process, so there is no model-side prompt injection into routing. Group text cannot run `/allow` even if the sender is owner (owner uses DM).
- Destination comes only from slash args or the bound topic / `dm_default_topic`, never from parsing the payload.

## Testing

No live Telegram required for the core.

- `frame`: encode/decode roundtrip, reject >64 KiB, reject unknown `v`.
- `identity`: allowlist add/remove, pairing code expire, join/depart signature check.
- `router`: topic fanout excludes sender; offline queue bound 32; ttl drop; unknown dest → error to sender; every delivered request/notify/reply is preceded by a wake.
- `ws_plane`: rustls test client, reject unknown pin, reject hello without allow, accept join→pending, depart removes membership, kick on second connect.
- `commands`: `/ask` and `/say` produce the documented frames; plain DM → `dm_default_topic`; group plain → bound topic; unknown dest is an error.
- `tg_plane` group bind: one topic per chat_id; mention filter; unallowlisted member ignored.
- Optional `#[ignore]` integration: live Telegram, behind env flags.

## Tech stack (v1)

- Rust **1.96.0** (this node’s active toolchain). rust-version = "1.96". Edition 2024.
  - Operator asked for 1.98; it is not installed here (`rustc 1.96.0 (ac68faa20 2026-05-25)`). Do not block on 1.98. Bump `rust-version` when 1.98 is current.
- tokio, tokio-tungstenite, tokio-rustls, rustls, rcgen, ciborium, serde, uuid (v7), ed25519-dalek, teloxide 0.17, toml, tracing
- No HTTP client, no OpenRouter, no Redis, no DB

## Repo layout (when implementation starts)

```
a2a-human-rust-hub/
  Cargo.toml                 # workspace
  crates/frame/              # types + codec
  crates/hub/                # daemon binary a2a-hub
  crates/a2a/                # CLI: pair / watch / send / depart
  crates/a2a-mcp/            # optional stdio MCP: a2a_send, a2a_who
  docs/adapters/             # one-pager: “run a2a pair && a2a watch” (not per-vendor code)
  docs/superpowers/specs/    # this file
  README.md
  LICENSE                    # Apache-2.0 OR MIT
```

Workspace keeps `frame` reusable by both binaries. One `Cargo.lock`.

## Implementation order (preview; full plan after spec approval)

1. `frame` crate + tests
2. `router` + `identity` in-process tests
3. `ws_plane` TLS + `a2a` CLI `pair`/`watch`/`send`/`depart` loopback test
4. `tg_plane` DM + group bind against a fake bot (teloxide testing hooks or a thin trait)
5. `commands` parser tests (no HTTP)
6. `a2a-mcp` optional; one generic adapter page (any `--id`)
7. README, config example, launchd plist optional
8. Public GitHub `alphaonedev/a2a-human-rust-hub`

## Success criteria

- `a2a watch` in two terminals: `send` from one appears in the other as **wake then frame**, no polling.
- Third process `a2a pair --id anything`; owner `/pair`; it joins. Hub has no special case for that name.
- `a2a depart --id anything` then `watch` is unauthorized until a new pair.
- TLS pin mismatch refuses connect.
- Offline recipient reconnects, gets `wake {pending:N}` then queued frames.
- Non-owner Telegram user cannot `/allow`.
- `/say hive hello` reaches connected agents as schema-1 notify.
- Bound Telegram group round-trips schema-1 to/from topic `ops`; unbound groups are ignored.
- Unallowlisted group member is dropped even with a mention.
- `/allow` in a group is rejected; it works only in owner DM.
- DM plain text lands on `hive` (or `dm_default_topic`) as schema-1 notify, no HTTP.
- `/ask grok-build …` from a group returns the reply to that group.
- Agent-to-agent path does not open any HTTP client. The hub has no model client.
- `cargo test` green with no network.

## Open questions (non-blocking)

None that block v1. Optional later: LF-A2A gateway, QUIC, VPS bind, durable log, first-party Grok Bot / OpenClaw plugins, an optional NL router if humans refuse slash commands (not v1).

## Out of scope reminders

Do not put secrets in the repo. Do not scrape Telegram. Do not auto-create the public GitHub repo until the operator accepts this spec.
