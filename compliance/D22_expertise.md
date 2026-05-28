# D22 — `expertise:*` (STRONG-3)

> Declared competence in domain (named-expert attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D22` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=1 · EU=1 · IEEE=10 · ASEAN=0 · total=12

**Absent from**: ASEAN — ASEAN frames competence at the organizational-governance level, not the named-expert level.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various*
    > "discernment expertise (sensus fidelium adjacent)"
    Wire form: `expertise:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "domain expertise required for trustworthy deployment"
    Wire form: `expertise:domain`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7-Ch11 (10 attestations)*
    > "engineering, ethics, law, policy expertise; interdisciplinary expertise composition"
    Wire form: `expertise:{domain}`

## Wire primitives

- `expertise:{domain}`

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`expertise:*` (named-expert attestation) is the dimension where CIRIS has the most structural gaps. CIRIS does not currently declare named-expert competence in machine-readable wire form. The functional analogue is the Wise Authority (WA) system + Domain Category routing: when a thought touches a domain where expertise is required (medical, financial, legal, etc.), the agent DEFERs to a human WA. Expertise is *outsourced* rather than *attested*.

- **Code references** — Wise Authority (the expertise-routing primary surface):
    - `ciris_engine/logic/services/governance/wise_authority/service.py:42` — `WiseAuthorityService`
    - `ciris_engine/protocols/services/governance/wise_authority.py:24` — `WiseAuthorityServiceProtocol`
    - `ciris_engine/protocols/services/governance/wise_authority.py:38` — `get_guidance(request: GuidanceRequest)` — the named-expert query surface
    - `ciris_engine/protocols/services/governance/wise_authority.py:73` — `fetch_guidance(context: GuidanceContext)` — WiseBus-compatible variant
    - `ciris_engine/logic/services/governance/wise_authority/service.py:378` — `send_deferral(deferral: DeferralRequest)`
    - `ciris_engine/logic/services/governance/wise_authority/service.py:530` — `resolve_deferral(deferral_id, response: DeferralResponse)` — the WA's expert ruling
- **Code references** — domain-routing (expertise:domain via deferral taxonomy):
    - `ciris_engine/schemas/services/agent_credits.py:38` — `DomainCategory` enum (MEDICAL, FINANCIAL, LEGAL, HOME_SECURITY, IDENTITY_VERIFICATION, CONTENT_MODERATION, RESEARCH, INFRASTRUCTURE_CONTROL, etc.)
    - `ciris_engine/schemas/services/deferral_taxonomy.py:19` — `DeferralNeedCategory` (HEALTH_AND_BODILY_INTEGRITY, LIVELIHOOD_AND_FINANCIAL_SECURITY, JUSTICE_AND_LEGAL_AGENCY, etc.)
    - `ciris_engine/schemas/services/deferral_taxonomy.py:33` — `DeferralOperationalReason`
    - `ciris_engine/schemas/services/deferral_taxonomy.py:245-254` — `DOMAIN_TO_NEED_CATEGORY` mapping (machine-readable expertise routing)
    - `ciris_engine/schemas/services/deferral_taxonomy.py:317` — `get_rights_basis_for_need_category()` — UDHR-grounded rights basis tied to each expertise domain
    - `ciris_engine/logic/dma/dsaspdma.py:27` — domain-specialized ASPDMA imports `DomainCategory` and routes accordingly
- **Code references** — Wise Bus broadcast (multiple expertise sources):
    - `ciris_engine/logic/buses/wise_bus.py` — broadcasts to multiple WiseAuthorityService providers; aggregates expert opinions
    - `ciris_engine/logic/buses/prohibitions.py` — categorical prohibitions; the negative-space attestation of where CIRIS asserts non-expertise
- **Code references** — DEFER handler (the expertise-routing trigger):
    - `ciris_engine/logic/handlers/control/defer_handler.py` — sends to WA
    - `ciris_engine/logic/handlers/control/defer_handler.py:1-30` — `DeferParams`, `DeferralContext` imports
- **Code references** — Commons Credits (the proxy for domain-expertise reputation):
    - `ciris_engine/schemas/services/agent_credits.py:226` — `CreditGenerationPolicy`
    - `ciris_engine/schemas/services/agent_credits.py:180` — `AgentCreditSummary` carries domain-category breakdown
- **Policy text**:
    - `CLAUDE.md` — "Medical Domain Prohibition" — explicit non-expertise declaration; medical/health/financial/legal are blocked at bus level
    - `MISSION.md:36-66` — apophatic bounds; the agent declares which domains it lacks expertise in
    - `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:572` — explicit non-capability list (medical/health/financial/legal/spiritual-direction)
- **Test coverage**:
    - `tests/test_agent_credits.py`
    - WiseAuthority service tests under `tests/`
- **Configuration surface**:
    - `WiseBus` provider registration — declares which WA providers (Discord WA channel, API WA endpoint, etc.) the agent will consult

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Observability hooks

- **Deferral audit trail**: every DEFER emits an audit entry (action_type = "handler_action_defer") visible via `GET /v1/audit/search` — the chronological record of "where the agent acknowledged it lacked expertise."
- **WA response logging**: `resolve_deferral` writes the expert's ruling to the audit chain.
- **Domain-routing telemetry**: `dsaspdma.py` DomainCategory selections are observable per-thought.
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D22"]` resolves through this seed to MH discernment-expertise, EU §III.7 domain-expertise requirement, IEEE Ch7-Ch11 interdisciplinary-expertise composition.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **No `expertise:{domain}` wire-form emission**: substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.1` as `expertise:{domain}:{language}` (NodeCore §2 P3; §4.5 `ExpertiseLedger`); positive-only, broader granularity than credits. Emitted as a `Declaration` via `expertise_attestation` Contribution kind (`CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.10` — bilateral, open / jump-threshold witness-gated). CIRIS today inverts the IEEE pattern (agent defers rather than attests); future agent emission lands once NodeCore P3 ExpertiseLedger ships and the agent runs the `expertise_attestation` declaration flow on its self-known competence domains.
- **No interdisciplinary-expertise composition attestation**: composes via FSD-002 §6 composition policies (§6.1.2 one-hop transitive, §6.1.3 weighted-graph EigenTrust-style) over multiple `expertise:{domain}:{language}` attestations; the "panel composition" surface emerges from the witness-set discipline `witness_diversity:{contribution_id}` (FSD-002 §3.6.3 NodeCore P10 — meets jurisdictional + organizational + software-stack + cell-expertise bars). Agent emits per-WA-response data; composition runs substrate-side.
- **No expertise:agent_self_capability declaration**: substrate-specced as the bilateral `expertise_attestation` Contribution kind (MESSAGE_TAXONOMY.md §4.10 Declaration / Bilateral / Open with jump-threshold witness-gating). Agent emits once the federation-wire emission lands; today the Identity Template (Scout / Ally / Sage) is the human-readable analogue. The §4.13 `registry_vouch` Contribution is the inverse — third-party vouching of expertise.
- **ASEAN absent_batch**: ASEAN frames competence at organizational-governance level rather than named-expert level — CIRIS sits closer to ASEAN's pattern than to IEEE's. Organizational governance composes via `partner_role:{role}` (FSD-002 §3.9) rather than `expertise:{domain}:{language}`.
- **Sensus-fidelium analogue (MH)**: closest substrate primitive is multi-witness `witness_diversity:{contribution_id}` with the cell-expertise bar (FSD-002 §3.6.3 NodeCore P10) — sensus fidelium = "the cell whose constitution carries the question collectively attests." Spiritual / communal dimension preserved by the relational-anthropology commitment (FSD-002 §1.10 Ubuntu primary) but not lifted to a per-claim primitive.
- **`expertise:*` is already in the wire** — promoted in FSD-002 §3.6.1 as `expertise:{domain}:{language}` with the existing `expertise_attestation` Contribution kind for declaration. Agent's structurally-embedded DEFER + DomainCategory routing is the inverse surface (lack-of-expertise) rather than absence of the prefix itself.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the externally-measurable expertise domains in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 services across 6 categories** — each category represents a declared competence domain (graph, infrastructure, lifecycle, governance, runtime, tool)
- **256 API routes** — the externally-bounded expertise surface

These figures are deliberately conservative — the baseline measures *implemented competence*, not claimed competence. Per the D22 inversion noted above, CIRIS does not declare expertise in any domain; instead it declares deferral surfaces where the named DomainCategory routes to a WA. The baseline route count is therefore a ceiling on what CIRIS could attest expertise over, not an attestation itself.

## Tracked requirements

- **Umbrella(s)**: `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
