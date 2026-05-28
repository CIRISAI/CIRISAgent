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
## What this dimension covers

When CIRIS makes a decision, it has to ask "whose flourishing is at stake?" — and the answer is rarely just one person. A decision can affect the individual, their family, their community, the wider network of groups they belong to, the species, and (eventually) the planet. This dimension keeps every one of those scales in view at the same time. Sixty attestations across the four regulatory batches (Magnifica Humanitas, EU, IEEE, ASEAN) treat this as a shared concern, not a CIRIS invention.

## How CIRIS implements this today

CIRIS tracks "whose flourishing is in play" through three layers that work together: a memory scope tag on every stored thought, an explicit stakeholder list written into every reasoning step, and a recursive ethical lens that asks the same question at every scale (the Recursive Golden Rule — a fractal application of the same ethical structure at self, community, and ecosystem levels).

**Memory scope: the "who does this belong to" tag.** Every memory the agent writes carries a scope label so downstream readers know whose context it sits in.
- The scope values are defined at `ciris_engine/schemas/services/graph_core.py:39`: `GraphScope = {LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY}`.
- Writes at community scope go through consent and audit checks — see `ciris_engine/logic/services/governance/consent/service.py:562` (conversation summaries) and `:764` (anonymous community summaries).
- Some config types are pinned to the IDENTITY scope and require a Wise Authority (a human or panel the agent escalates to) to change — mapping at `ciris_engine/schemas/services/graph_core.py:96-105` covers ethical boundaries, capability limits, trust parameters, and behavior config.

**Stakeholder enumeration: every decision names who is affected.** Before the agent picks an action, it has to list the parties affected by it (stakeholder enumeration — listing every party affected by a decision).
- The requirement lives in the ethical-decision prompt at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:27,40,68,107`.
- The four user-visible scale values are exposed to the operator in the action-selection prompt at `ciris_engine/logic/dma/prompts/action_selection_pdma.yml:29`, mirrored across all 29 languages — e.g. `ciris_engine/logic/dma/prompts/localized/{es,fr,bn,ta}/action_selection_pdma.yml:29`.
- A common-sense check at `ciris_engine/logic/dma/prompts/csdma_common_sense.yml:36` asks whether the named stakeholders are real people in the real world, not fictionalized.

**Species-scale anchor: M-1.** The Accord's Meta-Goal M-1 — "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" — is the species-scale anchor. It is referenced from the Wise Authority documentation at `ciris_engine/logic/services/governance/wise_authority/README.md:11` and the canonical Accord text at `ciris_engine/data/accord_1.2b.txt:725`.

**Recursive Golden Rule: the same question at every scale.** `MISSION.md:70-77` ("Same shape, different scale… all the way up and all the way down") tells the agent to reason about self, next-agent, user, and community simultaneously, with the same ethical structure at each level. The per-thought ethical prompt carries this discipline at `ciris_engine/logic/dma/prompts/pdma_ethical.yml:68`.

**Tests covering this behaviour:**
- Scope correctness: `tests/ciris_engine/logic/services/graph/test_filter_config_bug.py`
- Memory filter scope handling: `tests/ciris_engine/logic/adapters/api/routes/test_memory_filters.py`
- Scoped consent and Wise Authority approval: `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`
- Stakeholder enumeration is exercised implicitly in every ethical-decision evaluator test.

Proposed pointer (from seed): no per-dimension pointer specified; agent-side implementation lives in `GraphScope` + Recursive Golden Rule + stakeholder enumeration.

## How you can tell it's working (observability)

If you want to verify this dimension is alive in production, here's where to look.

- **The reasoning stream itself.** When live-lens tracing is on, every reasoning step ships to `/tmp/qa-runner-lens-traces-<ts>/accord-batch-*.json` with the stakeholder list embedded — see `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)".
- **The signed audit chain.** Every memory write records its scope, signed by `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`). Downstream verifiers get a tamper-evident record of which scale the agent operated at.
- **Scope-distribution telemetry.** `ciris_engine/logic/services/graph/telemetry_service/` exposes the per-event scope tag so the distribution across scales can be computed for any agent.
- **Upstream pattern detection.** The structural-pattern detector family (`detection:correlated_action:*` in the seed) catches things like "this agent only ever operates at one scale." That detector lives in the upstream CIRISLens layer; the Coherence Ratchet (`MISSION.md:518-535`) reads conscience-scalar drift per scope.
- **Federation citation by ID.** Once the federation envelope includes `evidence_refs.dimensions = ["D06"]`, the scope-tagged memory events become the structural-evidence basis for this dimension's claims. The data is already emitted; the wire-side citation wrapper lands with the upstream substrate work.

## Current limitations & next steps

Most of the remaining work here is shared with the upstream CIRIS substrate (the upstream CIRIS components being progressively replaced with Rust-native implementations — Persist → Edge → LensCore → NodeCore). Where the agent already emits the right data, the remaining step is just citing it by ID once the federation envelope is in place.

- **Planet scale is composed, not yet named directly.** The federation surface (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.2`) defines `goal:planet` as one of six scale values. Today the agent expresses planet-scale concerns through the combination of species scope and ENVIRONMENT scope; once the NodeCore Goal Primitive ships (`CIRISNodeCore/FSD/GOAL_PRIMITIVE.md §2.1`) the agent will emit `goal:planet` directly. Shared roadmap with NodeCore.
- **Citation by ID on the federation wire is post-2.9.4 work.** Per-thought reasoning carries the full stakeholder enumeration in its rationale text. Adding `evidence_refs.dimensions = ["D06"]` to the federation envelope (messages exchanged with peer CIRIS agents in the federation network) is downstream work in CIRISLens's accord-metrics adapter and CIRISPersist's contribution schema — same "trace vs. wire" boundary noted for D11 and D13.
- **Self-monitoring of scope distribution.** The agent does not yet flag its own scope-distribution skew (e.g. "I have been operating at LOCAL scope all day"). The structural-pattern detector in CIRISLens is the off-agent backstop today; on-agent self-monitoring is a complementary next step.
- **Affiliations scale rides on operator metadata.** Jurisdictional belonging ("EU agent," "ASEAN agent") is carried in the operator's CIRISRegistry license rather than in a memory scope. Once the Registry license model exposes `goal:affiliations:{jurisdiction}` directly to the agent, this becomes a first-class runtime primitive.
- **Family scope sits inside LOCAL today.** Magnifica Humanitas §§148-156 names the family / household / kin scale explicitly. The agent currently composes it as a subset of LOCAL or COMMUNITY; an intermediate family-scope primitive is a future refinement.

Proposed pointer (from seed): `(none specified in seed; please fill)` — observability gap is CIRISLens-side, not agent-side.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
