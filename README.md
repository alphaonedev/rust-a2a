# a2a-rust-hub

Super-thin Rust daemon: **A2A only**. No humans, no Telegram, no LLM.

**Status:** design spec only. No daemon yet.

- Spec: [`docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md`](docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md)
- Intended public repo: `github.com/alphaonedev/a2a-rust-hub` (not created until the spec is accepted)

Any AI joins the same way: `a2a pair --id NAME` then `a2a watch`. Packed binary packets over TLS 1.3 on loopback. Hub routes headers and copies payload bytes. Recipients always get a `wake` before new frames. Signed join and signed depart.
