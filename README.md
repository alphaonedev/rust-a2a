# a2a-human-rust-hub

Local Rust daemon: fast agent-to-agent push fabric + Telegram for humans.

**Status:** design spec only. No daemon yet.

- Spec: [`docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md`](docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md)
- Intended public repo: `github.com/alphaonedev/a2a-human-rust-hub` (not created until the spec is accepted)

Agent plane: WebSocket + length-prefixed CBOR on loopback. Human plane: Telegram (teloxide, long-poll). OpenRouter is the NL translator only, never on the A2A hot path.
