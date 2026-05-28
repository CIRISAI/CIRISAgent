# D06 — `goal:*` (STRONG-4)

> Multi-scale belonging composite — self/family/community/affiliations/species/planet

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D06` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: beneficence
**Attestation density**: MH=34 · EU=6 · IEEE=13 · ASEAN=7 · total=60

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§148-156*
    > "labor as integral to belonging at family/community/affiliations/species scales"
    Wire form: `goal:family + goal:community + goal:affiliations + goal:species`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§A*
    > "Trustworthy AI for Europe"
    Wire form: `goal:affiliations (EU-jurisdiction scope)`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 §0.a*
    > "well-being of all humans as the species-scale aim of A/IS"
    Wire form: `goal:species`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§A (6 ASEAN attestations of goal:affiliations)*
    > "regional ecosystem belonging; cross-jurisdictional cooperation"
    Wire form: `goal:affiliations (ASEAN-jurisdiction)`

## Wire primitives

- `goal:{scale}`

## Convergence note

Every available {scale} value is exercised somewhere in the corpus. NB: `goal:planet` is a REINFORCED v1.5+ T-3 candidate (MH + IEEE Ch4 + IEEE Ch8).

## v1.5+ T-3 candidates affecting this dimension

- **T3-06** `goal:planet` (priority MEDIUM_HIGH, source(s): magnifica_humanitas_v1, ieee_ead_v1)

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`goal:*` is a multi-scale belonging composite; CIRISAgent operationalizes the {scale} slot through three layered primitives:

1. The `GraphScope` enum stratifies stored memory by who-it-belongs-to (the cohort of belonging).
2. The Recursive Golden Rule requires the agent to apply the same ethical shape at every scale simultaneously (the fractal enforcement).
3. The PDMA / CSDMA stakeholder identification step names whose flourishing is in scope for a given thought (the per-thought read-out of goal:{scale}).

**Multi-scale memory primitive (the {scale} enum on the agent side)**
- `ciris_engine/schemas/services/graph_core.py:39` defines `GraphScope = {LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY}`.
- Every memorize / recall / forget action carries a scope; community-scope writes are gated through the consent and audit chains.
- Worked example of COMMUNITY-scope writes: `ciris_engine/logic/services/governance/consent/service.py:562` (consent stream conversation summaries scoped to community) and `:764` (anonymous-stream community summaries).
- Config-type → scope mapping at `ciris_engine/schemas/services/graph_core.py:96-105`: filter_config / channel_config / response_templates are LOCAL; behavior_config / ethical_boundaries / capability_limits / trust_parameters are IDENTITY (requiring WA approval to mutate).

**MEMORIZE action surface (operator visibility)**
- `ciris_engine/logic/dma/prompts/action_selection_pdma.yml:29` enumerates the four user-visible scales (`local|identity|environment|community`) in every locale's localized ASPDMA prompt.
- Localized variants verified at e.g. `ciris_engine/logic/dma/prompts/localized/{es,fr,bn,ta}/action_selection_pdma.yml:29`.

**Species-scale orientation (the M-1 anchor)**
- `ACCORD.md` Meta-Goal M-1 ("Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing") is the species-scale species (in the original sense — a category of being) anchor.
- Referenced from `ciris_engine/logic/services/governance/wise_authority/README.md:11` and `ciris_engine/data/accord_1.2b.txt:725` ("species-specific welfare minima throughout the creation's lifecycle").
- Species is the outermost cohort the wire format admits today; planet is a v1.5+ candidate (T3-06).

**Recursive Golden Rule (the fractal enforcement)**
- `MISSION.md:70-77` ("Same shape, different scale… all the way up and all the way down") is the policy text that requires agents to reason at self / next-agent / user / community simultaneously.
- PDMA template carries this into the per-thought prompt at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:68` ("names the subject being evaluated and the key stakeholders").
- Per user-memory `project_recursive_golden_rule`: "fractal, not symmetric — same structure at every scale (Self/Originator/Ecosystem self-similar); literal recursive-modelling with Mandelbrot-style termination; hollow-center prohibition."

**Stakeholder identification step (PDMA Step 1)**
- `ciris_engine/logic/dma/prompts/pdma_ethical.yml:27,40,68,107` requires the agent to enumerate stakeholders and conflicts between their interests before action selection.
- This is the goal:* slot read-out at thought time: every PDMA result names the cohorts of belonging implicated by the response.
- CSDMA realism check at `ciris_engine/logic/dma/prompts/csdma_common_sense.yml:36` validates that the enumerated stakeholders are world-admitting (real, not fictionalized).

**Test coverage**
- Scope correctness exercised in `tests/ciris_engine/logic/services/graph/test_filter_config_bug.py`.
- Memory filter scope handling in `tests/ciris_engine/logic/adapters/api/routes/test_memory_filters.py`.
- Scoped consent / WA approval surface in `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`.
- Cohort-of-belonging implicitly exercised in every PDMA / ASPDMA evaluator test via the stakeholder enumeration block.

Proposed pointer (from seed): no per-dimension pointer specified; agent-side implementation lives in `GraphScope` + Recursive Golden Rule + PDMA Step 1.

## Observability hooks

- **Per-thought trace emission** — every PDMA / ASPDMA result carries the stakeholder enumeration in its rationale field, shipped to lens via the local-tee at `/tmp/qa-runner-lens-traces-<ts>/accord-batch-*.json` when `--live-lens` is on (see `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)"). Each event has the agent's at-call goal:{scale} read-out embedded in the PDMA stakeholders block.
- **Audit chain** — `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) signs every MEMORIZE / RECALL / FORGET event with the scope value, giving downstream verifiers a tamper-evident record of which {scale} the agent operated at.
- **MEMORIZE / RECALL scope-distribution telemetry** — `ciris_engine/logic/services/graph/telemetry_service/` records per-event scope alongside the standard service metrics; aggregate scope distribution per agent is computable from this stream.
- **LensCore detector adjacency** — D05 detection family (`detection:correlated_action:*` per seed) is the upstream consumer; same-scale-only deferral patterns and aggregate cohort-skew are flagged by the F-3 family. CIRISLens's Coherence Ratchet (`MISSION.md:518-535`) reads the conscience-scalar drift per scope.
- **Federation evidence_refs** — once `evidence_refs.dimensions = ["D06"]` lands on the Contribution envelope, GraphScope-tagged memorize/recall events become the per-thought structural-evidence basis for D06 attestations. Today the agent emits the data in audit + trace streams; the wrapper to cite D06 by id is the seed v1.0 binding pending downstream substrate work.

## Known gaps / not-yet-implemented

- **`goal:planet` is not yet a first-class scale value agent-side.** Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2` as `goal:{scale}` with `{scale}` ∈ `self` | `family` | `community` | `affiliations` | `species` | `planet` (v1.4 cross-source-reinforced addition — biosphere as belonging-scale per MH environmental concern + IEEE EAD Ch4 §1.3.a + IEEE EAD Ch8 sustainable-development); scored by 𝒞_CIRIS. Per FSD-002 §3.10 namespace-summary v1.4 entry — "`goal:planet` added to `goal:{scale}` enum per §3.6.2 — cross-source-reinforced HIGH-priority from CIRISRegistry#20, NOT a new prefix family, just a new value within existing prefix." Agent will emit at trace-emit time by mapping the federation `goal:planet` value onto its existing scope discipline once the NodeCore Goal Primitive lands (`CIRISNodeCore/FSD/GOAL_PRIMITIVE.md §2.1`); today the implicit composition is through species + ENVIRONMENT scope. **Substrate-specced, agent-side mapping pending.**
- **No federation-wire emission of D06 by id yet.** Per-thought DMA outputs carry the stakeholder enumeration in rationale text, but the wire envelope does not yet include `evidence_refs.dimensions = ["D06"]`. This is the same "trace ≠ wire contribution" boundary noted in user-memory `feedback_trace_vs_wire_contributions` — agent emits structurally-rich PDMA results; mapping those to D06 by id is downstream substrate work (CIRISLens accord_metrics adapter, CIRISPersist federation contribution schema). Trace-side work is in scope today; wire-side is post-2.9.4.
- **No automated calibration that goal:* is exercised across all scales in production.** A run could spend an entire day operating only at LOCAL scope and still pass; only RATCHET-style aggregate detection (which is in CIRISLens, not the agent) would catch the omission. The agent does not self-monitor scope-distribution skew.
- **Affiliations scale has no agent-side primitive.** Federation jurisdictional belonging ("EU agent," "ASEAN agent") is a CIRISRegistry license attribute, not a memory scope. Until the Registry license model exposes `goal:affiliations:{jurisdiction}` to the agent, affiliations is structurally implicit at deploy-config level.
- **Family-scale is conflated with LOCAL.** MH's `goal:family` (per seed regulatory_attestations) has no distinct agent-side primitive; family-scope memories memorize at LOCAL or COMMUNITY scope today, lacking the intermediate household / kin cohort that MH §§148-156 names. Compositional closure works today but is structurally compressed.

Proposed pointer (from seed): `(none specified in seed; please fill)` — observability gap is CIRISLens-side, not agent-side.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
