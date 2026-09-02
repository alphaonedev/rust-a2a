# a2a-human-rust-hub

Local Rust daemon: fast agent-to-agent push fabric + Telegram for humans.

**Status:** design spec only. No daemon yet.

- Spec: [`docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md`](docs/superpowers/specs/2026-09-02-a2a-human-rust-hub-design.md)
- Intended public repo: `github.com/alphaonedev/a2a-human-rust-hub` (not created until the spec is accepted)

- **A2A:** WebSocket + length-prefixed CBOR on loopback. Any agent type joins the same way (sidecar `a2a watch` and/or MCP). Roster: Grok Bot, Hermes, OpenClaw, IronClaw, Claude Agent, Codex CLI, Claude Code CLI, Grok Build.
- **Humans:** Telegram 1:1 DMs and bound Telegram groups. Natural language at the edge only.
- **No LLM in the hub.** Humans use `/ask` `/say` and deterministic defaults. Destination agents already understand English in the payload.
