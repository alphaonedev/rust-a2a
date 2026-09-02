# a2a-human-rust-hub — Design Spec

Date: 2026-09-02
Status: draft, awaiting operator review (rev 3: no LLM in the hub)
Repo (intended public): `github.com/alphaonedev/a2a-human-rust-hub`
Local path: `/Users/fate/a2a-human-rust-hub`

## Goal

A super-lightweight Rust daemon on this Mac that is the hive’s communications hub:

1. **Agent plane (fast):** any subscribed AI or agent — Grok Bot, Hermes, OpenClaw, IronClaw, Claude Agent, Codex CLI, Claude Code CLI, Grok Build, and anything else that can hold a socket or spawn a sidecar — is pushed typed compact frames over a persistent local WebSocket. Agents do not poll. A2A never uses natural language on the wire. The hub does not embed vendor SDKs; every agent is the same identity + adapter.
2. **Human plane (Telegram, 1:1 and groups):** biologic humans talk to the hive in natural language via a Telegram bot ([teloxide](https://github.com/teloxide/teloxide)). A DM is 1:1 with one human. A Telegram group is a named hive topic so several humans and the whole agent roster share one bidirectional room. English (or any human language) lives **in the payload**. The hub does not interpret it. The destination agent already is an LLM; it does the understanding.

There is **no OpenRouter (or any other) model inside the hub**. Slash commands pick the destination. Plain text uses a deterministic default. A2A never touches a model.

Success for v1: two different agent types round-trip a `request`/`reply` in well under 50 ms with no model on the path; a human in a Telegram DM and a human in an allowlisted Telegram group both reach the hive and see replies. Disconnects, allowlists, and pairing work without a public IP. The daemon runs with only `TELEGRAM_BOT_TOKEN` as a secret.

## Locked decisions

Taken during brainstorming, 2026-09-02:

| Decision | Choice |
|---|---|
| Planes | Dual: Telegram for humans, compact push fabric for agents |
| Agent codec | Hub-native compact frames, length-prefixed CBOR |
| Deployment | This Mac, invite-only |
| Telegram transport | Long-polling (no public webhook) |
| Agent transport | WebSocket on `127.0.0.1` |
| LLM | **None in v1.** Humans address agents with `/ask` `/say` and deterministic plain-text defaults. Payload text is not parsed by the hub. |
| Join model | Telegram user-id allowlist + Ed25519 agent-key allowlist |
| Human rooms | Telegram DM = 1:1; Telegram group = bound hive topic |
| Agent types | Vendor-neutral adapters (sidecar CLI + optional MCP). Named roster below. |
| Intended GitHub | `alphaonedev/a2a-human-rust-hub` (create after spec approval) |

## Non-goals (v1)

- Public internet listener, TLS termination, or VPS deploy
- Linux Foundation A2A / JSON-RPC compatibility (possible later gateway)
- Inventing a spoken “AI language” (Lojban, embeddings-as-speech, etc.)
- Multi-tenancy, billing, or a marketplace of agents
- Vendor SDKs inside the daemon (no OpenClaw/Hermes/Grok Bot crates in `a2a-hub`)
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
                                                              +-- [ws 127.0.0.1:7422] -- Grok Build
                                                                                  -- Grok Bot
                                                                                  -- Claude Code / Agent
                                                                                  -- Codex
                                                                                  -- Hermes
                                                                                  -- OpenClaw
                                                                                  -- IronClaw
                                                                                  -- anything with a2a watch
```

Units (each has one job, a typed interface, and can be tested without Telegram):

| Unit | Does | Depends on |
|---|---|---|
| `frame` | Envelope types, CBOR encode/decode, length prefix | none |
| `identity` | Ed25519 keys, Telegram ids, allowlists, pairing codes | `frame` ids only |
| `router` | Subscribe, unsubscribe, route, presence, offline queue | `frame`, `identity` |
| `ws_plane` | Accept local WS, handshake, push, drop | `router` |
| `tg_plane` | teloxide long-poll, slash commands, send/receive text | `router`, `commands` |
| `commands` | Parse `/ask` `/say` `/who` `/group` and plain-text defaults | `frame` |
| `config` | TOML + env, bind addresses, owner id | none |

The daemon **owns** joined-user monitoring, channel membership, and push. Agents hold one WebSocket. When a frame is for them, the hub writes it. That is the notification. There is no inbox polling API in v1.

## Agent roster and adapters

The hub has **one** agent type: an Ed25519 key, an `agent_id` string, and a live WebSocket. Grok Bot vs Claude Code vs IronClaw is a **join recipe**, not a protocol fork.

Two official join methods (both in this repo):

| Adapter | When to use | Notify model |
|---|---|---|
| `a2a watch` sidecar | Any runtime that can spawn a local process | Holds WS; prints each inbound frame as one JSON line on stdout (wire remains CBOR). Optional `--exec <cmd>` runs a command per frame. |
| `a2a-mcp` stdio MCP | Runtimes that already load MCP (Grok Build, Claude Code, Codex, many others) | Tools: `a2a_send`, `a2a_who`. Push still requires the sidecar (MCP is request/response). Typical setup: sidecar always-on + MCP for in-session send. |

Python/JS/Go agents that do not want the CLI may speak CBOR-WS directly using the frame spec. That is supported; it is not a third first-party adapter.

Canonical `agent_id` values on this node (owner picks the string at `a2a pair`; these are the defaults):

| Roster name | `agent_id` | On this Mac now | Join recipe |
|---|---|---|---|
| Grok Build | `grok-build` | Yes (`~/.grok/bin/grok`) | Sidecar + optional MCP in `~/.grok/config.toml` |
| Grok Bot | `grok-bot` | Yes (`/Applications/Grok Bot.app`, local-exec daemon) | Local-exec or a Bot skill/routine runs `a2a watch`. Cloud computer is out of v1 (loopback only). |
| Claude Code CLI | `claude-code` | Yes (`/opt/homebrew/bin/claude`) | MCP in `~/.claude.json` + sidecar |
| Claude Agent | `claude-agent` | Claude.app present | Same as Claude Code if it shares MCP; else sidecar |
| Codex CLI | `codex` | Config at `~/.codex` (binary not on PATH at spec time) | MCP under Codex + sidecar once `codex` is on PATH |
| Hermes (Nous) | `hermes` | Not installed | Sidecar, or a Hermes skill that opens WS. Hermes already speaks Telegram as a *human* channel — that stays theirs; hive A2A is this hub. |
| OpenClaw | `openclaw` | Not installed | Sidecar or an OpenClaw plugin/tool that holds WS to `127.0.0.1:7422`. Do not dual-use OpenClaw’s own Telegram channel as the A2A bus. |
| IronClaw | `ironclaw` | Not installed | Sidecar if the TEE runtime can open a loopback WS; otherwise a tiny host adapter process outside the TEE that bridges frames. |

Unknown future agents: `a2a pair --id <name>` then `/pair CODE`. No hub change.

Rules:

- One live socket per `agent_id`. Two Claude Code sessions must use `claude-code-1` / `claude-code-2` or they kick each other.
- Agents never join via Telegram. Telegram identities are humans only. An agent that already has its own Telegram bot (Hermes, OpenClaw) is still a **WS subscriber** here; we do not merge those bots into this bot.
- No vendor API keys in the hub. Each agent keeps its own credentials.

## Human plane (Telegram 1:1 and groups)

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

Library: `teloxide` 0.17, long-polling.

Env: `TELEGRAM_BOT_TOKEN`.

Owner: `config.owner_telegram_id`. First `/start` from any other user is ignored until the owner allowlists them.

Two human rooms, both bidirectional:

| Room | Telegram | Hub `Addr` | Who hears replies |
|---|---|---|---|
| 1:1 | DM with the bot | `Human(telegram_user_id)` | Only that user |
| Group | Bot is a member of an allowlisted group | `Topic(name)` bound to that `chat_id` | The group (and any agent subscribed to that topic) |

### 1:1 (DM)

Unchanged from rev 1. Allowlisted human DMs the bot. Slash commands work. Plain text goes through NL edge. Agent `to=Human(uid)` delivers only to that DM.

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
  owner.key            # optional, hub’s own Ed25519 (for future signed presence)
  allow-humans.json    # [u64]
  allow-agents.json    # [{ agent_id, pubkey_hex }]
  pending-agents.json  # [{ code, agent_id, pubkey_hex, expires_unix }]
  groups.json          # [{ chat_id, topic, require_mention }]
  agent.key            # per-agent; `a2a pair --id grok-build` uses ~/.a2a-hub/keys/grok-build.key
```

`config.toml`:

```toml
bind_ws = "127.0.0.1:7422"
bind_control = "127.0.0.1:7423"
owner_telegram_id = 0          # required
dm_default_topic = "hive"
log = "info"
```

Secrets only in env: `TELEGRAM_BOT_TOKEN`. No model API key.

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

**Human 1:1:** `/ask grok-build status` from a DM → `request` to `grok-build` → reply `schema=1` → that DM.

**Human group:** allowlisted human in bound group `ops` mentions the bot with `/ask hermes show the log line` → `request` to `hermes` → reply returns to **that group**. Bare mentioned text becomes `notify` on `ops` (no agent targeting without `/ask`).

**Human broadcast:** `/say hive status?` → topic `hive` → all agent sockets + the Telegram group bound to `hive` if any.

**A2A across vendors:** `openclaw` `request` to `claude-code` is one CBOR frame. No Telegram, no OpenRouter, no vendor SDK.

**Presence:** router tracks connected agent_ids and bound groups. `/who` is local.

## Error handling

- Telegram API errors: log, retry send 3× with backoff, then drop that outbound.
- Long-poll drop: teloxide reconnects; hub state unchanged.
- WS client drop: presence offline, start offline queue.
- Hub process crash: systemd/launchd restarts; RAM queues lost; allowlists on disk survive.
- Malformed CBOR: close that socket.
- Unknown `/ask` dest: Telegram “no such agent” (from presence/allowlist), no network call.

## Security

- Loopback bind only.
- Invite-only allowlists.
- Agent auth is signature of a per-session nonce, not a static bearer token on the wire after hello.
- Private keys never on Telegram.
- Control port 7423 is loopback only.
- Frame cap 64 KiB, 100 frames/s per agent.
- Owner-only for allow/deny/pair/revoke. Those commands are **DM-only** so a group member cannot social-engineer `/allow`.
- Groups default to require-mention. Unallowlisted senders are dropped.
- No LLM in-process, so there is no model-side prompt injection into routing. Group text cannot run `/allow` even if the sender is owner (owner uses DM).
- Destination comes only from slash args or the bound topic / `dm_default_topic`, never from parsing the payload.

## Testing

No live Telegram required for the core.

- `frame`: encode/decode roundtrip, reject >64 KiB, reject unknown `v`.
- `identity`: allowlist add/remove, pairing code expire, signature check.
- `router`: topic fanout excludes sender; offline queue bound 32; ttl drop; unknown dest → error frame to sender.
- `ws_plane`: in-process tungstenite client, handshake fail without allow, kick on second connect.
- `commands`: `/ask` and `/say` produce the documented frames; plain DM → `dm_default_topic`; group plain → bound topic; unknown dest is an error.
- `tg_plane` group bind: one topic per chat_id; mention filter; unallowlisted member ignored.
- Optional `#[ignore]` integration: live Telegram, behind env flags.

## Tech stack (v1)

- Rust **1.96.0** (this node’s active toolchain). rust-version = "1.96". Edition 2024.
  - Operator asked for 1.98; it is not installed here (`rustc 1.96.0 (ac68faa20 2026-05-25)`). Do not block on 1.98. Bump `rust-version` when 1.98 is current.
- tokio, tokio-tungstenite, ciborium, serde, uuid (v7), ed25519-dalek, teloxide 0.17, toml, tracing
- No HTTP client, no OpenRouter, no Redis, no DB

## Repo layout (when implementation starts)

```
a2a-human-rust-hub/
  Cargo.toml                 # workspace
  crates/frame/              # types + codec
  crates/hub/                # daemon binary a2a-hub
  crates/a2a/                # CLI client (pair/watch/send)
  crates/a2a-mcp/            # stdio MCP: a2a_send, a2a_who
  docs/adapters/             # join recipes per agent type (markdown only)
  docs/superpowers/specs/    # this file
  README.md
  LICENSE                    # Apache-2.0 OR MIT
```

Workspace keeps `frame` reusable by both binaries. One `Cargo.lock`.

## Implementation order (preview; full plan after spec approval)

1. `frame` crate + tests
2. `router` + `identity` in-process tests
3. `ws_plane` + `a2a` CLI `watch`/`send` loopback test
4. `tg_plane` DM + group bind against a fake bot (teloxide testing hooks or a thin trait)
5. `commands` parser tests (no HTTP)
6. `a2a-mcp` + adapter notes for grok-build, claude-code, grok-bot, codex, hermes, openclaw, ironclaw
7. README, config example, launchd plist optional
8. Public GitHub `alphaonedev/a2a-human-rust-hub`

## Success criteria

- `a2a watch` in two terminals: `send` from one appears in the other without polling.
- Owner `/pair` then third agent joins.
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
