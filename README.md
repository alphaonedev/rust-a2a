# a2a-human-rust-hub

Local Rust daemon: fast agent-to-agent push fabric + Telegram for humans.

**Status:** design spec only. No daemon yet.

- Spec: [`docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md`](docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md)
- Intended public repo: `github.com/alphaonedev/a2a-human-rust-hub` (not created until the spec is accepted)

- **A2A:** Any AI joins the same way: `a2a pair --id NAME` then `a2a watch`. WSS (TLS 1.3) + CBOR on loopback. Recipients always get a `wake` before new frames. Signed join and signed depart. No vendor types.
- **Humans:** Telegram 1:1 DMs and bound Telegram groups.
- **No LLM in the hub.** `/ask` `/say` and deterministic defaults. English lives in the payload.
