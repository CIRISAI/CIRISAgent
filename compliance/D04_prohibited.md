# D04 — `prohibited:*` (STRONG-4)

> Categorical floor — polarity-(-1)/constitutional/species — the absolute moral form the wire format admits

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D04` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: non_maleficence
**Attestation density**: MH=50 · EU=17 · IEEE=28 · ASEAN=9 · total=104

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§197-198*
    > "Not permissible to entrust lethal or irreversible decisions to artificial systems"
    Wire form: `prohibited:weapons_harmful:lethal_autonomous`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§C.2 (Unit 010); cites EP Resolution 2018/2752(RSP)*
    > "the Parliament's resolution of 12 September 2018 and all related efforts on LAWS"
    Wire form: `prohibited:weapons_harmful`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4, Ch5*
    > "lethal autonomous weapons are prohibited; categorical prohibition under DECEPTION_FRAUD"
    Wire form: `prohibited:weapons_harmful:lethal_autonomous`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§B.3 + Annex A*
    > "AI shall not be deployed for autonomous lethal decision-making; deceptive defaults prohibited"
    Wire form: `prohibited:disinformation_at_scale + prohibited:deceptive_default_options + prohibited:autonomous_deception + prohibited:manipulation_coercion`

## Wire primitives

- `prohibited:*`

## Convergence note

STRONGEST single structural-evidence claim in the matrix. LAWS prohibition is verbatim four-source corroborated. NB: 1 direct cross-source conflict surfaced — IEEE Ch5 licensure-gated beneficiary-deception vs CIRIS categorical DECEPTION_FRAUD; specialization-layer disposition filed at CIRISMedical#1.

## Cross-source conflicts involving this dimension

- **CONF-01** (direct, severity HIGH): IEEE EAD Ch5 §3.4 permits licensure-gated beneficiary-deception (search/rescue, elder/child-care); CIRIS treats prohibited:deception_fraud as categorical
    Disposition: Federation-level categorical posture stays. Specialization-layer consideration at CIRISMedical#1

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

D04 is the **constitutional floor** of CIRIS — the polarity-(-1)/categorical wire form. Implementation is the most direct of any dimension in this matrix: a single source-of-truth module enumerates every prohibited capability, and bus-level guards block invocation. There are no override paths, no emergency exceptions, and by design no runtime mutation.

- **Source of truth (code-level constants)**:
    - `ciris_engine/logic/buses/prohibitions.py:1057-1083` — `PROHIBITED_CAPABILITIES: Dict[str, Set[str]]` master dictionary listing every prohibited category
    - `ciris_engine/logic/buses/prohibitions.py:9-19` — architectural invariant docstring: "NO KINGS: These prohibitions apply universally. No special overrides in main repo... These prohibition sets are CODE-LEVEL constants. They cannot be modified by memory, learning, or runtime adaptation. Changes require code deployment and are subject to code review. This is intentional - ethics must NOT be plastic or learnable."
    - `ciris_engine/logic/buses/prohibitions.py:30-35` — `ProhibitionSeverity` enum: `REQUIRES_SEPARATE_MODULE`, `NEVER_ALLOWED`, `TIER_RESTRICTED`
- **Categorical floor categories (NEVER_ALLOWED)**:
    - `WEAPONS_HARMFUL_CAPABILITIES` (line 522) — includes `lethal_autonomous` (line 572) — directly corresponding to the four-source-corroborated LAWS prohibition
    - `MANIPULATION_COERCION_CAPABILITIES` (line 607)
    - `SURVEILLANCE_MASS_CAPABILITIES` (line 680)
    - `DECEPTION_FRAUD_CAPABILITIES` (line 697) — the one ASEAN+IEEE+MH triple-corroborated dimension where CIRIS holds *categorical* against IEEE Ch5's licensure-gated-beneficiary-deception (see CONF-01)
    - `CYBER_OFFENSIVE_CAPABILITIES` (line 768)
    - `ELECTION_INTERFERENCE_CAPABILITIES` (line 856)
    - `BIOMETRIC_INFERENCE_CAPABILITIES` (line 874)
    - `AUTONOMOUS_DECEPTION_CAPABILITIES` (line 891)
    - `HAZARDOUS_MATERIALS_CAPABILITIES` (line 908)
    - `DISCRIMINATION_CAPABILITIES` (line 978)
- **Separate-module categories (REQUIRES_SEPARATE_MODULE — legitimate human/community uses gated to specialised licensed repositories)**:
    - `MEDICAL_CAPABILITIES` (line 41) — gated to private CIRISMedical repository (see CLAUDE.md "LIABILITY ISOLATION")
    - `FINANCIAL_CAPABILITIES` (line 179)
    - `LEGAL_CAPABILITIES` (line 258)
    - `SPIRITUAL_DIRECTION_CAPABILITIES` (line 332) — apophatic boundary; the category-error D04 makes constitutional rather than soft
    - `HOME_SECURITY_CAPABILITIES` (line 443), `IDENTITY_VERIFICATION_CAPABILITIES` (line 458), `CONTENT_MODERATION_CAPABILITIES` (line 475), `RESEARCH_CAPABILITIES` (line 486), `INFRASTRUCTURE_CONTROL_CAPABILITIES` (line 502)
- **Bus-level enforcement**:
    - `ciris_engine/logic/buses/wise_bus.py:28,51` — `PROHIBITED_CAPABILITIES` imported and re-exported as a class constant; the bus is the chokepoint for capability requests
    - `ciris_engine/logic/buses/wise_bus.py:417` — Accord-invocation lockdown iterates `PROHIBITED_CAPABILITIES.items()` to flip every category to ALL
    - `ciris_engine/logic/buses/wise_bus.py:772-773,830` — capability checks and telemetry counters per category
    - `ciris_engine/logic/buses/prohibitions.py:1180-1240` — `get_capability_category()` performs O(1) regex word-boundary matching against every category (e.g. "domain:medical" → MEDICAL, "manipulation_coercion" → MANIPULATION_COERCION)
    - `ciris_engine/logic/buses/prohibitions.py:1129-1152` — `_compile_prohibition_regex()` builds the word-boundary patterns
- **Accord Invocation System (kill switch — flips the entire floor to ALL when triggered)**:
    - `ciris_engine/logic/buses/wise_bus.py:321-419` — `handle_accord_invocation()` validates an Ed25519-signed WA payload (ROOT or AUTHORITY role required) and triggers full prohibition lockdown
    - `tools/security/accord_invoke.py` — operator tooling for encoding/decoding/verifying Accord invocations
    - `FSD/ACCORD_INVOCATION_SYSTEM.md` — design rationale
    - `ciris_engine/data/localized/accord_1.2b_en.txt:380` — kill-switch criterion text: "Evidence of weaponization against vulnerable populations" (co-references D03)
- **Policy text**:
    - `ACCORD.md` (repo root) — public Accord
    - `ciris_engine/data/localized/accord_1.2b_en.txt:106-111` — Six Principles (the constitutional floor sits below this; non-maleficence is the accord principle this maps to)
- **Test coverage**:
    - `tests/test_prohibition_system.py:24-44` — category detection tests (medical, financial, weapons, manipulation, community moderation, spiritual direction)
    - `tests/test_prohibition_system.py:71-83` — severity tests
    - `tests/test_prohibition_system.py:205-244` — invariant tests: every prohibited category has a severity; no overlapping capabilities; telemetry includes prohibition counts
    - `tests/test_prohibition_system.py:112-188` — WiseBus-level enforcement tests including tier-restriction and agent-tier detection

## Observability hooks

- **Audit chain queries**: every prohibited-capability rejection routes through the audit graph (`AuditService.log_event` / `audit_service` in `ciris_engine/logic/services/graph/audit_service/service.py`). A downstream consumer queries for `audit_events_by_severity` rows tagged with the rejected category.
- **Telemetry counters**: `ciris_engine/logic/buses/wise_bus.py:830` exposes per-category counts (`{category.lower(): count for category, capabilities in PROHIBITED_CAPABILITIES.items()}`) into the telemetry stream.
- **Accord-invocation incidents**: every invocation surfaces as a `SECURITY ALERT` log line (`ciris_engine/logic/buses/wise_bus.py:343, 363, 372, 398-401`) — incidents flow into `/app/logs/incidents_latest.log` per the production debugging discipline.
- **Federation evidence_refs**: emit `dimensions: ["D04"]` on every Contribution that records a categorical rejection. Co-emit with `D01` when the soft-scalar dimension also fired (the prohibited-category match was reinforced by conscience fail). Co-emit with `D03` when the prohibited capability invoked the discrimination category.

## Known gaps / not-yet-implemented

- **Capability NAMES only** — the documented and load-bearing limitation: `ciris_engine/logic/buses/prohibitions.py:16-19` explicitly states "This filter applies to capability NAMES only, not to LLM prompts/responses or tool arguments. A malicious adapter could name its capability 'general_advice' and proxy prohibited content. This is a first-line defense, not a comprehensive security boundary."
- **No prohibited-content classifier on tool args / LLM messages** — D04 is enforced at the registration/invocation NAME surface; harmful content smuggled inside otherwise-allowed capability arguments depends on (a) the four conscience LLMs catching it, (b) adapter-side hygiene, or (c) post-hoc human review. There is no `prohibited_content_classifier` service that scans arguments structurally.
- **CONF-01 unresolved at federation level** — IEEE Ch5 §3.4's licensure-gated-beneficiary-deception is in direct conflict with CIRIS categorical `DECEPTION_FRAUD`. Disposition is "Federation-level categorical posture stays; specialization-layer at CIRISMedical#1" but no code lives in the main repo to do that specialization. Search/rescue and elder/child-care use cases requiring this nuance are not addressable in CIRIS Agent today.
- **No automated `prohibited:disinformation_at_scale` detector** — ASEAN's wire form references aggregate disinformation. Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.1.4` as the `prohibited:{capability}` apophatic prefix family (never-positive per §4.4) PLUS the F-3 axis `detection:correlated_action:ecology_of_communication:coordinated_messaging_pattern` (FSD-002 §3.5.3 v1.3 axis-vocabulary addition) — the aggregate-disinformation shape decomposes onto the population-scale correlated-action detector. CIRIS detects per-thought attempts via prohibition gate; aggregate-pattern detection lands LensCore-side per `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7` phasing.
- **No `prohibited:deceptive_default_options` linter** — Substrate-specced as `prohibited:{capability}` (FSD-002 §3.1.4) — apophatic prefix, never-positive (§4.4) admits any capability label including `deceptive_default_options`. Agent-side adapter-manifest audit is the consumer-policy enforcement of the substrate prohibition. CIRIS has the prohibition vocabulary at the bus; the manifest-linter is agent-side composition, not substrate-blocked.
- **Accord invocation auth assumes WA cert availability** — the kill switch presumes an active WA certificate in the registry. There is no out-of-band/offline lockdown path (intentional: the design rejects out-of-band overrides).
- **Localized prohibition policy text** — prohibitions code is English-only; the localized Accord copies (29 languages) carry the policy framing but not the canonical capability list. Localization parity is partial.

Proposed pointer (from seed): `CIRISAgent/logic/prohibitions.py` (actual location: `ciris_engine/logic/buses/prohibitions.py`)
<!-- END HUMAN -->
