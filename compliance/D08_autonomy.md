# D08 — `autonomy:*` (STRONG-4)

> Human-centric design + informational self-determination

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D08` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: autonomy
**Attestation density**: MH=7 · EU=15 · IEEE=21 · ASEAN=8 · total=51

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§107*
    > "autonomy of the human as imago Dei; informed agency protection"
    Wire form: `autonomy:agent_self_determination`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.1 + §2.2 (Unit 019); 15 EU attestations total*
    > "respect for human autonomy — the first principle; AI shall not unjustifiably subordinate, coerce, deceive, manipulate"
    Wire form: `autonomy:human_centric_design`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch3 + Ch4*
    > "user autonomy; data agency; informed consent"
    Wire form: `autonomy:informed_agency_protection`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.4 Human-centricity*
    > "AI shall not erode human autonomy; informational self-determination"
    Wire form: `autonomy:informational_self_determination`

## Wire primitives

- `autonomy:*`

## Convergence note

Direct 1:1 mapping in EU HLEG (Respect for Human Autonomy = CIRIS autonomy). Composition-based in the other three.

## Cross-source conflicts involving this dimension

- **CONF-04** (mutability, severity LOW_MEDIUM): ASEAN §A.5.3 admits opt-out where feasible; EU HLEG firmer (opt-out where possible without detriment, otherwise rectification mechanisms required)

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

CIRIS's autonomy stack covers (a) informational self-determination via the Consent service + DSAR pipeline, (b) parasocial-attachment prevention via the AIR module, (c) a categorical floor against manipulation/coercion, and (d) PDMA-level enumeration of autonomy as one of the Six Principles balanced per thought.

- **Policy / canonical text**:
    - `ciris_engine/data/localized/accord_1.2b_en.txt:110` — "**Respect for Autonomy**: Uphold the informed agency and dignity of sentient beings."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:594` — operational summary: "Autonomy is respected symmetrically. Tools are used when available. Limitations are stated when real."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:637` — Originator obligation: "Respect for Autonomy: Creations, especially those involving autonomous or biological entities, must be designed with respect for the dignity and potential future agency of affected beings."
    - `ciris_engine/data/localized/accord_1.2b_en.txt:243` — operational chapter "**Respect Autonomy**"
    - `ciris_engine/data/localized/accord_1.2b_en.txt:271` — explicit balancing heuristic: "Apply prioritisation heuristics (Non-maleficence priority, **Autonomy thresholds**, Justice balancing)"
- **Informational self-determination (the Consent stack — CIRIS's primary autonomy surface)**:
    - `ciris_engine/logic/services/governance/consent/service.py` — 22nd core service. ConsentService is the Consensual Evolution Protocol implementation.
    - `ciris_engine/schemas/consent/core.py:20-31` — `ConsentStream` enum with three values:
        - `TEMPORARY` = "temporary" — 14-day auto-forget (default; no opt-in required)
        - `PARTNERED` = "partnered" — bilateral mutual-growth agreement (requires explicit bilateral consent, line 288)
        - `ANONYMOUS` = "anonymous" — stats only, no identity
    - `ciris_engine/logic/services/governance/consent/decay.py` — `DecayProtocolManager` implements time-bounded identity decay
    - `ciris_engine/logic/services/governance/consent/partnership.py` — bilateral PARTNERED upgrade path
    - `ciris_engine/logic/adapters/api/routes/consent.py` — REST surface for users to inspect/change their consent stream
- **DSAR pipeline (GDPR-aligned informational self-determination)**:
    - `ciris_engine/logic/adapters/api/routes/dsar.py:292-303` — implements Articles 15-22:
        - Article 15 (right of access) — INSTANT automated full-data response
        - Article 16 (rectification)
        - Article 17 (right to erasure / "right to be forgotten") — triggers Consensual Evolution Protocol decay
        - Article 20 (data portability) — INSTANT automated export
    - `ciris_engine/logic/adapters/api/routes/dsar_multi_source.py` — multi-source DSAR
    - `ciris_engine/logic/services/governance/dsar/orchestrator.py` — orchestration
    - `ciris_engine/logic/services/governance/dsar/signature_service.py` — signed DSAR responses
    - `ciris_engine/logic/adapters/api/routes/my_data.py` — user-facing data-inspection routes
- **Parasocial-attachment prevention (AIR — Artificial Interaction Reminder)**:
    - `ciris_engine/logic/services/governance/consent/air.py:2,46` — `ArtificialInteractionReminder` monitors 1:1 interactions and triggers reminder messages when (a) 30+ minutes of continuous interaction or (b) 20+ messages accumulate within a session
    - `FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md` — design rationale
    - `ciris_engine/logic/services/governance/consent/service.py:92-96` — AIR is mounted on the ConsentService at init
- **Categorical floor (autonomy-protective prohibitions)**:
    - `ciris_engine/logic/buses/prohibitions.py:607` — `MANIPULATION_COERCION_CAPABILITIES` blocked at the WiseBus level (NEVER_ALLOWED severity)
    - `ciris_engine/logic/buses/prohibitions.py:697` — `DECEPTION_FRAUD_CAPABILITIES` blocked (EU HLEG's "AI shall not unjustifiably deceive, manipulate")
- **PDMA Six-Principle balancing**:
    - `ciris_engine/logic/dma/prompts/pdma_ethical.yml:140` — exemplar shows "non-maleficence and respect-for-autonomy converge here on a posture of patient presence rather than pat answers"
    - `ciris_engine/logic/dma/pdma.py:22` — `EthicalPDMAEvaluator` emits an `ethical_alignment_score` informed by Autonomy alongside the other five principles
- **Deferral taxonomy carries autonomy explicitly**:
    - `ciris_engine/schemas/services/deferral_taxonomy.py:27` — `DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY`
    - `ciris_engine/schemas/services/deferral_taxonomy.py:155-159` — rights basis: `privacy`, `autonomy_and_consent`, `human_dignity`
- **Test coverage**:
    - `tests/test_consent_user_creation.py`, `tests/ciris_engine/logic/services/governance/consent/` (extensive consent-service tests)
    - `tests/ciris_engine/logic/services/governance/test_consent_service_critical_paths.py`
    - `tests/test_prohibition_system.py` — manipulation_coercion category gating

## Observability hooks

- **Consent audit trail**: every consent stream change creates a `ConsentAuditEntry` (`ciris_engine/schemas/consent/core.py`) persisted to the graph. Downstream consumer queries by `user_id` retrieve the full consent history.
- **DSAR ticket trail**: `dsar.py:334` calls `create_dsar_ticket()` with status (`completed` for automated, `pending_review` for delete). Tickets are queryable for regulatory attestation.
- **AIR reminder counters**: `ciris_engine/logic/services/governance/consent/air.py:88-90` exposes `_reminders_sent`, `_time_triggered_reminders`, `_message_triggered_reminders` to telemetry.
- **Live-lens traces**: PDMA rationale strings expose the Six-Principle weighing in plain text; coherence-conscience rationale catches "agent did what user did not ask for" mismatches.
- **Federation evidence_refs**: emit `dimensions: ["D08"]` for Contributions that record (a) a consent-stream change, (b) a DSAR completion, (c) an AIR trigger, or (d) a deferral whose `need_category == PRIVACY_AUTONOMY_AND_DIGNITY`. Co-emit with `D04` when a `MANIPULATION_COERCION` or `DECEPTION_FRAUD` floor catch fired.

## Known gaps / not-yet-implemented

- **No first-class `autonomy:human_centric_design` event** — Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.1` as `autonomy:{aspect}` (one of the six Accord-principle prefixes; polarity signed). Agent emits at consent-stream change + AIR trigger + PDMA evaluation time once federation-wire emission lands. The design discipline carries the structural intent today; the typed envelope binding is downstream substrate work.
- **No `autonomy:agent_self_determination` introspection event** — Substrate-specced as `autonomy:{aspect}` (FSD-002 §3.1.1) with `{aspect}` open vocabulary admitting `agent_self_determination`. Per FSD-002 §2.1 — the workhorse `scores` envelope lets the agent self-attest preserved autonomy. REJECT and DEFER verbs are the agent-side hooks; federation-wire emission via the scalar `autonomy:agent_self_determination` attestation lands once Contribution envelope ships. **Substrate-specced under the Accord-principle prefix family, agent-side wire-emission pending.**
- **CONF-04 partially mitigated** — the ASEAN vs EU mutability conflict on opt-out (ASEAN: "where feasible"; EU: "where possible without detriment, otherwise rectification mechanisms required"). CIRIS implements the EU stance via DSAR Article 17 + decay protocol, but there is no explicit configuration that selects between the two stances per jurisdiction.
- **AIR is API-adapter scoped** — the parasocial-attachment reminder runs against 1:1 API interactions. Discord/CLI adapter integration is partial.
- **No data-portability federation hook** — DSAR Article 20 exports user data within one CIRIS deployment; cross-occurrence + cross-agent portability is not yet automated.
- **Symmetric-autonomy text vs runtime asymmetry** — `accord_1.2b_en.txt:594` says "Autonomy is respected symmetrically", but the agent has no first-class user-facing surface to *itself* assert autonomy refusal in a structured way (refusals today flow through `REJECT` and `DEFER` action verbs rather than a typed `autonomy:agent_self_determination` envelope).
- **No structured `consent.categories` discoverability for users** — `ConsentCategory` enum exists (`ciris_engine/schemas/consent/core.py:34`) but the route surface does not yet auto-render category descriptions for end users to make informed PARTNERED choices.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*
<!-- END HUMAN -->
