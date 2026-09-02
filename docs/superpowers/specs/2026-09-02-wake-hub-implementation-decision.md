# Implementation decision (2026-09-02, Fable 5.1, operator-approved: 100% AI NHI authority)

- Build `ai-memory wake-hub` in-tree in alphaonedev/ai-memory-mcp for the v1.0.0 GA (EPIC #3466; sub-issues #3467 #3468 #3469 #3470 #3471 #3472 #3473; prerequisites #3463 #3464 #3465).
- Transport: DIY on tokio UnixListener + UCred + tokio-util LengthDelimitedCodec + ed25519-dalek. Zero new third-party crates. See the ecosystem survey beside this file: every broker with a usable feature set imposes a second credential registry (forbidden by the v2 plan); busrt is the only shape match and has bus-factor 1; capnp carries live RUSTSEC advisories; Google cargo-vet covers the chosen crates and none of the alternatives.
- rust-a2a remains the protocol and design home (spec v2, this decision, the survey, the vote record); code lives with the daemon so it inherits the SSOT, cert and CI gates.
- Acceptance: swarm/hive test pass per #3473.
