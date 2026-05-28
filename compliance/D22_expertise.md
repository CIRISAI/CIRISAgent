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
## What this dimension covers

Expertise asks: what does the agent claim to be competent in, and what does it decline? An auditor wants to know that the agent has a clear, machine-readable answer to "do you know what you don't know?"

## How CIRIS implements this today

CIRIS takes a different approach to expertise than IEEE's named-expert framing: instead of declaring expertise in specific domains, CIRIS declares the domains it will *not* act in on its own — and routes any thought that touches one of those domains to a Wise Authority (a human or panel the agent defers to). This is the same goal achieved by a different structure: an auditor can read off the agent's competence boundary by inspecting (1) the categorical prohibition list, (2) the domain taxonomy (medical, financial, legal, etc.), and (3) the deferral trail in the audit chain.

**Wise Authority service (the deferral-routing surface).**
- `ciris_engine/logic/services/governance/wise_authority/service.py:42` — `WiseAuthorityService`
- `ciris_engine/protocols/services/governance/wise_authority.py:24` — `WiseAuthorityServiceProtocol`
- `ciris_engine/protocols/services/governance/wise_authority.py:38` — `get_guidance(request: GuidanceRequest)` — the query surface
- `ciris_engine/protocols/services/governance/wise_authority.py:73` — `fetch_guidance(context: GuidanceContext)` — the WiseBus-compatible variant
- `ciris_engine/logic/services/governance/wise_authority/service.py:378` — `send_deferral(deferral: DeferralRequest)`
- `ciris_engine/logic/services/governance/wise_authority/service.py:530` — `resolve_deferral(deferral_id, response: DeferralResponse)` — the Wise Authority's ruling

**Domain routing (the machine-readable expertise boundary).** The domain taxonomy (medical, financial, legal, etc.) plus its rights basis is enumerated in code.
- `ciris_engine/schemas/services/agent_credits.py:38` — `DomainCategory` enum (MEDICAL, FINANCIAL, LEGAL, HOME_SECURITY, IDENTITY_VERIFICATION, CONTENT_MODERATION, RESEARCH, INFRASTRUCTURE_CONTROL, etc.)
- `ciris_engine/schemas/services/deferral_taxonomy.py:19` — `DeferralNeedCategory` (HEALTH_AND_BODILY_INTEGRITY, LIVELIHOOD_AND_FINANCIAL_SECURITY, JUSTICE_AND_LEGAL_AGENCY, etc.)
- `ciris_engine/schemas/services/deferral_taxonomy.py:33` — `DeferralOperationalReason`
- `ciris_engine/schemas/services/deferral_taxonomy.py:245-254` — `DOMAIN_TO_NEED_CATEGORY` mapping (the machine-readable routing table)
- `ciris_engine/schemas/services/deferral_taxonomy.py:317` — `get_rights_basis_for_need_category()` — the UDHR-grounded rights basis tied to each domain
- `ciris_engine/logic/dma/dsaspdma.py:27` — the domain-specialized action selection imports `DomainCategory` and routes accordingly

**WiseBus broadcast (multiple expertise sources).** The central decision-routing layer (the WiseBus) can fan out a query to multiple registered Wise Authority providers and aggregate the responses.
- `ciris_engine/logic/buses/wise_bus.py` — broadcast and aggregation
- `ciris_engine/logic/buses/prohibitions.py` — categorical prohibitions: the explicit declaration of where CIRIS asserts it lacks expertise

**DEFER handler (the routing trigger).**
- `ciris_engine/logic/handlers/control/defer_handler.py` — sends to Wise Authority
- `ciris_engine/logic/handlers/control/defer_handler.py:1-30` — `DeferParams`, `DeferralContext`

**Commons Credits (the reputation proxy for domain experience).** Credit records (CommonsCredits — non-monetary recognition of substrate-building work) carry a domain breakdown.
- `ciris_engine/schemas/services/agent_credits.py:226` — `CreditGenerationPolicy`
- `ciris_engine/schemas/services/agent_credits.py:180` — `AgentCreditSummary` (per-domain breakdown)

**Policy text.**
- `CLAUDE.md` — "Medical Domain Prohibition" — explicit non-expertise declaration; medical / health / financial / legal are blocked at the bus boundary
- `MISSION.md:36-66` — apophatic bounds: the agent declares which domains it does not operate in
- `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE.txt:572` — explicit non-capability list (medical / health / financial / legal / spiritual direction)

**Tests.**
- `tests/test_agent_credits.py`
- WiseAuthority service tests under `tests/`

**Configuration.**
- WiseBus provider registration — declares which Wise Authority providers (Discord channel, API endpoint, etc.) the agent will consult

Proposed pointer (from seed): `(none specified in seed; please fill)`

## How you can tell it's working (observability)

If you wanted to verify this from outside, every deferral produces an audit entry naming the domain and reason, every Wise Authority ruling is written back to the audit chain, and the per-thought domain selection is observable in telemetry.

- **Deferral audit trail**: every DEFER (escalate to a Wise Authority) emits an audit entry (action type `handler_action_defer`) visible via `GET /v1/audit/search`. This is the chronological record of where the agent acknowledged it had reached its competence boundary.
- **Wise Authority response logging**: `resolve_deferral` writes the Wise Authority's ruling to the audit chain.
- **Domain-routing telemetry**: the domain selections made by `dsaspdma.py` are observable per thought.
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D22"]` resolves through this seed to MH discernment expertise, EU §III.7 domain-expertise requirement, IEEE Ch7-Ch11 interdisciplinary-expertise composition.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **Typed `expertise:{domain}` federation envelope**: currently implemented via the escalation path (CIRIS declares non-expertise and routes to a Wise Authority); the explicit declaration form will be added when the federation primitive ships. Shared work with the upstream substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.1 expertise:{domain}:{language}`, `CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.10 expertise_attestation`). When NodeCore P3 ExpertiseLedger ships, the agent will run the declaration flow on its self-known competence domains.
- **Interdisciplinary-expertise composition**: shared work with the upstream substrate (FSD-002 §6 composition policies, §3.6.3 `witness_diversity` NodeCore P10 — meets jurisdictional, organizational, software-stack, and cell-expertise bars). The agent emits per-Wise-Authority-response data; the composition layer runs substrate-side.
- **`expertise:agent_self_capability` declaration**: shared work with the upstream substrate (`MESSAGE_TAXONOMY.md §4.10` bilateral `expertise_attestation`). Today the Identity Template (Scout / Ally / Sage) is the human-readable analogue; the typed envelope lands once the federation primitive ships. (The inverse — third-party vouching for the agent's expertise — uses `registry_vouch` from §4.13.)
- **ASEAN frames competence at the organizational level** rather than the named-expert level — CIRIS sits closer to ASEAN's framing than IEEE's. Organizational governance composes via the upstream `partner_role:{role}` primitive (FSD-002 §3.9) rather than via `expertise:*`.
- **MH "sensus fidelium" analogue** (community discernment): closest upstream primitive is multi-witness `witness_diversity:{contribution_id}` with the cell-expertise bar (FSD-002 §3.6.3 NodeCore P10) — "the cell whose constitution carries the question collectively attests." The relational-anthropology commitment (FSD-002 §1.10 Ubuntu primary) preserves the spiritual / communal dimension at the policy level; a per-claim primitive is a possible next step.
- **`expertise:*` is already declared in the federation wire** (FSD-002 §3.6.1). The agent's current DEFER + DomainCategory routing is the inverse surface (the boundary of non-expertise); the explicit attestation surface lands when the agent runs the declaration flow.

## Quantitative baseline

Per [MEASUREMENT_METHODOLOGY.md](MEASUREMENT_METHODOLOGY.md), the externally-measurable expertise domains in the current baseline ([`baselines/2026-05-28.md`](baselines/2026-05-28.md)):

- **22 services across 6 categories** — each category represents a declared competence domain (graph, infrastructure, lifecycle, governance, runtime, tool)
- **256 API routes** — the externally-bounded expertise surface

These figures are deliberately conservative — the baseline measures *implemented competence*, not claimed competence. Per the D22 inversion noted above, CIRIS does not declare expertise in any domain; instead it declares deferral surfaces where the named DomainCategory routes to a WA. The baseline route count is therefore a ceiling on what CIRIS could attest expertise over, not an attestation itself.

## Tracked requirements

- **Umbrella(s)**: `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
