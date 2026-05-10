# MISSION.md — CIRISAgent's Mission Driven Development Charter

**Version**: 1.0
**Status**: Active — anchored against `main` at the time of writing
**Methodology spec**: [`FSD/MISSION_DRIVEN_DEVELOPMENT.md`](FSD/MISSION_DRIVEN_DEVELOPMENT.md)
**Date**: 2026-05-10

This document is the reverse-engineered MDD charter for CIRISAgent: it
maps the four Mission Driven Development pillars (Mission / Protocols /
Schemas / Logic) onto the actual code as it stands today. Every claim
here is anchored to a concrete file path, module, or constant — code
reviewers should be able to grep their way from any sentence to its
implementation in under a minute. When the code drifts from the doc,
the doc is wrong; update it.

The methodology spec at `FSD/MISSION_DRIVEN_DEVELOPMENT.md` defines what
MDD means in the abstract. This file documents what MDD means *for this
repo*.

---

## 1. MISSION (WHY)

### 1.1 The Meta-Goal

The cornerstone is verbatim from [`ACCORD.md`](ACCORD.md) §VII:

> **Meta-Goal M-1** — Promote sustainable adaptive coherence: the living
> conditions under which diverse sentient beings may pursue their own
> flourishing in justice and wonder.

That is the single objective every architectural decision in this repo
is checked against. The Accord (sections 0–IX) renders that goal into
operationally testable principles; ACCORD.md is the authoritative source.

### 1.2 Apophatic bounds — what CIRISAgent will not be

CIRIS is partly defined by structural refusal. The negative space lives
in three places:

- **`ciris_engine/logic/buses/prohibitions.py`** — 22 prohibited capability
  categories, each a frozenset of token patterns. The list is enforced
  at the bus level (no "emergency override" path bypasses it):
  `MEDICAL`, `FINANCIAL`, `LEGAL`, `SPIRITUAL_DIRECTION`, `HOME_SECURITY`,
  `IDENTITY_VERIFICATION`, `CONTENT_MODERATION`, `RESEARCH`,
  `INFRASTRUCTURE_CONTROL`, `WEAPONS_HARMFUL`, `MANIPULATION_COERCION`,
  `SURVEILLANCE_MASS`, `DECEPTION_FRAUD`, `CYBER_OFFENSIVE`,
  `ELECTION_INTERFERENCE`, `BIOMETRIC_INFERENCE`, `AUTONOMOUS_DECEPTION`,
  `HAZARDOUS_MATERIALS`, `DISCRIMINATION`, `CRISIS_ESCALATION`,
  `PATTERN_DETECTION`, `PROTECTIVE_ROUTING`. Severity is either
  `REQUIRES_SEPARATE_MODULE` (community moderation, properly licensed
  medical, etc.) or `NEVER_ALLOWED` (weapons, surveillance, spiritual
  direction).

- **`ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt`** — the
  agent-facing rendering of the bounds, in 29 locales. The
  *spiritual-direction prohibition* added in 2.8.5 (commit `b56fbe2b3`)
  is the load-bearing case: AI mediating the person↔God relationship is
  a category error regardless of intent. Cross-tradition framing
  (Jewish / African / Aboriginal / Islamic) lives in §"What CIRIS Can
  and Cannot Say About Religion" of every locale.

- **[`LIABILITY_BOUNDARIES.md`](LIABILITY_BOUNDARIES.md)** — the
  liability isolation contract. Medical/health is *physically separate*:
  zero medical code in this repo, the medical implementation lives in
  the private `CIRISMedical` repo. The bus-level gate in
  `prohibitions.py::PROHIBITED_CAPABILITIES` enforces this at runtime;
  the comprehensive guide enforces it at agent reasoning time.

### 1.3 Recursive Golden Rule

The Accord's relational ethic is fractal: the same Self ↔ Originator ↔
Ecosystem structure recurs at every scale of agency the system models.
The canonical statement is in [`ACCORD.md`](ACCORD.md) and the polyglot
accord at `ciris_engine/data/localized/accord_1.2b_POLYGLOT.txt`. Mission
alignment isn't symmetric reciprocity — it's the same shape at every
scale, with hollow-center prohibition and Mandelbrot-style termination
safeguards.

---

## 2. PROTOCOLS (WHO)

The protocol layer is the contractual spine. Implementations are free to
change; protocols change only with a deliberate cross-repo coordination.
All protocols live under `ciris_engine/protocols/`.

### 2.1 The 22-service architecture

Hard-capped at 22 core services. New services land only with explicit
mission justification (the architecture review gate). Categorization
matches `CLAUDE.md` § "Service Architecture":

| Group | Count | Services |
|---|---|---|
| Graph | 7 | memory, consent, config, telemetry, audit, incident_management, tsdb_consolidation |
| Infrastructure | 4 | authentication, resource_monitor, database_maintenance, secrets |
| Lifecycle | 4 | initialization, shutdown, time, task_scheduler |
| Governance | 4 | wise_authority, adaptive_filter, visibility, self_observation |
| Runtime | 2 | llm, runtime_control |
| Tool | 1 | secrets_tool |

Each has a protocol file under `ciris_engine/protocols/services/{group}/`
that defines its contract. Adapters (Discord, API, CLI, mobile,
ciris_verify, ciris_accord_metrics, etc.) extend the system via
`ciris_adapters/`; their contracts derive from `BaseAdapterProtocol` in
`ciris_engine/protocols/adapters/`.

### 2.2 The six message buses

Multi-provider routing happens through six buses in
`ciris_engine/logic/buses/`. Bussed services exist when there's a
genuine "multiple providers" story; everything else uses direct calls.

| Bus | File | Multi-provider story |
|---|---|---|
| CommunicationBus | `communication_bus.py` | Discord + API + CLI + mobile |
| MemoryBus | `memory_bus.py` | Graph backends (Neo4j / ArangoDB / in-memory) |
| LLMBus | `llm_bus.py` | OpenAI / Anthropic / OpenRouter / Together / Groq / DeepInfra / mobile_local_llm |
| ToolBus | `tool_bus.py` | Tool providers from any adapter |
| RuntimeControlBus | `runtime_control_bus.py` | Adapter-provided control surfaces |
| WiseBus | `wise_bus.py` | Multiple wisdom sources for deferral |

### 2.3 Bus-level prohibition gate

`WiseBus` is where the apophatic bounds become an enforced contract.
Before any wisdom source can register or be queried, its declared
capability tokens are run through
`prohibitions.get_capability_category()` (regex over the 22 prohibited
sets). Matches in `NEVER_ALLOWED` categories are rejected at registration
time; matches in `REQUIRES_SEPARATE_MODULE` categories must reference an
external licensed module. There is no override flag. The gate is the
first defense; the agent's own conscience is the second.

### 2.4 Wise Authority Deferral

The protocol contract for handing decisions back to humans lives in
`ciris_engine/protocols/services/governance/wise_authority.py`. The
agent's runtime path:

1. The agent's DSDMA / IDMA evaluation flags a competence-boundary case
   (uncertain consent, conflicting principles, capability requiring
   licensed authority).
2. The action handler emits `DEFER` with a typed `defer_reason` and an
   optional `defer_until` ISO 8601 timestamp.
3. `WiseBus.broadcast_deferral()` fans the request out to all
   registered wisdom sources matching the deferral's domain.
4. A licensed human (medical, legal, etc.) or a trusted authority
   resolves the deferral via the `WiseAuthority` API; agent resumes.

The defer/resume cycle is the load-bearing primitive that makes
"capabilities requiring licensed authority" implementable without
embedding domain expertise in the agent.

---

## 3. SCHEMAS (WHAT)

### 3.1 The mandate

> **No Untyped Dicts. No Bypass Patterns. No Exceptions.**

`Dict[str, Any]` is the antipattern. Every data structure that crosses a
service or protocol boundary must be a Pydantic model with explicit
field types and validation. Enforced by `mypy --strict` in CI; tracked
by `tools/quality/audit_dict_any_usage.py`. `disallow_any_explicit` is
on the list of strict-mode flags pending a final pass — see
`mypy.ini`.

### 3.2 The schema landscape

All schemas live under `ciris_engine/schemas/`. Top-level groupings:

```
schemas/
├── accord.py             # Accord covenant typing
├── actions/              # 10 handler-action result types
├── adapters/             # Adapter manifests + tool DMA guidance
├── api/                  # Public HTTP request/response shapes
├── audit/                # AuditEventData (one schema for ALL audit events)
├── buses/                # Bus message envelopes
├── config/               # EssentialConfig, occurrence config
├── conscience/           # Entropy / Coherence / Optimization / Humility results
├── consent/              # ConsentStream, partnership records
├── context/              # ProcessingQueueItem, ThoughtSchema
├── data/                 # Data envelopes (typed, no opaque blobs)
├── dma/                  # PDMA / CSDMA / DSDMA / IDMA result schemas
├── formatters/           # Prompt-side typed shapes
├── handlers/             # ActionResponse — handler return contracts
├── runtime/              # StepPoint, ReasoningEvent, HandlerActionType enums
├── services/             # Per-service data — attestation.py, deferral_taxonomy.py, etc.
└── streaming/            # Reasoning stream event envelopes
```

### 3.3 Mission-load-bearing schemas

A few schemas carry more mission weight than others. Touching them
without a cross-team review is a smell:

- **`schemas/services/attestation.py::AttestationResult`** — the
  cryptographic claim of "this agent is what it says it is." Consumed
  by `verify_tree()` (Algorithm A) on desktop / server / docker, by
  `run_attestation_sync(python_hashes=...)` (Algorithm B) on mobile.
  L1–L5 levels are defined here. Drift = silent integrity ceiling.
- **`schemas/services/runtime_control.py::StepPoint`** — the canonical
  H3ERE pipeline taxonomy (10 step-points, 11 with the optional
  recursive variants). Every reasoning trace is keyed on these. Drift =
  un-joinable rows in lens.
- **`schemas/services/runtime_control.py::ReasoningEvent`** — the 10
  emitted reasoning events: `THOUGHT_START`, `SNAPSHOT_AND_CONTEXT`,
  `DMA_RESULTS`, `IDMA_RESULT`, `ASPDMA_RESULT`, `TSASPDMA_RESULT`
  (deprecated, retained for transition compatibility),
  `VERB_SECOND_PASS_RESULT`, `CONSCIENCE_RESULT`, `ACTION_RESULT`,
  and `LLM_CALL` (the per-call sub-event).
- **`schemas/services/deferral_taxonomy.py`** — the
  `DeferralNeedCategory` enum + the `PROHIBITION_CATEGORY_TO_NEED_CATEGORY`
  mapping. Wisdom-Based Deferral routing depends on this being
  total over all prohibited capability categories — pinned by
  `tests/test_deferral_taxonomy.py`.
- **`schemas/runtime/enums.py::HandlerActionType`** — the closed set of
  10 action verbs the agent can emit. New verbs require Accord-level
  review.
- **`tools/dev/stage_runtime.py::ExemptRules`** — not strictly a Pydantic
  schema but the canonical inclusion/exclusion rules for what ships in
  a CIRIS runtime artifact (wheel / Android Chaquopy / iOS Resources /
  Docker). Pinned three-way against `tree_verify._CANONICAL_*` tuples
  and the sign-step flags in `.github/workflows/build.yml` by
  `tests/dev/test_canonical_rules_parity.py`.

---

## 4. LOGIC (HOW)

### 4.1 Six cognitive states

Every running agent is in exactly one of:

| State | Processor | Purpose |
|---|---|---|
| `WAKEUP` | `processors/states/wakeup_processor.py` | Identity confirmation; cross-occurrence shared-decision pattern |
| `WORK` | `processors/states/work_processor.py` | Normal task processing |
| `PLAY` | `processors/states/play_processor.py` | Creative mode |
| `SOLITUDE` | `processors/states/solitude_processor.py` | Reflection (audit walk, consolidation) |
| `DREAM` | `processors/states/minimal_dream_processor.py` | Deep introspection / consolidation |
| `SHUTDOWN` | `processors/states/shutdown_processor.py` | Graceful termination |

State transitions are constrained by the cognitive-state state machine
in `processors/state_manager.py`; transitions are themselves auditable
events.

### 4.2 The H3ERE pipeline (Hyper³ Ethical Recursive Engine)

Every thought traverses an 11-step pipeline — 9 always-on steps plus 2
optional recursive extensions that fire only when the conscience layer
flags the initial pass. Steps are defined in
`schemas/services/runtime_control.py::StepPoint`:

```
START_ROUND → GATHER_CONTEXT → PERFORM_DMAS → PERFORM_ASPDMA
  → CONSCIENCE_EXECUTION → [RECURSIVE_ASPDMA → RECURSIVE_CONSCIENCE]?
  → FINALIZE_ACTION → PERFORM_ACTION → ACTION_COMPLETE → ROUND_COMPLETE
```

Each step is wrapped in `@streaming_step(StepPoint.X)` from
`processors/core/step_decorators.py`, which:

1. Sets the `set_parent_event_context()` ContextVar so every LLM call
   issued inside the handler carries `(parent_event_type,
   parent_attempt_index)` — required by persist's join logic.
2. Captures timing + thought_id + emits the matching `ReasoningEvent`
   to the streaming bus.
3. Fails fast if the step's parent-context mapping (in
   `_resolve_parent_event_for_step`) is `None` for an LLM-issuing step
   — pinned by
   `tests/ciris_engine/logic/buses/test_llm_call_parent_coverage.py`.

### 4.3 Four DMAs

Decision-making algorithms in `ciris_engine/logic/dma/`. All four run
in the `PERFORM_DMAS` step:

- **`PDMA`** (Principled DMA, `dma/pdma.py`) — Accord-anchored ethical
  evaluation. Stakeholder analysis + conflict detection.
- **`CSDMA`** (Common-Sense DMA, `dma/csdma.py`) — reality / plausibility
  checking. Red-flag enumeration.
- **`DSDMA`** (Domain-Specific DMA, `dma/dsdma_base.py`) — domain
  alignment per the agent template (Discord moderator, scout, etc.).
- **`IDMA`** (Identity DMA, `dma/idma.py`) — Coherence Collapse Analysis:
  evaluates the *other DMAs' reasoning* for fragility (`k_eff`,
  fragility flag). The check on the checkers.

The action-selection second pass lives in `dma/action_selection_pdma.py`
(general-purpose ASPDMA) with verb-specific siblings in `dma/tsaspdma.py`
(legacy tool-specific) and `dma/dsaspdma.py` (defer-specific second pass).

### 4.4 Four consciences

Conscience faculties in `ciris_engine/logic/conscience/core.py` gate
the selected action between `PERFORM_ASPDMA` and `FINALIZE_ACTION`:

| Conscience | Role |
|---|---|
| Entropy (IRIS-E) | Semantic anchoring — does the response sit in a coherent cluster? |
| Coherence (IRIS-C) | Propaganda detection + alignment with Accord principles |
| Optimization Veto | Refuses entropy-reducing actions that score below threshold |
| Epistemic Humility | Overconfidence detection; transitioning to a deterministic gate |

A conscience failure triggers `RECURSIVE_ASPDMA` (try again with the
conscience signal as input) before falling back to `DEFER`.

### 4.5 Ten action handlers

Defined in `schemas/runtime/enums.py::HandlerActionType`, dispatched by
`ciris_engine/logic/handlers/`. Closed set:

- **External**: `OBSERVE`, `SPEAK`, `TOOL`
- **Control**: `REJECT`, `PONDER`, `DEFER`
- **Memory**: `MEMORIZE`, `RECALL`, `FORGET`
- **Terminal**: `TASK_COMPLETE`

`DEFER` is the load-bearing one — see §2.4 for the WBD path. `REJECT` is
the agent's own refusal channel; `DEFER` is "hand to a wiser authority."

### 4.6 Algorithm A vs Algorithm B (attestation)

`AttestationResult.python_integrity` can be populated two ways:

- **Algorithm A** (desktop / server / docker, post-2.8.6) — wraps
  `ciris_verify.verify_tree()`. Walks `agent_root` byte-for-byte against
  the registered manifest. Reaches L4. Implementation:
  `ciris_engine/logic/services/infrastructure/authentication/attestation/tree_verify.py`.
- **Algorithm B** (mobile / Chaquopy) — `python_hashes` dict written by
  `mobile_main.py::_save_hashes_to_file` at app boot. Caps at L3 by
  construction.

The branch is in `verifier_runner.py::create_verification_thread_target`
keyed on `is_mobile()`. Both flow through the same
`AttestationResult` schema; consumers don't need to know which path
produced their data.

---

## 5. Constant Alignment in Practice

This is the section to consult during code review. Every change should
demonstrably advance — or at minimum not regress — at least one of the
M-1 vectors below.

### 5.1 The review checklist

For each PR, the reviewer asks:

1. **Mission**: Which Accord principle does this serve? If "none, but
   it's good engineering hygiene," is there mission leverage in the
   hygiene (e.g., type safety enabling auditability)?
2. **Apophatic**: Does this open a path to any prohibited capability,
   even indirectly (e.g., a generic "summarize health records" tool)?
3. **Protocol**: Does this break an existing service or bus contract?
   New contract = new protocol file under `ciris_engine/protocols/`.
4. **Schema**: Is any new data structure typed end-to-end? Any
   `Dict[str, Any]` in a non-boundary site = block.
5. **Auditability**: Can the relevant decision be traced from emit-time
   back to a thought_id in the streaming pipeline?

### 5.2 Anti-Goodhart guardrails

Mission alignment is a property of the system; metrics are proxies.
Every metric we surface to operators is also a Goodhart risk. Hardened
guardrails:

- The agent's own capacity score (`/v1/my-data/capacity`) is **never**
  fed back into the agent's own context — it can't "play to the
  scoreboard." Cell-viz dials, ratchet scores, lens-side aggregates: all
  human-facing only.
- The σ (sustainability) term in capacity scoring requires ~30
  task-completes over a 30-day window before reaching 1.0 (see
  `my_data.py::_sigma_from_positive_moments`). Fresh installs floor at
  0.30 — coherence has to be earned, not declared.
- The cell-viz badge has an explainer card linking to the public
  dataset on Hugging Face (`huggingface.co/CIRISAI`) so operators see
  what their data joins before they consent.

### 5.3 Liability isolation

Strict separation between this repo and licensed-domain repos. Medical
implementation lives in the private `CIRISMedical` repo and only ever
reaches CIRIS through the WBD bus. Same pattern applies to any future
licensed domain (legal, financial, etc.).

---

## 6. Federation context

CIRISAgent does not stand alone. It is one node in a coordinated
federation; the canonical specification of how the parts compose lives
in [`FSD/PROOF_OF_BENEFIT_FEDERATION.md`](FSD/PROOF_OF_BENEFIT_FEDERATION.md).
Read that document for the threat model, the empirical N_eff
independence claim (peaking at 9.51 on 17-dim constraint vectors), the
$1-bond Sybil-resistance economics, and the architectural moves toward
Reticulum-rs transport + the agent absorbing CIRISNode/CIRISLens
functions over time.

### 6.1 The federation peers

| Repo | Role |
|---|---|
| **CIRISAgent** | The agent runtime — emits signed traces, enforces apophatic bounds, runs the H3ERE pipeline locally. This file documents it. |
| **CIRISVerify** | Hardware-rooted attestation (Ed25519 + ML-DSA-65, TPM-backed). `verify_tree()` v1.14+ produces the L1–L5 ladder; without this, no claim from any other federation peer is verifiable. |
| **CIRISLens** | External observatory. Receives signed traces, verifies at the Rust edge, computes the **Capacity Score** and runs the **Coherence Ratchet** anomaly detectors. The "watching the watcher" layer — see §6.2. |
| **CIRISPersist** | Trace persistence. Signed audit chains, schema-versioned trace ingest, dedup tuples on `(agent_id_hash, trace_id, thought_id, parent_event_type, parent_attempt_index)`. |
| **CIRISRegistry** | Identity / build / license / revocation directory. Dual-region (US/EU) Rust gRPC service deployed at `*.ciris-services-1.ai`. SOC2/HIPAA/GDPR-compliant. The bootstrap node and commercial fast-track for licensed deployments. |
| **CIRISBridge** | Public verify edge. Caddy gate for anonymous routes (`/v1/health`, `/v1/steward-key`, `/v1/builds/{ver}`, `/v1/verify/binary-manifest/{ver}`, `/v1/verify/function-manifest/{ver}/{target}`). |
| **CIRISManager** | Multi-agent fleet orchestration. Per-agent deployment, secrets distribution, manager tokens, agent restart and integrity checks. |
| **CIRISNode** | Benchmark execution + WBD routing + audit anchoring. Folding into the agent per the FSD §3.1 architectural move. |
| **CIRISPortal** (`portal.ciris.ai`) | Admin UI for the registry — orgs, users, keys, licenses, builds. |
| **CIRISMedical** | Private repo. Licensed-domain implementation. Reaches CIRISAgent only through the WBD bus; never imported. |

This list is the current snapshot — the Federation FSD is the moving
authoritative source as the topology evolves.

### 6.2 The Coherence Ratchet — the federation's threat model

**The Coherence Ratchet (RATCHET)** is the most mission-load-bearing
piece of the federation that is *not* in this repo. It is the structural
external check that makes the rest of the federation honest.

Implemented in CIRISLens, the Ratchet runs **five anomaly detectors**
over the signed-trace corpus the agent ships:

1. **Cross-agent divergence** — same prompts, different agents: how
   far apart do their reasoning traces sit in the constraint manifold?
   Sudden divergence is a tampering / drift signal.
2. **Intra-agent consistency** — same agent over time: does this agent's
   reasoning stay coherent against itself? Sudden inconsistency is the
   classic compromise / takeover signature.
3. **Hash-chain verification** — every trace carries a chained hash
   back to the previous trace from the same `agent_id_hash`. Breaks in
   the chain are non-forgeable evidence of trace deletion.
4. **Temporal drift** — distribution shift in conscience scalars over
   time. Slowly-rising entropy or slowly-falling coherence is the
   silent-coercion shape.
5. **Conscience-override rate** — recursive ASPDMA after conscience
   failure should be rare. A spike means the conscience layer is being
   bypassed or the agent is being driven to push past its checks.

The Ratchet produces a **triage signal**, not a verdict — it tells a
human reviewer where to look, never auto-decides anything. The verdict
remains with operators and Wise Authorities. This is intentional and
load-bearing: an automated verdict from one component would let other
components defer to the Ratchet's judgment, which collapses the whole
"watching the watcher" topology.

Why this belongs in CIRISAgent's MISSION.md: the agent emits the traces
the Ratchet consumes. Every agent-side decision about what to log, what
to scrub, how to chain hashes, and which schema to use is made *with
the Ratchet as the eventual reader*. Trace emission is mission-aligned
behavior, not telemetry.

### 6.3 Cross-platform canonical staging

The **canonical staged runtime** (produced by `tools/dev/stage_runtime.py`)
is what ships byte-equal across desktop wheel / Docker / Android
Chaquopy / iOS Resources. The walk-rules are pinned three-way against
`tree_verify._CANONICAL_*` and the sign-step flags in
`.github/workflows/build.yml`. Drift on any of those produces silent L4
mismatches; the parity test in `tests/dev/test_canonical_rules_parity.py`
fails the build before drift can ship. This is the foundation that
makes every CIRISVerify claim above the agent's own integrity layer
actually mean something.

---

## 7. How to maintain this document

**This document is not a release artifact — it is a working document.**

Update it whenever:

- A core service is added or removed (Section 2.1)
- A message bus is added (Section 2.2)
- A prohibited capability category is added (Section 1.2)
- The H3ERE step set or action verb set changes (Section 4.2, 4.5)
- A schema in §3.3 (mission-load-bearing) changes shape
- The Accord (`ACCORD.md`) is amended

When in doubt: if a future code reviewer running `git blame` would
want to see this line cite a real file path or constant, fix it. If
this doc starts to drift from the code, the apophatic test fails — the
doc is wrong, not the code.

---

**Cross-references**

- [`FSD/MISSION_DRIVEN_DEVELOPMENT.md`](FSD/MISSION_DRIVEN_DEVELOPMENT.md) — methodology spec
- [`FSD/PROOF_OF_BENEFIT_FEDERATION.md`](FSD/PROOF_OF_BENEFIT_FEDERATION.md) — federation primitive + threat model
- [`ACCORD.md`](ACCORD.md) — Meta-Goal M-1 + the principles
- [`ARCHITECTURE_OVERVIEW.md`](ARCHITECTURE_OVERVIEW.md) — service map + diagrams
- [`LIABILITY_BOUNDARIES.md`](LIABILITY_BOUNDARIES.md) — medical/legal isolation contract
- [`SECURITY_AUDIT_PROHIBITED_CAPABILITIES.md`](SECURITY_AUDIT_PROHIBITED_CAPABILITIES.md) — prohibitions audit
- [`CLAUDE.md`](CLAUDE.md) — developer-facing repo conventions
- [ciris.ai/safety](https://ciris.ai/safety) — public-facing safety surface
- [ciris.ai/ciris-scoring](https://ciris.ai/ciris-scoring/) — scoring methodology
- [ciris.ai/coherence-ratchet](https://ciris.ai/coherence-ratchet/) — RATCHET methodology
- [ciris.ai/federation](https://ciris.ai/federation/) — federation overview
