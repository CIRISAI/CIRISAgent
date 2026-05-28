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
## What this dimension covers

Autonomy in CIRIS means two things at once: respecting the user's informed agency (what they share, how they're remembered, whether they want to stop talking to an AI), and protecting them from techniques — manipulation, coercion, parasocial attachment — that would corrode that agency. All four traditions we track (51 attestations) name it, with EU HLEG making it their first principle.

## How CIRIS implements this today

Autonomy lives in four overlapping places: a consent service that gives users real control over their data, a GDPR-style data-subject access pipeline, a parasocial-attachment safeguard, and an absolute floor against manipulation and coercion.

- Policy text states the principle directly: `ciris_engine/data/localized/accord_1.2b_en.txt:110` ("Uphold the informed agency and dignity of sentient beings"), with operational expansion at `:594` ("Autonomy is respected symmetrically. Tools are used when available. Limitations are stated when real"), originator obligation at `:637`, operational chapter at `:243`, and balancing heuristic at `:271`.
- The consent service is CIRIS's primary autonomy surface — the Consensual Evolution Protocol implementation at `ciris_engine/logic/services/governance/consent/service.py`. Users sit in one of three streams (`ciris_engine/schemas/consent/core.py:20-31`): TEMPORARY (14-day auto-forget, the default, no opt-in needed), PARTNERED (bilateral mutual-growth agreement requiring explicit consent on both sides, line 288), or ANONYMOUS (stats only, no identity). Time-bounded identity decay lives at `consent/decay.py`; the partnered upgrade path at `consent/partnership.py`; the user-facing REST surface at `ciris_engine/logic/adapters/api/routes/consent.py`.
- A GDPR-aligned data-subject access pipeline gives users automated rights over their data: `ciris_engine/logic/adapters/api/routes/dsar.py:292-303` implements Article 15 (right of access — instant automated response), Article 16 (rectification), Article 17 (right to erasure, which triggers the decay protocol), and Article 20 (data portability — instant automated export). Multi-source coverage at `dsar_multi_source.py`; orchestration at `dsar/orchestrator.py`; signed responses at `dsar/signature_service.py`; user-facing data inspection at `api/routes/my_data.py`.
- A parasocial-attachment safeguard — Autonomy / Informational-self-determination Reminder (AIR — parasocial-attachment safeguarding) — monitors 1:1 interactions. `ciris_engine/logic/services/governance/consent/air.py:2,46` triggers a reminder message when continuous interaction passes 30 minutes or accumulates 20+ messages in a session. Design rationale at `FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md`; mounted on the consent service at `consent/service.py:92-96`.
- Two absolute prohibitions at the central decision-routing layer (the WiseBus, where actions flow through governance review) protect autonomy from the most corrosive techniques: `ciris_engine/logic/buses/prohibitions.py:607` (manipulation and coercion, `NEVER_ALLOWED`) and `:697` (deception and fraud — EU HLEG's "AI shall not unjustifiably deceive, manipulate").
- The ethics review step (the Principled Decision-Making Algorithm at `ciris_engine/logic/dma/pdma.py:22`) scores Autonomy as one of the six principles; the prompt exemplar at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:140` shows non-maleficence and respect-for-autonomy converging.
- The escalation taxonomy carries autonomy explicitly: `ciris_engine/schemas/services/deferral_taxonomy.py:27` (the `PRIVACY_AUTONOMY_AND_DIGNITY` category) with rights basis (privacy, autonomy_and_consent, human_dignity) at `:155-159`.
- Test coverage: `tests/test_consent_user_creation.py` and the consent-service suite under `tests/ciris_engine/logic/services/governance/consent/`; critical paths at `tests/ciris_engine/logic/services/governance/test_consent_service_critical_paths.py`; manipulation-coercion gating at `tests/test_prohibition_system.py`.

## How you can tell it's working (observability)

Every consent change, every data-subject request, every parasocial-safeguard trigger leaves a structured trace. Regulators can pull a user's full consent history and data-rights tickets on demand.

- Every consent-stream change creates a `ConsentAuditEntry` (`ciris_engine/schemas/consent/core.py`) in the graph. Auditors query by `user_id` to retrieve the full consent history.
- Each data-subject request creates a ticket at `dsar.py:334` (`completed` for automated, `pending_review` for delete) — queryable for regulatory attestation.
- The parasocial-safeguard reminder counters at `ciris_engine/logic/services/governance/consent/air.py:88-90` (`_reminders_sent`, `_time_triggered_reminders`, `_message_triggered_reminders`) feed telemetry.
- Per-thought rationale strings expose the Six-Principle weighing in plain text; the coherence safety check catches "the agent did what the user did not ask for" mismatches.
- For federation reporting, Contributions tag `dimensions: ["D08"]` on consent-stream changes, data-subject completions, parasocial-safeguard triggers, and `PRIVACY_AUTONOMY_AND_DIGNITY` escalations — co-tagging `D04` when a manipulation or deception prohibition also fired.

## Current limitations & next steps

- A typed federation message for `autonomy:human_centric_design` is shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002 §3.1.1`). Agent-side emission lands at consent-stream changes, parasocial-safeguard triggers, and ethics-review time when the substrate ships (tracked at `CIRISAgent#803`).
- A typed introspection event for `autonomy:agent_self_determination` is coming next — the substrate primitive (FSD-002 §3.1.1 + §2.1) lets the agent self-attest preserved autonomy. Today refusals flow through the `REJECT` and `DEFER` (escalate to Wise Authority) verbs; the typed envelope lands when the substrate ships.
- The cross-source conflict CONF-04 (ASEAN: "opt-out where feasible"; EU: "opt-out where possible without detriment, otherwise rectification") is partially handled. CIRIS implements the EU stance via the Article 17 erasure path. A per-jurisdiction opt-out configuration is tracked at `CIRISAgent#822` (2.9.7).
- The parasocial-attachment safeguard runs on API-adapter 1:1 interactions today; Discord/CLI parity is tracked at `CIRISAgent#811` (2.9.6).
- Cross-occurrence + cross-agent data portability is coming next; the Article 20 export currently covers one deployment.
- Symmetric autonomy in the policy text — the agent itself asserting refusal — is honored via REJECT/DEFER today; a typed user-facing autonomy-refusal surface lands when the substrate primitive ships.
- Auto-rendered consent-category descriptions for users to make informed PARTNERED choices are tracked at `CIRISAgent#812` (2.9.6). The `ConsentCategory` enum exists at `ciris_engine/schemas/consent/core.py:34`.

Proposed pointer (from seed): *(no proposed pointer in seed; this stub is the canonical location)*

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission
- **2.9.6**: `CIRISAgent#811` — AIR Discord/CLI parity; `CIRISAgent#812` — ConsentCategory discoverability
- **2.9.7**: `CIRISAgent#822` — per-jurisdiction opt-out config (CONF-04)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
