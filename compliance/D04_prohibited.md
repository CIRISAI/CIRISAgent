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
## What this dimension covers

CIRIS has a list of things it will never do — regardless of who asks, what the context is, or what an emergency claim might justify. This is the **constitutional floor** (actions CIRIS will never take, regardless of who asks): a hard "no" that cannot be moved by memory, learning, runtime configuration, or operator override. All four traditions we track (104 attestations, including the strongest single structural-evidence claim in the matrix — the verbatim four-source LAWS prohibition) name categorical prohibitions of this kind; CIRIS unifies them in one code-level list.

## How CIRIS implements this today

The list lives in one file as plain Python constants. The central decision-routing layer (the WiseBus, where actions flow through governance review) checks every requested capability against the list before it can run. There are no override paths, no emergency exceptions, and by design no runtime mutation.

- The prohibited-capabilities list is the single source of truth: `ciris_engine/logic/buses/prohibitions.py:1057-1083`. Every category is enumerated; changing the list requires a code commit and review.
- The architectural promise — "No Kings, no overrides, ethics must not be plastic or learnable" — is stated in the file's own docstring at `ciris_engine/logic/buses/prohibitions.py:9-19`. Severity levels (`NEVER_ALLOWED`, `REQUIRES_SEPARATE_MODULE`, `TIER_RESTRICTED`) at `:30-35`.
- The hard "never" categories include weapons including lethal-autonomous systems (`:522`, with `lethal_autonomous` at `:572` — the four-source corroborated LAWS prohibition), manipulation and coercion (`:607`), mass surveillance (`:680`), deception and fraud (`:697`), offensive cyber (`:768`), election interference (`:856`), biometric inference (`:874`), autonomous deception (`:891`), hazardous materials (`:908`), and discrimination (`:978`).
- A second class — "requires a separate licensed module" — gates legitimate uses to specialized repositories with appropriate review: medical (`:41`, gated to the private CIRISMedical repository for liability isolation), financial (`:179`), legal (`:258`), spiritual direction (`:332`), home security (`:443`), identity verification (`:458`), content moderation (`:475`), research (`:486`), and infrastructure control (`:502`).
- The central decision-routing layer is the chokepoint. `ciris_engine/logic/buses/wise_bus.py:28,51` imports and re-exports the list; `:772-773,830` performs per-capability checks and emits per-category telemetry counters. Category detection is regex word-boundary matching at `ciris_engine/logic/buses/prohibitions.py:1180-1240` (e.g. "domain:medical" matches MEDICAL) with patterns compiled at `:1129-1152`.
- A signed kill switch flips every category to ALL when triggered. `ciris_engine/logic/buses/wise_bus.py:321-419` validates an Ed25519-signed Wise Authority (a human or panel the agent defers to) payload — ROOT or AUTHORITY role required — and triggers full prohibition lockdown. Operator tooling lives at `tools/security/accord_invoke.py`; design rationale at `FSD/ACCORD_INVOCATION_SYSTEM.md`; the kill-switch criterion text at `ciris_engine/data/localized/accord_1.2b_en.txt:380` ("Evidence of weaponization against vulnerable populations" — cross-references D03).
- Policy text: `ACCORD.md` at the repo root is the public Accord; the canonical Six Principles sit at `ciris_engine/data/localized/accord_1.2b_en.txt:106-111` (non-maleficence is the principle the floor maps to).
- Test coverage is thorough: `tests/test_prohibition_system.py:24-44` (category detection), `:71-83` (severity), `:205-244` (invariants — every category has a severity, no overlaps, telemetry includes counts), `:112-188` (bus-level enforcement including tier restriction).

## How you can tell it's working (observability)

Every rejection leaves a structured trace; every kill-switch invocation surfaces as a security alert.

- Every prohibited-capability rejection routes through the audit graph via `AuditService.log_event` in `ciris_engine/logic/services/graph/audit_service/service.py`. Auditors query for events tagged with the rejected category.
- Per-category rejection counters land in the telemetry stream at `ciris_engine/logic/buses/wise_bus.py:830`.
- Kill-switch (Accord invocation) events emit `SECURITY ALERT` log lines (`wise_bus.py:343, 363, 372, 398-401`) into `/app/logs/incidents_latest.log` per the production debugging discipline.
- For federation reporting, Contributions tag `dimensions: ["D04"]` on every categorical rejection, co-tagging `D01` when an internal safety check also fired and `D03` when the rejection hit the discrimination category.

## Current limitations & next steps

- Prohibitions match capability *names*, not arbitrary content inside tool arguments — `ciris_engine/logic/buses/prohibitions.py:16-19` documents this as a first-line defense. Harmful content smuggled into otherwise-allowed capability arguments is caught (if at all) by the internal safety checks, adapter-side hygiene, or post-hoc human review. A structural content classifier on tool arguments is a next step.
- The cross-source conflict CONF-01 (IEEE Ch5 §3.4 permits licensure-gated beneficiary-deception in search/rescue and elder/child-care; CIRIS holds categorical) is resolved by keeping the categorical posture in the main repo and handling the specialization at `CIRISMedical#1`. The search/rescue nuance is not addressable in the main CIRIS Agent today.
- An automated detector for `prohibited:disinformation_at_scale` (ASEAN's aggregate-disinformation shape) is shared work with the upstream CIRIS substrate. The substrate spec (FSD-002 §3.1.4 as the apophatic prefix family + §3.5.3's `ecology_of_communication:coordinated_messaging_pattern` axis) decomposes the aggregate shape onto a population-scale structural-pattern detector; agent-side per-thought detection is already in place. LensCore implementation tracks at `CIRISLensCore/FSD/LENS_CORE_V0_5.md §4.7`.
- An adapter-manifest dark-pattern linter for `prohibited:deceptive_default_options` is coming next (tracked at `CIRISAgent#818`, 2.9.7). The prohibition vocabulary exists at the central decision-routing layer; the manifest linter is the agent-side enforcement.
- The kill switch presumes an active Wise Authority certificate in the registry. There is no out-of-band offline path — this is intentional: the design rejects out-of-band overrides.
- Prohibition policy is fully localized in 29 languages in the Accord copies, but the canonical capability list itself is English-only. Localization parity is in progress.

Proposed pointer (from seed): `CIRISAgent/logic/prohibitions.py` (actual location: `ciris_engine/logic/buses/prohibitions.py`)

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3
- **2.9.7**: `CIRISAgent#818` — adapter-manifest dark-pattern linter

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
