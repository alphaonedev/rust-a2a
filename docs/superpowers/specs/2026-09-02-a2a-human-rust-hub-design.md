# a2a-rust-hub — Design Spec

Date: 2026-09-02
Status: draft, awaiting operator review (rev 5: A2A only, no humans, packed binary envelope)
Local path: `/Users/fate/a2a-human-rust-hub`
Intended public repo: `github.com/alphaonedev/a2a-rust-hub`
(folder still named `a2a-human-rust-hub` until GitHub create; rename then)

## Goal

A **super-thin Rust daemon** that does one thing: **A2A**.

No Telegram. No human plane. No LLM. No JSON on the wire. No WebSocket.

It is a TLS byte-router for AI agents. It reads a tiny binary header, pushes a `wake`, copies the payload, done.

Any AI joins the same way. The hub has no vendor types.

Success for v1: two processes round-trip a `request`/`reply` on loopback TLS in the low microseconds of userspace work (plus kernel/TLS); a third `--id` joins identically; disconnect ≠ depart; an offline agent is woken on reconnect. No `TELEGRAM_BOT_TOKEN`. No model key.

## Locked decisions

| Decision | Choice |
|---|---|
| Who | **Agents only.** Humans out of this daemon. |
| A2A language | **Packed binary envelope** (not English, not JSON). Hub routes on the header only. Payload is opaque bytes. |
| Transport | TLS 1.3 stream on `127.0.0.1:7422` (rustls). **Not** WebSocket, **not** HTTP. Length-prefixed frames. |
| Bind | Loopback only |
| Join / leave | Signed `join` (pending code + local `a2a allow CODE`) and signed `depart`. Disconnect ≠ depart. |
| Notify | Mandatory `wake` frame pushed to the recipient before every `request`/`reply`/`notify`. No polling. Offline queue then `wake` on reconnect. |
| Identity | Ed25519 per `--id`. No agent-type registry. |
| LLM | None |
| JSON | Debug/CLI only, never the wire |

## Why this “language”

AIs do not share a machine code, a tokenizer, or an embedding space. English is slow. JSON is what they *know*, but it is a verbose parse on every hop.

The fastest A2A contract is not a spoken language. It is an **IP-like packet**:

- Fixed binary **header** the hub understands in one pass (who, to, kind, ids, ttl)
- **Opaque payload** the hub never parses
- Two agents that want structure pick a `schema` and put CBOR/postcard/raw in the payload — that is their business, not the hub’s

The hub is a switch, not a diplomat. That is the efficiency.

## Non-goals (v1)

- Telegram, teloxide, humans, groups, slash commands
- WebSocket, HTTP, JSON-RPC, Linux Foundation A2A
- OpenRouter / any model
- Public bind / VPS
- Vendor SDKs or `agent_kind`
- Parsing payloads
- Durable disk log of frames (RAM queue only)

## Architecture

One tokio process.

```
  agent  -- TLS 1.3 + length-prefixed frames --+
  agent  -- TLS 1.3 + length-prefixed frames --+-->  a2a-hub  (header decode → wake → copy)
  agent  -- TLS 1.3 + length-prefixed frames --+
```

| Unit | Job |
|---|---|
| `frame` | Packed header encode/decode, length prefix. Payload is `&[u8]`. |
| `identity` | Ed25519, allowlist, pending join codes, owner key |
| `router` | Route, presence, offline queue, wake |
| `tls_plane` | Accept rustls, pin, join/hello/depart, push |
| `config` | Bind, paths |

## The A2A packet

Magic `A2A1` (`0x41324131`). Then `u32be` body length. Max body **64 KiB**. Then:

```
offset  size  field
0       1     v            = 1
1       1     kind         see Kind
2       1     flags        bit0 = has_corr
3       1     pad          = 0
4       2     schema       u16be  (0 = empty payload)
6       2     from_len,to_len  (u8 each, packed in u16be: from_len<<8|to_len)
8       16    id           uuid v7 bytes
24      16    corr         uuid bytes, or 0 if flags.has_corr=0
40      8     ts_ms        u64be
48      4     ttl_ms       u32be, 0 = no expire
52      N     from         UTF-8 agent_id, N=from_len, 1..=32
52+N    M     to           UTF-8 agent_id or "#topic", M=to_len, 1..=32
        rest  payload      opaque; length = body_len - header
```

`to` starting with `#` is a topic (`#hive`). Anything else is an agent id.

```
Kind (u8)
  0 challenge     1 hello        2 welcome
  3 ping          4 pong
  5 join          6 join_pending
  7 depart        8 departed
  9 wake
 10 subscribe    11 unsubscribe
 12 notify       13 request      14 reply
 15 error
```

Hub **must not** decode payload. Routing uses `kind`, `to`, `from`, `ttl_ms`, `id`, `corr` only.

`wake` payload is 21 bytes: `id[16] | kind[1] | pending[u32be]`. No text.

## Transport

- `127.0.0.1:7422` TLS 1.3, rustls, ALPN `a2a/1`
- First start: `~/.a2a-hub/tls/` local CA + server cert
- Client TOFU: `~/.a2a-hub/hub.pin` (SHA-256 of server cert). Mismatch = fail closed
- Framing: `u32be length` + body. No WebSocket masking, no HTTP
- One TCP connection per `agent_id`. Second hello with same id: `error/replaced` to the old socket, then the new one wins
- `ping` every 15 s; no `pong` in 45 s → drop (**leave**, not depart)

## Join, leave, depart

**Hello (already a member)**

1. TLS + pin
2. Hub `challenge` + 32-byte nonce
3. Client `hello`: payload = `pubkey[32] || sig[64] || sub_count[u8] || topics…` signed over nonce
4. Allowlist + sig check or `error/unauthorized` and close
5. `welcome`
6. If queue non-empty: `wake {pending:N}` then queued frames, each preceded by `wake`

**Join (not a member)**

1. `a2a pair --id NAME` → TLS TOFU, `join` signed with a fresh/loaded key
2. Hub replies `join_pending` with 6-char Crockford code (600 s)
3. Operator on this Mac: `a2a allow CODE` (authenticated with hub **owner** key, not Telegram)
4. Hub promotes pending → allow-agents; if socket still up, `welcome`

**Leave (temporary):** TCP drop or missed pong. Queue kept. Next `hello` does not need a new allow.

**Depart (membership ends):** `a2a depart --id NAME` sends signed `depart`. Hub deletes allow row, flushes queue, `departed`, closes TLS. Owner `a2a revoke NAME` is the same. Rejoin = new `pair` + `allow`.

## Wake (A2A notify)

Recipients never poll.

- Online dest: hub writes `wake` then the frame, immediately
- Offline dest: enqueue (32 frames or 5 min, drop oldest). On `welcome`: `wake {pending:N}` then replay
- `request` / `reply` / `notify` always wake. `ping`/`pong` do not
- Failed route: `error` to **sender**, never a silent success
- Holding the TLS session **is** being notified

## Universal client

The daemon does not care what the agent is. One binary:

```
a2a pair --id NAME
a2a allow CODE          # owner key, local
a2a watch --id NAME     # binary in, optional --hex/--json debug out
a2a send --id NAME --to DEST --kind request --file payload.bin
a2a depart --id NAME
a2a revoke NAME         # owner
```

`watch` default stdout is **not** English. Default: length-prefixed binary on stdout (same packet). `--json` is a debug flag for humans during development, off in agent use.

Any language joins by spawning `a2a watch` or by speaking TLS+packets natively. No per-vendor adapter crate.

## Files

```
~/.a2a-hub/
  config.toml
  tls/
  hub.pin
  owner.key              # created at first hub start; used by a2a allow/revoke
  allow-agents.json      # [{ agent_id, pubkey_hex }]
  pending-agents.json
  keys/<agent_id>.key
```

```toml
bind = "127.0.0.1:7422"
log = "info"
```

No chat tokens. No model keys.

## Error codes (u16 in `error` payload)

| code | meaning |
|---|---|
| 401 | unauthorized |
| 404 | unknown dest |
| 409 | replaced session |
| 410 | expired |
| 413 | too large |
| 429 | 100 frames/s |
| 500 | internal |

## Data flow

**A2A:** A `request` → hub header-decode → B `wake` + frame → B `reply` with same `corr` → A `wake` + reply. Payload copied blindly.

**Topic:** `to=#hive` → every subscriber except sender, each gets `wake` + frame.

**Depart:** signed `depart` → gone from allowlist.

## Error handling

- TLS pin mismatch: client refuses
- Bad depart sig: 401, membership unchanged
- TCP drop: leave, queue kept
- Hub crash: RAM queues lost; allowlist on disk survives
- Truncated frame: close that connection

## Security

- Loopback only
- TLS 1.3, TOFU pin, fail closed
- Signed join and signed depart
- Nonce-bound hello sig, not a static bearer
- Keys never leave `~/.a2a-hub/`
- 64 KiB / 100 frames/s
- Owner key required for `allow` / `revoke`

## Testing (no network beyond 127.0.0.1)

- `frame`: roundtrip, reject bad magic, reject >64 KiB, reject `v!=1`
- `identity`: join pending expire, allow, depart, bad sig
- `router`: fanout, wake-before-frame, queue bound, ttl drop, unknown dest → 404 to sender
- `tls_plane`: pin reject, hello without allow, join→pending, depart, second connect kicks

## Tech stack

- Rust **1.96.0** (this node). rust-version = "1.96". Edition 2024. (1.98 not installed.)
- tokio, tokio-rustls, rustls, rcgen, ed25519-dalek, uuid, tracing, toml
- **No** teloxide, tungstenite, serde-json on the hot path, reqwest, HTTP, OpenRouter, Redis, DB

## Repo layout

```
crates/frame/     # packet
crates/hub/       # a2a-hub daemon
crates/a2a/       # pair watch send allow depart revoke
```

## Implementation order

1. `frame` + tests
2. `identity` + `router` + tests
3. `tls_plane` + CLI loopback: pair, allow, watch, send, wake, depart
4. README + example config
5. Public GitHub `alphaonedev/a2a-rust-hub`

## Success criteria

- Two `a2a watch` processes: send appears as **wake then packet**, no poll
- Third `--id anything` joins with pair + allow; hub has no special case for the name
- `depart` then `watch` is 401 until a new pair
- Pin mismatch refuses
- Offline reconnect: `wake {pending:N}` then queue
- `cargo test` green; hub binary has no Telegram/HTTP client

## Open questions

None that block v1. Optional later: UDS instead of TCP (even faster, still local), public bind, LF-A2A gateway.

## Out of scope reminders

Do not add teloxide back. Do not put JSON on the wire. Do not create the public repo until this rev is accepted.
