# rust-a2a

Protocol and design home for **`ai-memory wake-hub`** — a same-host, **content-free** wake plane
over a `0600` AF_UNIX socket with kernel-attested peer credentials.

**Site:** https://alphaonedev.github.io/rust-a2a/

**Status:** spec v2 signed; the hub ships in-tree in
[alphaonedev/ai-memory-mcp](https://github.com/alphaonedev/ai-memory-mcp)
(EPIC [#3466](https://github.com/alphaonedev/ai-memory-mcp/issues/3466);
core [#3467](https://github.com/alphaonedev/ai-memory-mcp/issues/3467) merged,
identity [#3468](https://github.com/alphaonedev/ai-memory-mcp/issues/3468) in gate).
This repository holds the protocol, the specs and the vote record; no daemon is built here.

A wake is a **hint**. The ai-memory inbox row is the **record**. The `<=60 s` backstop poll is the
**guarantee** — so the hub may be fast and lossy at the same time without ever producing a wrong result.

- AWH1 length-delimited frames; ten kinds, none with a body field. `request` / `reply` / `notify`
  are removed from v1 and their wire numbers permanently reserved and refused by name.
- 256-byte wake hints `{inbox_row_id, namespace, sender, digest, seq_high_watermark}`.
- Byte-bounded per-recipient queues (256 frames / 64 KiB) under a 32 MiB hub-wide egress budget;
  fan-out charged to the sender; connection ceiling derived from `RLIMIT_NOFILE`.
- One identity root: a scoped `a2a-hub/join/v1` delegation minted by the agent's enrolled Ed25519
  key, `<=12 h`, over a domain-separated hello transcript. One uniform `401` for every refusal.
- Design target 128–256 agents per instance. Zero new third-party crates.

## Specs

- [Spec v2 — adjusted plan](docs/superpowers/specs/2026-09-02-a2a-wake-hub-v2-adjusted-plan.md) (current)
- [Implementation decision](docs/superpowers/specs/2026-09-02-wake-hub-implementation-decision.md)
- [Ecosystem survey — buy vs build](docs/superpowers/specs/2026-09-02-wake-hub-ecosystem-survey.md)
- [v1 design spec](docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md) (superseded by v2)

Apache-2.0 · © 2026 AlphaOne LLC
