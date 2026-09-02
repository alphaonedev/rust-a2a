# wake-hub ecosystem survey — buy vs build

Scout: Opus 5 light-tier · 2026-09-02 · read-only, no cargo run, no repo touched.
Scope filter from `a2a-verdict.md`: same-host UDS (0600 + peer creds), ≤256 B content-free wake frames,
128–256 conns/host, **one identity root** (scoped `a2a-hub/join/v1` Ed25519 delegation), bounded
per-recipient queues in bytes, coalesced pending set, Linux f2 + macOS f1.

> SOP note: the `rust-1.98` skill is **not loadable in this session** (no Skill tool exposed; the `memory`
> MCP also failed with CONNECT_TIMEOUT). No Rust source was reviewed here — this is a metadata/ecosystem
> survey only. Any code review of the resulting hub must re-run under `rust-1.98`.

## Hard disqualifier applied to every candidate

Verdict item 6 ("one identity root") is structural, not a preference. Every broker below ships its own
identity model (usrpwd files, MQTT credentials, ZMTP/CURVE, ACLs, or "all peers are trusted"). Adopting one
means a second credential registry (forbidden) or bypassing its auth and writing our hello anyway — leaving
the broker to save us only the framing layer, ~80 lines of `LengthDelimitedCodec`.

## Candidates

| Crate | Latest / date | Cadence | Org, license | Downloads (total / recent) | MSRV | Linux+macOS UDS | Peer creds | Own auth (conflict) | Deps (est. transitive) | unsafe | RUSTSEC | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **tokio + tokio-util + ed25519-dalek** (DIY) | tokio-util 0.7.19, 2026-07-21 | ~monthly | tokio-rs, MIT | 749M / 158M | 1.70 | yes — `UnixListener` + `UCred{uid,gid,pid}`; `pid()` documented on Linux **and** macOS | **yes, native** | none — we supply it | **0 new** (already in tree) | contained, heavily audited | tokio has 5 historic (all fixed, none current) | **FIT (baseline)** |
| **interprocess** 2.4.3 | 2026-08-01 | ~quarterly | kotauskas (solo), 0BSD/Apache-2.0 | 13.8M / 3.9M | 1.75 | yes (`uds_local_socket`, tokio feature) | **no public creds API in 2.x** | none | ~7 direct, ~66K SLoC | yes (libc/windows-sys FFI) | none | **PARTIAL** — adds an FFI layer and *loses* the peer-cred API tokio gives free |
| **iceoryx2** 0.9.3 | 2026-07-08 | ~6 wks | Eclipse Foundation, MIT/Apache-2.0 | 588K / 305K | 1.81 (2024 ed.) | shm, not UDS | no | none — **assumes mutually-trusted processes** | 15 direct (own subcrates), ~203K SLoC | **very high** — own POSIX PAL, lock-free shm | none | **NO** — zero-copy shm = trust-everyone; wrong threat model, pre-1.0 |
| **zenoh** 1.10.0 | 2026-08-14 | ~6 wks | Eclipse/ZettaScale, EPL-2.0 or Apache-2.0 | 2.7M / 1.2M | 1.75 | `transport_unixsock-stream` yes | no | **yes** — usrpwd file + mTLS subjects + ACL interceptors (restart-only) | 33 direct, ~1M SLoC (est. 250–400 transitive) | present | none in DB; external audit exists (Census Labs 2025) | **NO** — a distributed routing fabric + second credential store for a 21-byte local wake |
| **busrt** 0.5.6 | 2026-07-17 | ~quarterly | alttch / Bohemia Automation, Apache-2.0 | 45K / 2.3K (**~178/mo**) | unstated | UNIX sockets yes | no | yes (broker-level client names/ACL) | heavy w/ `broker` (tokio, parking_lot, serde, submap, …), ~537K SLoC | present | none | **NO** — closest functional match, but bus-factor 1, ~178 dl/mo, no MSRV policy, 0.5.x: manageability risk |
| **rumqttd** 0.20.0 | 2025-09-29 | irregular (0.19→0.20 = 21 months) | bytebeamio, Apache-2.0 | 664K / 98K | unstated | **no UDS listener** (TCP/TLS/WS only) | no | **yes** — MQTT auth, extensible authenticator | large (est. 150+) | present | none | **NO** — no UDS, unwanted MQTT semantics, repo idle since 2026-05 |
| **zeromq (zmq.rs)** 0.6.0 | 2026-05-04 | ~quarterly | zeromq org, MIT | 2.6M / 925K | unstated | TCP + IPC (unix) | no | partial ZMTP; **no CURVE/ZAP** | est. 60–100 | some | none | **NO** — incomplete ZMTP, silent PUB/SUB drops, no auth, no byte bounds |
| **zmq (rust-zmq)** 0.10.0 | **2022-11-04** | dead (4 yrs) | erickt, MIT/Apache-2.0 | 6.6M / 1.3M | old | via libzmq | no | CURVE/ZAP (own PKI) | + C libzmq | FFI-wide | none | **NO** — dead 4 yrs, C dep, second PKI |
| **nng (nng-rs)** 1.0.1 | **2021-12-08** | **repo ARCHIVED** | neachdainn (GitLab), MIT | 319K / 43K | old | via C nng | no | own TLS/ZT | + C nng | FFI-wide | none | **NO** — archived upstream |
| **tarpc** 0.38.0 | 2026-08-12 | ~annual | Google, MIT | 9.5M / 1.26M | recent | transport-agnostic (works over tokio UDS) | n/a (we'd read it) | none | est. 40–80 | low | none | **PARTIAL** — req/reply RPC, which the verdict *removed* from v1; wrong shape for fan-out |
| **capnp-rpc** 0.27.0 | 2026-08-02 | ~monthly | capnproto org, MIT | 4.2M / 312K | recent | transport-agnostic | n/a | capability-based (arguably a 2nd identity model) | small (capnp + futures) | some | **capnp: RUSTSEC-2022-0068, RUSTSEC-2025-0143** | **NO** — only candidate with real advisories; obj-cap RPC is far more machinery than a wake |
| **ipc-channel** 0.23.0 | 2026-09-01 | ~quarterly | Servo, MIT/Apache-2.0 | 6.0M / 909K | recent | UDS w/ fd passing; macOS uses Mach ports | no | none | small (bincode, libc, mio) | yes (Mach/fd FFI) | none | **PARTIAL** — 1:1 channels, no fan-out, no byte bounds, divergent macOS transport |

## Recommendation: **(B) DIY on tokio + tokio-util + ed25519-dalek**

Reasons, in North-Star order:

1. **Data integrity / identity.** Every broker with a usable feature set (zenoh, busrt, rumqttd, zmq) forces
   a second credential registry — the exact failure the panel ruled out. The one crate with the right shape
   (busrt) has bus-factor 1 and ~178 downloads/month; it is not fleet-manageable.
2. **The reusable part is already in the tree.** `tokio::net::UnixListener` + `UCred` gives kernel-attested
   uid/gid/**pid on both Linux and macOS**; `tokio_util::codec::LengthDelimitedCodec` gives length-prefixed
   framing with a `max_frame_length`. That is the transport. What remains — scoped-delegation hello,
   bounded-in-bytes per-recipient queues, coalesced pending set, token bucket, drain, metrics — is exactly
   the ~1200 lines **no broker implements to our spec anyway**.
3. **Supply chain, measured.** Google's `cargo-vet` registry (2181 audit entries) contains **17** entries
   covering tokio / tokio-util / bytes / ed25519-dalek and **zero** for interprocess, tarpc, capnp-rpc,
   zeromq, ipc-channel, busrt, zenoh, iceoryx2, rumqttd. Adopting any candidate means importing 60–400
   unvetted transitive crates into the daemon that holds the durable memory store.
4. **`unsafe` budget.** DIY adds none. iceoryx2/interprocess/ipc-channel/nng/zmq all add FFI or hand-rolled
   POSIX layers on the hot path.

**Reconsider only if:** we later need cross-host wake — that rides ai-memory federation per the verdict, not a broker.

## Security-audit checklist if (A) is chosen anyway

Run all of these **before** the crate lands in `Cargo.toml`, and wire 1–3 into CI as gates:

1. `cargo audit` (+ `--stale`) clean; gate in CI.
2. `cargo deny check` — advisories, **bans** (dupe versions), **licenses** (zenoh is EPL-2.0 — confirm
   outbound compatibility), **sources** (registry allowlist, no git deps).
3. `cargo vet` with Google/Mozilla/Bytecode-Alliance registries imported; every new crate needs an audit or
   an `exemption` row with a named owner and expiry. Expect a large diff.
4. `cargo crev verify` — count crates with zero reviews (expect nearly all).
5. `cargo geiger` — enumerate `unsafe` in the new subtree; hand-review every block on the accept and
   frame-decode paths.
6. **build.rs review** — no network access, no `cc`/`bindgen` against unpinned system headers, no env-var
   codegen. Re-diff on every bump.
7. **Maintainer posture** — crates.io owners, org 2FA, publish-rights bus factor, release signing.
   busrt / interprocess / nng fail this (solo or archived).
8. **Feature minimisation** — `default-features = false`, transport feature only; re-run 1–6 on the
   *resolved* tree.
9. **Pin + vendor** — `=x.y.z`, committed `Cargo.lock`, `cargo vendor` snapshot, documented rip-out plan
   (cert §6 NOT-COVERED already requires the hub be provably removable).
10. **Fail-closed test** — kill the broker under load: inbox rows intact, wake degrades to the ≤60 s backstop
    only (verdict acceptance test 3); plus frame-decode fuzzing.
