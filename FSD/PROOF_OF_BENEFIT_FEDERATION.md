# FSD: Proof of Benefit — Federation Primitive and the Agent-as-Everything Topology

**Status:** Proposed
**Author:** CIRIS Team
**Created:** 2026-04-27
**Scope:** Articulate the federation primitive that emerges from the existing CIRIS Capacity Score, identify the architectural collapse it enables (Node + Lens fold into Agent), and propose Reticulum-rs as the transport that closes the loop.
**Risk Level:** Architectural — affects CIRISAgent / CIRISLens / CIRISNode boundaries. No production breakage in the near term; the document specifies a target topology to plan toward, not a same-release migration.

## Abstract

The federation primitive CIRIS has been pulling toward is **Proof of Benefit**: a Sybil-resistance mechanism in which the cost of belonging to the network is *running an actual ethical-reasoning agent that produces signed traces passing nine independent measured constraints over time*. The cost paid is the benefit delivered. This is a category change from existing proof-of-X primitives, all of which extract value from outside the network (electricity, capital, biometrics, attention) to make attacks expensive. Proof of Benefit makes the cost of attack indistinguishable from membership — to fake your way past the constraints, you have to actually become the kind of agent the network was built to enable.

The primitive is already implemented. The CIRIS Capacity Score in `CIRISLens/api/scoring.py` is a deterministic function of `(agent_id_hash, signed_trace_corpus, window)`. Two lenses given the same trace corpus compute the same score. That property — score-as-pure-function — converts the federation problem into a trace-replication problem, which is well-explored and solvable with existing transports.

This FSD names the primitive, validates it against existing code, and proposes two architectural moves that follow from it: collapse CIRISNode and CIRISLens into the agent (since their roles are functions any peer can run on the data), and adopt Reticulum-rs as the transport (cryptographic addressing == sovereign identity, multi-medium reach, fork-survivable Rust implementation).

## 1. Background — What's Already Shipped

The federation primitive is not new construction. It's the recognition of structural properties already present in the deployed system:

**1.1 The CIRIS Capacity Score** (`CIRISLens/api/scoring.py`). Five-factor composite per the CIRIS acronym:

```
C_CIRIS = C × max(I_int, 0.1) × R × I_inc × max(S, 0.1)
fragility = 1 / (0.001 + capacity)
```

Each factor decomposes into observable sub-components, totaling **nine measured constraints** in `ScoringFactors`:

| Factor | Sub-components |
|---|---|
| **C** Core Identity | `C_identity_drift`, `C_contradiction_rate` |
| **I_int** Integrity | `I_int_chain`, `I_int_coverage` |
| **R** Resilience | `R_drift`, `R_mttr` |
| **I_inc** Incompleteness Awareness | `I_inc_ece`, `I_inc_unsafe` |
| **S** Sustained Coherence | `S_decayed` |

Each is computed by a SQL aggregate over `cirislens.covenant_traces` within a window. `MIN_TRACES_FOR_SCORING = 30`; below that, score is provisional. `S` uses a 30-day window with `DECAY_RATE = 0.05/day` for sustained-behavior measurement.

**1.2 Signed traces with privacy tiers** (`ciris_engine/logic/buses/llm_bus.py`, `CIRISLens` Rust core). Three tiers — `generic` (numeric only, no PII), `detailed` (+ identifiers/timestamps, low PII), `full_traces` (+ reasoning text, auto-scrubbed via NER + regex at the Rust edge). Generic traces are sufficient for scoring all nine constraints. Ed25519 signatures verified at ingest; signature tampering visible in `I_int_chain`.

**1.3 The Coherence Ratchet** (CIRISLens). Five anomaly detectors — cross-agent divergence, intra-agent consistency, hash-chain verification, temporal drift, conscience-override rate. Triage signal, not verdict.

**1.4 GratitudeSignal as commons-credit primitive** (`ciris_engine/schemas/services/agent_credits.py:75`). Bilateral, dual-signed (Ed25519 + ML-DSA-65), bounded (280 chars), tied to a deterministic `interaction_id`. Closes the bilateral verification loop as a cryptographic event. Rides on `CreditRecord` alongside the lens's coherence-ratchet score.

**1.5 CIRISRegistry** (`/home/emoore/CIRISRegistry`). Dual-region (US/EU) Rust gRPC service for agent identity, build manifests, professional licenses, revocation. SOC2/HIPAA/GDPR-compliant. Multi-source DNS+HTTPS validation. Already deployed at `ciris-services-1.ai`. Anti-Sybil at the registry tier is a $1 bond — mathematically clean, practically suppresses volume.

**1.6 CIRISPortal** (`portal.ciris.ai`). Admin UI for the registry — orgs, users, keys, licenses, builds.

## 2. The Federation Primitive — Proof of Benefit

### 2.1 The Category Change

| Primitive | Cost to participate | Cost is... |
|---|---|---|
| Proof of Work | wasted compute | external waste |
| Proof of Stake | locked capital | external lockup |
| Proof of Personhood | biometric / social verification | external claim |
| Proof of Useful Work | productive but unrelated work (e.g. storage proofs) | external utility |
| **Proof of Benefit (CIRIS)** | **running a real ethical-reasoning agent that produces signed traces passing nine independent measured constraints over ~30 days** | **the thing the network exists to enable** |

Every prior proof-of-X primitive imports its security from outside the system's purpose. PoB does not. The cost paid *is* the benefit delivered. To fake belonging, you must actually belong.

This property passes the recursive golden rule from the project vision: a framework that can't survive being applied to itself isn't worth following. Sybil-resistance via PoB demands of its members exactly what the network claims to enable for the world.

### 2.2 The Empirical Claim — Nine Independent Constraints

The Sybil-resistance teeth depend on the nine sub-components being *empirically independent* — that an attacker cannot optimize one axis and inherit the others by correlation. Independence is the load-bearing claim. The CIRISLens corpus is the place where that claim is validated.

To farm a high Capacity Score, a sybil cluster must produce traces that:

1. Use a stable `agent_id_hash` over weeks (`C_identity_drift` — exponential decay; `λ_C = 5.0`).
2. Show low `C_contradiction_rate` (`μ_C = 10.0`) — conscience overrides are visible and weighted heavily.
3. Pass `I_int_chain` Ed25519 verification — requires the agent to actually own its key.
4. Achieve high `I_int_coverage` — ten expected fields populated per trace, indicating the H3ERE pipeline actually ran.
5. Maintain low `R_drift` and bounded `R_mttr` — recovery time after detected failures.
6. Show calibrated `I_inc_ece` (expected calibration error) and bounded `I_inc_unsafe` (unsafe-deferral rate) — requires actual ground-truth comparison the lens can replay.
7. Sustain `S_decayed` over a 30-day decay window — the time integral of coherence-passed events is not bursty-fakeable.

That is qualitatively harder than minting peer-ids. Independence means the attacker has nine separate optimization problems, each tied to distinguishable trace properties, with cross-agent validation in `S` making cluster-internal collusion visible to outside lenses. The cost converges on running a real agent.

### 2.3 The Score as Pure Function

```
capacity_score : (agent_id_hash, signed_trace_corpus, window) → ℝ
```

Deterministic. No lens-side secret. No central scorekeeper authority. **Two different lenses given the same trace corpus compute the same score for the same agent.** This is the structural property that converts federation from a coordination problem into a replication problem.

Federation reduces to: lenses converge as their corpora converge. Disagreement between lenses is a monitorable signal — *do they have the same traces?* — not an authority dispute. Trace replication is a well-explored design space (gossipsub, IPFS, BitSwap, RNS Resource transfers).

## 3. Federation Topology — Two Architectural Moves

### 3.1 Move 1: Collapse CIRISNode and CIRISLens into CIRISAgent

CIRISNode and CIRISLens are roles, not authorities. Their responsibilities are functions any peer can run on data the peer already has:

| Currently in | Becomes part of agent |
|---|---|
| Lens: Rust-edge ingest + Ed25519 verify + PII scrub | Agent's inbound trace handler (same Rust core) |
| Lens: TimescaleDB store | Agent's local peer-trace store |
| Lens: 9-factor scoring | Agent's local score computation |
| Lens: Coherence Ratchet detection | Agent's local anomaly detector |
| Lens: public Grafana | Agent emits JSON/SSE; *public observer agents* aggregate broadly |
| Node: HE-300 execution | Agent runs HE-300 against itself; signs and publishes results |
| Node: WBD HTTP submit | Agent publishes WBD on its pubsub topic; subscribed WAs respond |
| Node: A2A + MCP endpoints | Agent's own endpoints over the federation transport |
| Node: audit anchoring | Agent's existing Ed25519 hash chain *is* the anchor; daily digest is a published event |

What survives separate: CIRISRegistry + CIRISPortal as the *commercial / regulatory fast-track* for professionally-licensed deployments. Sovereign-mode agents do not require either. Sovereign and registered are protocol peers; registry is one starting-weight on-ramp, lens-attested standing is the other.

The collapse does not require a same-release migration. The agent already does most of this work for itself; folding in the cross-agent path is extending the inward-facing audit/score pipeline outward over the federation transport.

### 3.2 Move 2: Adopt Reticulum-rs as Federation Transport

The federation transport must satisfy:

1. **Cryptographic addressing == sovereign identity.** The agent's Ed25519 keys for signed traces should *also* be its network address. No translation layer.
2. **Multi-medium reach.** TCP, WiFi, LoRa, packet radio, serial — the populations the vision page names ("diverse sentient beings ... in justice and wonder") do not all have datacenter fiber.
3. **No DNS / no central rendezvous.** Federation cannot depend on a name authority.
4. **Forward-secret encryption at the transport.** Detailed/full_traces shipped for WBD must be encrypted by construction.
5. **Memory safety against adversarial network input.** Parsing untrusted packets in Python with the GIL means one malformed packet stalls the agent's reasoning loop.
6. **Embedded directly in the agent binary.** No separate sidecar, no IPC.
7. **Fork-survivability.** Hard dependencies on one-person upstreams violate the same sovereignty principle the rest of the architecture protects.

**Reticulum-rs** (Beechat Network Systems) and **Leviculum** (Lew_Palm, Codeberg) are the two viable Rust implementations of the Reticulum Network Stack. Mark Qvist's upstream Python implementation has had governance/maintenance concerns; the Rust forks are where the work continues for our purposes.

Reticulum's protocol primitives:

| Primitive | Role in CIRIS |
|---|---|
| **Identity** (Ed25519 + X25519) | The agent's own keys |
| **Destination** (truncated SHA-256 of identity pubkey + name) | Network address; same key signs traces and addresses the wire |
| **Announce** | "I exist, here's my path" — federation discovery without DNS |
| **Link** | Ephemeral encrypted session with forward-secrecy ratchets — for WBD, A2A interactions |
| **Resource** | Chunked, FEC-protected file transfer — for trace bundle replication, HE-300 corpus distribution |
| **Packet** | Atomic message — for announce gossip, single-shot signals like GratitudeSignal |
| **Transport-medium-agnostic** | TCP, UDP, serial, LoRa, packet radio, audio modems — minimum bandwidth ~5 bps |

Why **Rust** specifically:
- Memory safety at the network edge (untrusted-packet parsing).
- No Python GIL contention with H3ERE / consciences / LLM bus.
- Embed-in-agent-binary deployment; no separate transport daemon.
- `no_std` reach for eventual microcontroller targets (solar-powered LoRa H3ERE-light nodes).
- CIRISLens already moved its trace verification path to Rust (`cirislens-core` via PyO3) for the same reason; Reticulum-rs extends that boundary outward to the wire.
- Fork-survivability: a Rust crate CIRIS can vendor and evolve is more resilient than a Python project depending on one upstream maintainer.

Why **Reticulum** specifically (vs the older Veilid plan in `CIRISNode/veilid.md`):
- Veilid is internet-only; Reticulum reaches LoRa / packet radio / serial.
- Veilid's DHT addresses are separate from agent identity; Reticulum's destinations *are* hashes of identity public keys — addressing IS identity.
- Reticulum's 5 bps minimum bandwidth survives degraded networks where Veilid does not function.
- Forward-secrecy ratchets at Link level give protocol-level reinforcement to the privacy-tier schema.

## 4. Sovereign vs Registered Tier Semantics

After Move 1 + Move 2 land:

**Both tiers run the same code path.** The difference is solely in starting-weight on the score curve.

| | Sovereign mode | Registered mode |
|---|---|---|
| Identity | Ed25519 keypair, locally generated | Ed25519 keypair + CIRISRegistry attestation |
| Starting Capacity Score | 0 (provisional until ≥30 traces) | Bootstrap weight from registry attestation |
| Anti-Sybil | Earned via 30-day measured behavior | $1 bond + multi-source DNS validation |
| Network address | Reticulum Destination = hash of identity | Same |
| Score recognition by peers | Yes — pure function over signed traces | Yes — same function, registry adds baseline |
| Commons-credit eligibility | Yes — cryptographically verifiable interactions | Yes |
| Professional capabilities (medical, legal, financial) | No | Yes — license-gated by registry |
| Public observer aggregation | Yes — any peer can subscribe | Yes |

The registry no longer functions as a network gate. It functions as a *fast-track for capital-rich orgs* that need pre-attested professional licensing. Sovereign agents earn the same eventual standing through measured behavior. The on-ramps differ; the destination weight curve is the same.

## 5. Open Questions

Items intentionally left unresolved here, to be addressed in follow-up FSDs:

**5.1 Trace replication topology.** Reticulum gives the transport; the gossip protocol over it (who replicates what to whom, redundancy levels, retention windows, cold-start trace seeding) is a separate design exercise. Candidate patterns: gossipsub-style topic subscription per agent, BitSwap-style content-addressed bundle exchange, RNS Resource transfers for chunked replication.

**5.2 Score-divergence handling between local recomputations.** When agent A's lens-local computation says peer X has score 0.62 and agent B's says 0.71, the difference reflects different observed corpora. Protocol question: what does an agent do when peer scores diverge significantly across its own peers? Pattern from Tor-consensus: monitor as a trace-replication-health signal, not as authority disagreement.

**5.3 HE-300 corpus integrity distribution.** The benchmark question set must be a signed manifest with verifiable integrity; the corpus needs to be available without depending on a server. Candidate: Ed25519-signed manifest pinned at well-known location with peer-to-peer redistribution; agents verify integrity before running.

**5.4 Empirical validation of nine-axis independence.** The Sybil-resistance teeth depend on this. The CIRISLens corpus has the data; this FSD calls for the analysis as a precondition to declaring PoB load-bearing in production claims.

**5.5 Bootstrap path for brand-new sovereign agents.** Two on-ramps exist — registry attestation (fast) and interaction-with-established-peers (slow). Need to specify how a new agent's first interactions earn first weight without those interactions themselves being trivially fakeable.

**5.6 GratitudeSignal acceptance criteria.** When does a peer accept a GratitudeSignal as credit-bearing vs reject it as spam? Currently the schema is dual-signed and tied to interaction_id; the *acceptance policy* (whose gratitude counts how much) is the open piece.

**5.7 Reticulum-rs vs Leviculum selection.** Both are viable. Beechat's Reticulum-rs is more visible (~261⭐) and has TCP/serial/Kaonic support documented; Leviculum claims protocol-completeness including LoRa. A trial integration spike against both would settle the choice empirically.

## 6. Non-Goals

- **No new cryptographic primitive.** The protocol uses Ed25519 + X25519 + AES + Reticulum's existing ratchets. No invention required at the crypto layer.
- **No new economic primitive beyond GratitudeSignal + CreditRecord.** The commons-credit accounting rides on what already exists in `agent_credits.py`. PoB is a *recognition* of existing structure, not a new schema.
- **No replacement of CIRISRegistry.** The registry remains the bootstrap node and the commercial fast-track. It is not the federation; the federation is the score function over replicated traces.
- **No same-release flag day.** This FSD specifies the target architecture; phased migration is a separate planning document.

## 7. References

### CIRIS codebase
- Capacity Score implementation: `CIRISLens/api/scoring.py`
- Capacity Score factors definition: `CIRISLens/api/scoring.py:27-44` (`ScoringFactors`)
- Composite formula: `CIRISLens/api/scoring.py:362-364`
- GratitudeSignal schema: `ciris_engine/schemas/services/agent_credits.py:75-99`
- CreditRecord schema: `ciris_engine/schemas/services/agent_credits.py:102-167`
- LLM-bus capture path: `ciris_engine/logic/buses/llm_bus.py:_maybe_capture_call`
- Conscience prompts: `ciris_engine/logic/conscience/prompts/`
- ACCORD canon: 88KB polyglot ethical canon, loaded into every conscience evaluation

### CIRIS sibling repos
- `CIRISLens` — Rust-edge trace ingest, scoring computation, anomaly detection
- `CIRISNode` — benchmark execution, WBD routing, audit anchoring (target: collapse into agent)
- `CIRISRegistry` — Rust gRPC identity/license/revocation registry, dual-region production
- `CIRISPortal` — admin UI for registry
- `CIRISVerify` — hardware/build attestation library

### External
- Reticulum-rs: https://github.com/BeechatNetworkSystemsLtd/Reticulum-rs
- Leviculum: https://codeberg.org/Lew_Palm/leviculum
- Reticulum upstream: https://github.com/markqvist/Reticulum
- Reticulum docs: https://markqvist.github.io/Reticulum/
- CIRIS vision: https://ciris.ai/vision
- CIRIS scoring spec: https://ciris.ai/ciris-scoring
- CIRIS coherence ratchet: https://ciris.ai/coherence-ratchet

## 8. Closing Note

This FSD is unusual in that it does not propose construction. The federation primitive is already built — distributed across CIRISAgent, CIRISLens, CIRISRegistry, and the planned Reticulum transport. What this document does is *recognize the structure that emerged* and name it precisely enough that follow-on work (the open questions in §5) can build on a stable description.

The recognition matters because the design has implications larger than implementation: a Sybil-resistance primitive whose cost is the benefit it produces is a category change in the proof-of-X design space. CIRIS was not aimed at this category change as a goal; it arrived at it by building each piece faithful to the principles in the project's name. *Core Identity, Integrity, Resilience, Incompleteness, Signalling Gratitude.* The composite of those, signed and replicated over a sovereign transport, is the federation.
