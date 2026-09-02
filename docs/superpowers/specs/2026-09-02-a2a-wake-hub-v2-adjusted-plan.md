# rust-a2a — 2×3 adversarial vote: verdict and adjusted plan

Conductor: Fable 5.1 · 2026-09-02 17:15Z · Reviewed: `docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md` (repo docs-only, no code yet) · Ecosystem: ai-memory v1.0.0 at 2b191538 · Panel: three red-team and three blue-team hard-coders, two rounds (independent review, then cross-examination with explicit concessions). Reports: `scratchpad/a2a-vote/{r1,r2,r3,b1,b2,b3}-round{1,2}.md`, capacity models `cap.py`, `calc.py`.

## Final tally (round 2, six votes per question)

| Question | YES | CONDITIONAL | NO | Verdict |
|---|---|---|---|---|
| Q1 Is the spec as written the best plan? | 0 | 4 | 2 | **No.** Unanimous that it must be rewritten (below). The integration I first proposed, "the existing webhook fires at the hub", does not exist: `memory_notify` dispatches no event. |
| Q2 Permanent part of the ai-memory ecosystem? | 0 | 6 | 0 | **Yes, conditionally**, as `ai-memory wake-hub`: a content-free, disposable wake plane under one identity root, inside the SSOT and cert gates. Never a message store. |
| Q3 Significantly faster swarm/hive? | 2 | 4 | 0 | **Wake latency: yes, by three to six orders of magnitude** (3-minute polling → ~1 ms). **Substrate throughput: zero.** The measured ceilings (134 signed writes/s, ~900 keyword reads/s, semantic recall collapsing 56→32 ops/s) live in the embedder and the daemon's writer path, which the hub never touches. |
| Q4 Fits 128–256 agents per modular instance? | 1 | 5 | 0 | **Yes, once four spec defects are fixed.** Wake-only: ~120 KiB and one fd per connection → ~30 MiB, 257 fds, <0.2 core at 256 agents; a 256-way reconnect storm costs ~90 ms of one core. As specified it does not fit: 512 MiB of frame-counted queues, unbounded online egress, fan-out amplification the rate cap cannot see, and macOS's default 256-fd limit on f1 (EMFILE at exactly target scale). |

Confidence across the 24 final votes: 82–90.

## What all six agreed on

1. `memory_notify` emits no event, so there is nothing to bridge today (ai-memory #3465).
2. The webhook lane cannot carry wakes: a process-global 32-permit semaphore fixed at first use, blocking retry ladder, 26.2 s worst case, an audit row per dispatch on the contended writer lock, and a 1000-row subscription scan that silently truncates. Wakes must come from an in-process broadcast bus.
3. "Wake, then read the inbox once" is unsound today because `unread_only` is applied after the SQL `LIMIT` on both backends (ai-memory #3463).
4. Frames must be wake-only and content-free; the durable body and the delivery record stay in ai-memory. Drop-oldest on payload frames is silent data loss and violates the North Star.
5. UDS with `SO_PEERCRED` is the v1 transport (measured on this host: p50 19 µs vs 48 µs loopback TCP, kernel-attested uid/pid, no TOFU pin); loopback TLS stays behind a flag for the deferred gateway.
6. One identity root. The hub key is a scoped delegation (`a2a-hub/join/v1` domain, explicit scope, short `not_after`) issued by the enrolled ai-memory agent key. Never the raw `.priv` (a transport bug would become write forgery), never a second registry, never the raw `SUBKEY_CERT_V1_DOMAIN` (it would cross-verify as unscoped write authority).
7. Bind header `from` to the key that authenticated the hello; sign a domain-separated transcript, not the bare nonce; nonce-bind `join` and `depart` too; refuse ids over 32 bytes instead of truncating (ai-memory ids go to 128).
8. Queues and per-connection egress bounded in bytes with a global cap; refuse loudly to the sender; no pre-`wake` for an online peer; token bucket instead of the flat 100 frames/s; fan-out charged to the sender.
9. Loopback-only gives the real fleet (f1 macOS, f2 Linux, DigitalOcean) nothing. Cross-host wake rides ai-memory federation, one hub per host.
10. A permanent backstop poll (≤60 s) stays on so a hub crash degrades latency only.

## Disagreements I resolved as conductor

- **SSE-first vs hub-first.** Red argued the existing `approvals_sse` bus generalised to `/api/v1/inbox/stream` gives ~1 ms wake, cross-host, with zero new surface. Blue argued 256 long-lived streams land inside the daemon the architecture docs call the fleet-scale bottleneck, and that the hub's real value is an ephemeral lane that never touches the 134 writes/s ceiling. **Ruling: both, in this order.** Prerequisites (#3463, #3465), then the SSE inbox stream as the measured baseline and the cross-host path, then the wake-hub as the same-host offload, shipped only if it beats SSE on tail latency at 128–256 connections.
- **Proof of possession.** Blue-2 proposed the hub as the PoP oracle for ai-memory enrollment. Red-2's objection is decisive: a disposable, loopback-reachable artifact must never be the gate into the durable identity root. **Ruling: PoP is fixed inside ai-memory** (#3464), and the hub consumes a scoped delegation from that root.
- **Ephemeral payload lane.** Blue-1 wanted a ~4 KiB ephemeral frame lane, never queued offline. Red-2 wanted the 21-byte wake only. **Ruling: v1 is wake plus metadata `{inbox_row_id, namespace, sender, digest, seq_high_watermark}` capped at 256 bytes**, which removes the 77–108 ms inbox read from the common path and lets a lost wake self-heal. The ephemeral lane is v1.1 behind a feature flag, after measurement.
- **Per-recipient delivery accounting** (Red-3's orphan): moot once the webhook lane is out. The wake is a hint by contract; the inbox row is the record; the backstop poll is the guarantee.

## Adjusted plan (what I will sign)

### ai-memory prerequisites
1. #3463 `unread_only` inside the query on both backends.
2. #3464 challenge-response `bind_agent_pubkey`, append-only key history, `revoked` gating subkey verification.
3. #3465 `agent_notified` write event on both notify funnels, broadcast bus, `GET /api/v1/inbox/stream` modelled on `approvals_sse`, and a UDS sink hook. Operator decides GA vs v1.x.

### rust-a2a spec v2 (rewrite of the reviewed spec)
4. [spec] Package as `ai-memory wake-hub` (subcommand + unit file), not a second binary and repo; rust-a2a stays the design and protocol home.
5. [spec] Transport: UDS mode 0600 + `SO_PEERCRED` default; loopback TLS 1.3 behind `--tcp` for the deferred gateway; rustls `Ticketer` on when TLS is used.
6. [spec] Frames: `wake` (≤256 B metadata), `subscribe/unsubscribe`, `ping/pong`, `hello/welcome`, `join/depart`, `error`. `request/reply/notify` payload frames removed from v1.
7. [spec] Identity: scoped `a2a-hub/join/v1` delegation from the enrolled key; `from` bound to the hello key; domain-separated hello transcript `"a2a/v1/hello" ‖ hub_id ‖ nonce ‖ agent_id ‖ topics_hash`; nonce-bound join/depart; allowlist is a derived cache; allow/revoke emitted into the ai-memory audit spine; only `owner.pub` on the hub; `0o600` enforced at write and load.
8. [spec] Delivery: no pre-wake for online peers; per-recipient bounded mpsc with its own writer task; sharded routing table, no `.await` under a lock; refcounted fan-out; offline state is a coalesced pending set (count + id set + `lagged` marker), ~4 KiB per agent, never a payload ring.
9. [spec] Limits: token bucket ~500 frames/s burst 2000 per connection, fan-out charged to the sender, global egress byte cap, `error/507` to the sender on overflow, `RLIMIT_NOFILE` and a hard connection ceiling set at start-up, pre-auth frames rate-limited.
10. [spec] Ids up to 128 bytes; topics scoped to the subscriber's namespace read scope.
11. [ops] Metrics (connected agents, queue bytes, drops, fan-out p99, slow consumers, wake latency), health probe, SIGTERM drain, jittered reconnect with a handshake semaphore, two-pin rollover.
12. [ops] Cert: §6 NOT-COVERED line declaring the hub transport-only and content-free, a `check-cert-removal-proof.sh` row proving "wake is advisory, poll is the backstop", `doctor --posture` check, full SSOT reconciliation.

### Acceptance measurements
- Wake latency p50/p99 at 128 and 256 connected agents, hub vs SSE inbox stream, on f2 and f1.
- Zero substrate throughput regression: read-path and write-path harnesses A-B-A-B with the hub on and off.
- Kill the hub under load: no lost messages (inbox rows intact), wake latency degrades to the backstop poll only.
