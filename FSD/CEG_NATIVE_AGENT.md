# FSD: CEG-Native Agent — graph_nodes ARE self-level CEG attestations

**Status:** Design ratified (2026-06-08). 3.0 / CEG 1.0 candidate. Tracks CIRISAgent#840, umbrella #866.
**Stakes:** CIRISAgent's CEG conformance is **one of the four implementations that gate CEG RC1** (the path to CEG 1.0) — alongside the three fabric siblings **CIRISNodeCore, CIRISLensCore, CIRISRegistry**. This is not just an agent feature: CEG cannot reach RC1/1.0 until the agent conforms. The agent is the *single-party epistemic-actor* reference implementation of the grammar.
**Spec baseline:** CEG **0.15** (`CIRISRegistry/FSD/CEG/`, the Agent 3.0 / CEG 1.0 candidate).
**Substrate baseline:** persist 4.1.0 / edge 1.3.0 / verify 4.8.1 (the migration to the Rust substrate is *done*; this is the next layer up).

---

## 0. The thesis — what "this" is

The CIRIS Agent is a **single federation identity**. Everything in its head — what it knows, configured, observed, derived, decided — is the agent **attesting to its own state under its own key**. `graph_nodes` do not need to *map* to CEG envelopes; at local tier they **are** CEG envelopes (`witness_relation: self`, `epistemic_mode: direct`, `cohort_scope: self`).

This is the Recursive Golden Rule made substrate (see `[[project_recursive_golden_rule]]`): the agent models itself with the *same shape* it models others — Self / Originator / Ecosystem self-similar at every scale. And it carries the Ubuntu discipline CEG §13.5 enforces: **self-knowledge never constitutes standing on its own.** The agent's self-attestations compose with *external* witness (LensCore `detection:*`, peer attestations) before they mean anything to the federation. The agent declares; the commons constitutes.

Three consequences fall out for free once the agent's state is uniform CEG shape:
1. **One query language** replaces N bespoke typed services.
2. **Audit IS the substrate** — the audit log is a `SELECT` on the attestation table.
3. **Federation projection is a signature op, not a translation** — context-gathered state is already in CEG shape; promotion just signs it.

---

## 1. CEG 0.15 ground truth (the constraints that shape every decision)

*(Corrections vs the #840 issue text are flagged — the issue predates 0.15.)*

### 1.1 The 1 + 4 primitive set (§3)
- **The "1" (`scores`)** — every claim (identity / capability / behaviour / state / commitment) is a `scores` attestation on a named dimension. Fields: `dimension`, `score ∈ [-1,+1]`, `confidence ∈ [0,1]`, `context`, `evidence_refs[]`, `valid_until`, `epistemic_mode`, `witness_relation`, `oversight_mode`, `occurrence_*`, `stake`.
- **The "4" structural composers** are **`delegates_to` / `supersedes` / `withdraws` / `recants`** — **NOT** `endorses`/`revokes`/`links` (the #840 text is wrong here). Endorsement = a positive `scores`; revocation = subject-side `withdraws` (§3.2.3); links = `topical_relation:*` + `references_attestation_id`. This matters: our config-version chain and consent-revocation map onto `supersedes`/`withdraws`, not onto invented verbs.

### 1.2 Envelope fields for a self-attestation (§4)
| field | self-attestation value |
|---|---|
| `attesting_key_id` | the agent's own federation key |
| `attested_key_id` | self (own key) for self-claims |
| `witness_relation` | **`self`** (the load-bearing setter; allowed: self/external/derived) |
| `epistemic_mode` | **`direct`** (allowed: direct/crypto/hearsay/derivative/appeal — NOT `introspection`/`testimony`, both rejected §13.2) |
| `cohort_scope` | **`self`** default (allowed: self/family/community/affiliations/federation) |
| `subject_key_ids` | empty for pure self-claims; `canonical:sha256:hex` for un-enrolled subjects (§1.4) |
| `confidence` | **< 1.0 for any introspective claim** (§13.2 — self-knowledge is never certain) |
| `context` / `evidence_refs[]` | the sanctioned home for narrative + reasoning-chain hashes |

**§4.2.3 self-consent ceremony:** the agent attests `identity:current` about itself with `subject_key_ids = [self.key_id]`, asserting authority over its own identity claims (the D08 autonomy claim).

### 1.3 The reasoning-trace verdict — **FORBIDDEN as a dimension family** (§1.3.1, §13.2, §13.5)
There is **no `reasoning:trace:*` family and we must not invent one** (resolves #840 OQ2). §1.3.1-T2 requires a prefix name a *mechanism*, not a subjective inner narrative; §13.2 rejects the `introspection` shape; §13.5 (the rule #840 cites): *"the wire format should **resist** primitives that let a single key announce its own state without external composition… richer narrative expression belongs in `context:`, `evidence_refs[]`, and downstream witness attestations, **not in new envelope enum members or new self-attestation prefix families**."* The sanctioned encoding for a reasoning chain:
- hash the chain → `evidence_refs[]`;
- narrative → `context:`;
- emit the **terminal verdict only** under an existing family (`dma:pdma|csdma|dsdma|idma:*` §5.1.2, `conscience:*` §5.1.3, the six `beneficence:*…justice:*` principles §5.1.1) with `witness_relation: self` + `confidence < 1.0`.

Our existing `ciris_accord_metrics` flat reasoning-event stream **stays as-is** — it is the *evidence* (the trace), referenced by hash; the CEG attestation is the verdict, not the trace.

### 1.4 Un-enrolled parties — canonical-hash, not new keys (resolves #840 OQ3) (§4.2.2)
A Discord user who never signed is named in `subject_key_ids` as `canonical:sha256:hex` of the preimage `"{platform}:{entity_kind}:{id}"` (immutable snowflake, not handle), e.g. `discord:user:1234…`. The agent acts as a **`delegates_to` proxy** for that party's revocation authority (§3.2.3 rule 3) — so the agent can `withdraw` on their behalf. **No new keys minted, no new subject_kind.**

### 1.5 §7.5 anti-Goodhart — the agent MUST NOT self-emit `capacity:*`
A folded `{agent, lenscore_detector}` key still cannot score its own `capacity:*` (`attesting_key_id ≠ attested_key_id`). The agent's 𝒞_CIRIS factors come from **external** LensCore `detection:*` — never fed back into its own context. This is the structural guarantee against an agent grading its own homework.

### 1.6 Local-tier signature deferral (resolves #840 OQ1) (§10.1.3)
Producer-only self-attestations (empty `subject_key_ids`) **skip the hybrid Ed25519+ML-DSA-65 signature locally** and sign only at federation-promotion — "costs ~the same as a JSON row." **One table** (`federation_attestations`) with local-tier rows + a promotion/visibility gate; **not** two tables. The single carve-out: a **subject-side consent revocation** (non-empty `subject_key_ids`) MUST promote *signed* to federation-tier within **24h** (substrate emits `hard_case:consent_revocation_promotion_overdue` past the window).

---

## 2. The NodeType → CEG mapping (the concrete #840 deliverable)

Every agent NodeType, its CEG home, and tier. *(Clean = ratified now; Candidate = needs CEG-authority confirmation; Local-only = self-attestation shape but never federates.)*

| NodeType (owning service) | CEG dimension / subject_kind | envelope | tier | status |
|---|---|---|---|---|
| `AGENT` / `IDENTITY` "agent/identity" (identity) | `identity:current`; subject_kind **`identity_occurrence`** (§5.6.8.8, `device_class: agent`) | self-consent ceremony (§4.2.3): `subject_key_ids=[self]`, `witness_relation:self` | federate (`cohort_scope:self`→other occurrences) | **Clean** |
| `IDENTITY_SNAPSHOT` (self_observation) | `identity:variance:*` self-report; `supersedes` chain | `witness_relation:self`, `confidence<1.0` | local→promote on drift alarm | **Clean** |
| `CONFIG` / `ConfigNode` (config) | `config:{key}` self-report; version chain becomes **`supersedes`** composer (replaces ConfigNode.version) | `witness_relation:self`, `cohort_scope:self` | local-tier | **Clean** |
| `CONSENT` / `DECAY` (consent) | producer stance `consent:partnered:{user_key}` (§5.6.8.6); subject_kind **`consent_record`** (§5.6.8.7) | `subject_key_ids=[user canonical-hash]` | **producer stance local; subject revocation MUST promote ≤24h (§10.1.3)** | **Clean** |
| `AUDIT_ENTRY` / `AUDIT_SUMMARY` (audit) | **the substrate IS the audit** — every attestation row is an audit row; AuditEntry hash-chain ≡ the CEG canonical-hash chain (`canonicalize_for_hash` already exists) | n/a (emergent) | n/a | **Clean** (collapses a table) |
| `USER` (memory/tsdb) | `observed:user:{canonical_hash}:*` (e.g. `interaction_count`) (§11.6.2) | `subject_key_ids=[canonical-hash]`, agent `delegates_to` proxy, `epistemic_mode:direct` | local; federate opt-in | **Clean** |
| `CONCEPT` / `OBSERVATION` (memory) | `epistemic:memory:topic={topic}` (self-knowledge) / `epistemic:about:{key_id}:*` (about a party) | `witness_relation:self`, `confidence` per memory, `evidence_refs`→source-content hashes | local | **Clean** |
| `CHANNEL` (memory/tsdb) | context-tier observed-about-channel (canonical-hash subject) | `witness_relation:self` | local-only | **Candidate** |
| `TSDB_DATA` / `TSDB_SUMMARY` / `TRACE_SUMMARY` / `CONVERSATION_SUMMARY` / `TASK_SUMMARY` (telemetry, tsdb_consolidation) | operational self-report. **NOT** `system:*` (that's persist/substrate-reserved §7.2). Agent operational telemetry has no federation consumer → **local-only context-tier self-attestations** (queryable, never federated) | `witness_relation:self`, `cohort_scope:self` | **local-only** | **Candidate** — confirm no §5 family wanted |
| `INCIDENT` / `PROBLEM` / `INCIDENT_INSIGHT` (incident_management) | operational self-report; `supersedes`/`withdraws` for resolution | `witness_relation:self` | local-only | **Candidate** |
| `MODERATION` / `SAFETY_SCORE` (adaptive_filter) | about-a-party verdict. `moderation:*` (§5.6.4) is NodeCore-governance-reserved → agent emits `observed:user:{hash}:safety` / `epistemic:about` instead | `subject_key_ids=[hash]` | local; federate opt-in | **Candidate** — do NOT shadow `moderation:*` |
| `BEHAVIORAL` / `SOCIAL` (memory) | `observed:*` / `epistemic:about:*` | `subject_key_ids` as applicable | local | **Candidate** |
| *(reasoning output — not a node today)* DMA verdicts + conscience | `dma:*` (§5.1.2) + `conscience:*` (§5.1.3) + six principles (§5.1.1); chain→`evidence_refs` | `witness_relation:self`, `confidence<1.0` | federate (this is the agent-intent surface) | **Clean** |
| *(capacity — never a node)* 𝒞_CIRIS factors | `capacity:*` (§5.5.4) — **agent NEVER emits about itself** (§7.5); arrives from LensCore | — | inbound only | **Clean (prohibition)** |

**Disposition:** ~7 NodeTypes have clean CEG homes today; ~5 are operational/internal and resolve to **local-only context-tier self-attestations** (the CEG *shape*, never federated) or need a CEG-authority confirmation before claiming a §5 family — and crucially, none of them should shadow a reserved family (`system:*`, `moderation:*`, `detection:*`, `capacity:*`).

---

## 3. The persist gating dependency (the one hard blocker)

Today the agent's **only** node write path is `cirisgraph_upsert_node` (the legacy graph table). persist v4 *has* a CEG federation **read** surface (`ReadEngine v2`, `list_attestations_for`, `caller_occurrence_key_id`) but **the agent calls none of it**, and there is **no agent-facing local-tier attestation WRITE**. The projection has nowhere to land until persist exposes:

1. `attestation_upsert_local(envelope)` — write a local-tier self-attestation (deferred signature, producer-only authority).
2. `attestation_query(dimensions[], valid_at, confidence_floor, subject_key_id?)` — the uniform read surface that the memory/config/consent/audit services become wrappers over.
3. `attestation_promote(id) -> signed` — compute the hybrid signature + mark federation-visible at emit time.
4. The consent-revocation ≤24h promotion enforcement (§10.1.3) as a substrate guarantee.

**→ File this as a CIRISPersist FSD ask now.** It is the critical path; everything in §2 is inert until it lands. (Mirrors how 2.9.0–2.9.5 worked: agent design → persist surface → agent consumes.)

---

## 4. Codebase shape (what changes — schema + projection, not agent-logic redesign)

1. **`add_graph_node()` is rewired to write attestations directly** (not a parallel shadow): after the hard cut, a node write IS an `attestation_upsert_local(envelope)` call. Pre-cut, the `migrate_graph_nodes_to_attestations()` one-shot transforms the durable backlog (§5).
2. **memory / config / consent / audit reads collapse to a CEG-query client** — `self_attestations.query(dimensions=[…], valid_at, confidence_floor)`. The existing services become thin typed views over the uniform substrate.
3. **Context-gather collapse:** `batch_context.py`'s ~25 heterogeneous shapes (IdentityData, UserProfile, ChannelContext, SecretsSnapshot, TelemetrySummary, consent, queue depths, …) become a **CEG-query DAG** — one interface, composable confidence + provenance.
4. **Local-tier signature deferral** wired into the promotion path (federation emit signs; local writes don't).
5. **`GraphNodeAttributes` typed shapes → `attestation.context` + structured fields** (the typed-node round-trip becomes envelope (de)serialization).

---

## 5. Migration shape (resolves #840 OQ4) — **HARD cut-over, not dual-write**

A dual-write/shadow migration is the **wrong** tool here, for five reasons:

1. **Dual-write IS the cohabitation this design exists to eliminate.** §0 commits to a single substrate, no second-surface tables. Running `graph_nodes` and `federation_attestations` side-by-side for a migration window is exactly the two-surface cohabitation the frame rejects. The only migration shape *coherent with the thesis* is a hard cut.
2. **A shadow never tests the actual risk.** The risk is not "do rows copy" — it's "does the agent *reason* correctly off attestations." During dual-write the agent still reads `graph_nodes` (the shadow can't be source-of-truth), so the CEG-native agent is never exercised until cutover anyway. The shadow buys complexity and zero real confidence.
3. **Most `graph_nodes` are derived, not durable.** TSDB data + the five `*_SUMMARY` types + trace/task summaries + USER/CHANNEL nodes are consolidations/observations — **regenerated, not migrated**. The genuinely durable set is small and bounded (identity, config, partnered-consent, accumulated CONCEPT/OBSERVATION memory) → a **one-shot mechanical transform**, one node → one envelope.
4. **Continuity is by re-attestation, not data preservation.** The agent re-attests `identity:current` at every WAKEUP. A CEG-native agent boots, re-attests identity, runs the one-shot transform of the bounded durable set, and proceeds. Identity survives structurally.
5. **Conformance is binary** (the CEG RC1 gate): the agent's state either IS CEG attestations or it isn't. A dual-write shadow is a non-conformant agent with a side table — it does not pass the gate. A hard cut delivers a conformant agent on day one.

**The proven playbook (it was already a hard cut):** 2.9.0 *removed* the SQLite bootstrap layer outright and went straight to persist — no dual-write — de-risked by validating the transform against a **real production dump (scoutdb)** *before* the cut, with rollback = the release + the intact prior DB. Identical here:

- **C0 — one-shot transform, offline-validated:** write `migrate_graph_nodes_to_attestations()` (durable types only: identity, config, consent, memory; derived types are dropped/regenerated). Validate it against **production DB dumps** in CI + a canary (`FSD/multi_occurrence_canary_rollout.md`) — assert every durable node round-trips to a queryable attestation. This validation, not a live shadow, is where confidence comes from.
- **C1 — boot-time cut:** on first 3.0 boot, the migration runs once: durable `graph_nodes` → `federation_attestations` (local-tier), then the agent runs CEG-native. `graph_nodes` is retained **read-only as a cold backup** (not dropped) for one release.
- **C2 — context-gather + all read paths are CEG queries** from the cut (memory/config/consent/audit become typed views over `attestation_query`). There is no period where some services read old and some read new.
- **C3 — federation promotion live:** agent-intent (`dma:*`/`conscience:*`/principles) promotes to the public ledger; the LensCore fold (`{agent, lenscore_detector}`) consumes `detection:*` inbound.
- **Rollback** = redeploy the prior release; the cold-backup `graph_nodes` table is still intact. Reversible at the release boundary, not via a shadow.

The cut is atomic per occurrence and gated on the offline validation passing against real prod data — the same discipline that carried the persist/verify/edge substrate cut, applied one layer up.

---

## 6. Release sequencing (mapped to the 3.0 trajectory)

| release | CEG-native work |
|---|---|
| **2.9.6** (LensCore cut, *now*) | #754 done (tree_verify project param ✓). **This FSD ratified.** Persist attestation-surface ask filed. `ciris-lens-core` dependency added (fold-in scaffolding, #857). #842 closed-superseded. |
| **2.9.7** (hardening) | persist attestation write+query+promote surface lands (CIRISPersist#171); build `migrate_graph_nodes_to_attestations()` + the `attestation_query` read client. |
| **2.9.8** (NodeCore/Registry) | **C0** — validate the one-shot transform against production DB dumps in CI + canary (`FSD/multi_occurrence_canary_rollout.md`); all read paths rewritten onto `attestation_query` behind a flag, exercised in the canary. |
| **3.0 / CEG 1.0** | **C1–C3 hard cut** — boot-time transform, CEG-native from first boot, `graph_nodes` retained read-only as cold backup, federation promotion live. The CEG-native agent. Rollback = prior release. |

---

## 7. What this earns (and why it's the crux)

A CEG-native agent is **legible by construction**: every claim it makes about itself or its world is the *same shape* as every other federation participant's claim — auditable, time-travellable, revocable, composable with external witness, and federatable without translation. The austere 1+4 wire is *exactly* rich enough for a single-party epistemic actor (the multi-party witness-set / hybrid-sig surfaces it doesn't need live upstairs in NodeCore/Edge). The agent stops being a black box with a bolted-on audit log and becomes **a participant in the grammar it reasons about** — self-knowledge offered to the commons, standing granted back relationally. That is the Recursive Golden Rule as a data model, and it is the foundation Agent 3.0 / CEG 1.0 stands on.

---

## References
- CEG 0.15 spec: `CIRISRegistry/FSD/CEG/` — §3 primitives, §4 envelope, §5 namespace, §7 reserved, §10.1.3 local-tier, §11.9 fold-in, §13 anti-patterns.
- `FSD/GRAPH_NODE_TYPE_SYSTEM.md` (current node system), `FSD/PROOF_OF_BENEFIT_FEDERATION.md`, `FSD/TRACE_WIRE_FORMAT.md` (the trace = evidence).
- Current code: `ciris_engine/schemas/services/graph_core.py:127` (GraphNode), `ciris_engine/logic/context/batch_context.py` (the collapse surface), `ciris_engine/logic/persistence/models/graph.py` (the `cirisgraph_upsert_node` write path).
- Issues: #840 (this design), #866 (2.9.6 umbrella), #857 (LensCore ingest), #803/#801 (emission/cadence), #754 (tree_verify project ✓).
