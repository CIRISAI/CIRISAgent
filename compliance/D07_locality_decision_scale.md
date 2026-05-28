# D07 — `locality:decision:{scale}` (STRONG-4)

> v1.3 subsidiarity closure — decision routing at lowest competent scale

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D07` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=17 · EU=5 · IEEE=13 · ASEAN=7 · total=42

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§68-72*
    > "decisions should be made at the lowest competent level"
    Wire form: `locality:decision:local + locality:decision:community`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.0*
    > "EU-level decisions vs national-level decisions; supranational coordination"
    Wire form: `locality:decision:national + locality:decision:community`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch10*
    > "national A/IS policy; international R&D collaboration"
    Wire form: `locality:decision:national + locality:decision:federation`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§C.4 + §E*
    > "regional ASEAN-level coordination; community-level deployment decisions"
    Wire form: `locality:decision:regional (3) + locality:decision:community (2) + locality:decision:national (3)`

## Wire primitives

- `locality:decision:{local,community,national,regional,federation,planet}`

## Convergence note

First cross-source structural validation of the v1.3 subsidiarity addition. ASEAN exercises locality:decision:regional as first-deployment of that scale value.

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Decisions should be made at the lowest competent level — close to the people affected, escalated upward only when the local scale genuinely can't handle them (decisions made at the lowest competent scale — subsidiarity). This dimension is about the agent recognising when something is over its head and routing it to the right next level instead of either over-acting or fanning out indiscriminately. Forty-two attestations across MH, EU, IEEE, and ASEAN treat this as a core fairness concern.

## How CIRIS implements this today

When the agent meets a question it can't resolve at its own scale, it escalates to a Wise Authority (a human or panel the agent escalates to), but it doesn't just broadcast — it tags the request with a domain hint so only the right kind of authority is consulted. Three layers make this concrete: an escalate-to-human action (DEFER — escalate to a Wise Authority), a second-pass classifier that decides which authority is competent, and a stewardship tier (the agent's level of authorization — stewardship tier) that floors what an agent can do on its own.

**Escalation to a Wise Authority.** When the agent's competence at its own scale is not enough, it escalates upward.
- `ciris_engine/logic/buses/wise_bus.py:147-289` (`send_deferral`) implements the escalation path.
- The role hierarchy `ROOT > AUTHORITY > OBSERVER` (`ciris_engine/logic/services/governance/wise_authority/README.md:58-62`) is the agent-side stratification of decision authority.
- Each Wise Authority carries a scope of authority in `WACertificate.scopes_json` (`ciris_engine/logic/services/governance/wise_authority/README.md:53`), enforced by `check_authorization()`.

**Scale-routing classifier (DSASPDMA).** When the agent decides to escalate, a second-pass classifier figures out which authority is the right one to receive it.
- The classifier lives at `ciris_engine/logic/dma/dsaspdma.py:1-90` and fires only when the agent's primary decision is to escalate.
- It assigns a needs category from a nine-value taxonomy at `ciris_engine/schemas/services/deferral_taxonomy.py:19-30` (covering health, justice, privacy, livelihood, and general human oversight).
- It also tags a domain category from `ciris_engine/schemas/services/agent_credits.py:38-51`: medical, financial, legal, home security, identity verification, content moderation, research, or infrastructure control.
- The combined hint is the agent's articulation of "the competent scale for this question is X."

**Routing by domain hint.** The routing layer respects the hint instead of broadcasting blindly.
- `ciris_engine/logic/buses/wise_bus.py:163-211`: when a domain hint is set, only Wise Authority services advertising that domain receive the request.
- Services without the required domain are skipped (`wise_bus.py:185-196`).
- A medical question routes to medical-licensed authorities, not to financial ones.
- Fallback: when no domain hint is set, the request broadcasts to every Wise Authority with deferral capability (`wise_bus.py:155-156`).

**Memory scope reinforces the same discipline.** Some kinds of memory writes structurally require Wise Authority approval.
- `ciris_engine/schemas/services/graph_core.py:39` defines the four memory scopes.
- The mapping at `graph_core.py:96-105` pins ethical boundaries, capability limits, trust parameters, and behaviour configuration to the IDENTITY scope — those changes can only happen with Wise Authority sign-off.

**Stewardship tier floor for community moderation.** A new or low-tier agent doesn't get to moderate communities it isn't trusted to moderate.
- `ciris_engine/logic/buses/wise_bus.py:114-145` `get_agent_tier()` reads the agent's tier from config or identity.
- Tiers 1-3 are blocked from community-moderation capabilities; tiers 4-5 (stewardship) are allowed.
- The gated capabilities are listed at `ciris_engine/logic/buses/prohibitions.py:1085-1089` (crisis escalation, pattern detection, protective routing).
- The structural mark for "this needs a stewardship tier" is the `TIER_RESTRICTED` severity at `prohibitions.py:1245-1252`.

**Tests covering this behaviour:**
- Deferral routing: `tests/test_wise_bus_deferrals.py`
- Broadcast logic: `tests/test_wise_bus_broadcast_integration.py`
- Domain safety: `tests/logic/buses/test_wise_bus_safe_domains.py`
- Medical scale-block: `tests/logic/buses/test_wise_bus_medical_blocking.py`
- Taxonomy: `tests/test_deferral_taxonomy.py`
- Permission scaling: `tests/test_deferral_permissions.py`
- Discord-side integration: `tests/adapters/test_discord_deferrals.py`

Proposed pointer (from seed): `CIRISAgent DSASPDMA scale-routing classification (pending Accord A-1)` — the classifier exists today at `ciris_engine/logic/dma/dsaspdma.py`; the Accord A-1 binding is still pending.

## How you can tell it's working (observability)

If you want to verify subsidiarity is alive in production, here's what to check.

- **Escalation counter.** `WiseBus._deferrals_count` (`ciris_engine/logic/buses/wise_bus.py:66,283`) tracks every escalation. Exposed via service metrics.
- **Reason codes on every escalation.** `ciris_engine/schemas/services/deferral_taxonomy.py:33-45` enumerates the audited reasons — `LICENSED_DOMAIN_REQUIRED` is the canonical subsidiarity reason. Each escalation carries one.
- **Signed audit chain.** Every `send_deferral` is signed by `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) with the domain hint, reason code, and needs category embedded.
- **Live reasoning stream.** When live-lens tracing is on, every escalation ships as a discrete event in `accord-batch-*.json`. `tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics" documents the decode recipe.
- **Upstream pattern detection.** The structural-pattern detector (`detection:correlated_action:participation_exclusion:*`) catches "always escalating" or "never escalating" patterns. Lives in CIRISLens; agent emits the data.
- **Federation citation by ID.** Once the federation envelope includes `evidence_refs.dimensions = ["D07"]`, the per-deferral context already has the reason code, needs category, and domain hint ready to cite (`wise_bus.py:248-257`).

## Current limitations & next steps

Most of this dimension's remaining work is shared with the upstream CIRIS substrate. The agent already emits the per-deferral data; the remaining steps add federation-wire structure on top.

- **Regional and federation scales are upstream-defined.** The federation surface (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.5`) defines `locality:decision:{scale}` with values `local`, `regional`, `national`, `federation`. The agent's escalation today routes via the licensed-domain hint; the regional and federation scale values land once Registry and NodeCore expose the decision-authority extension. The locality-scaled quorum policy (FSD-002 §6.1.5) is the upstream check that pairs with the agent's emit. Shared roadmap with NodeCore. ([CIRISAgent#821](https://github.com/CIRISAI/CIRISAgent/issues/821))
- **Planet scale composes with `goal:planet`.** Planet-scale decisions are carried by the goal-scale enum rather than the locality-scale enum (FSD-002 §3.6.2 v1.4). Agent picks both up once Registry + NodeCore expose the extension.
- **Cross-scale assertion is upstream.** A formal check that "the chosen authority is in fact at a higher competent scale than the agent" rides on the locality-scaled quorum policy (FSD-002 §6.1.5). The agent's contribution today is the Wise Authority role hierarchy plus the signed audit chain; the structural assertion lands substrate-side.
- **Downward reconsideration ("this should be handled locally, not by me") is a v1.3 federation primitive.** The reconsideration shape (FSD-002 §3.6.4, `reconsideration:{grounds}`) and the fresh-quorum review flow (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10`) are upstream-defined; the agent will emit downward-defer once that primitive ships. See D24 for the agent-side reconsideration surface.
- **Memory scope and decision scope share an enum at `COMMUNITY`.** Memory writes at community scope are gated by consent and audit; community-scale decisions are not separately gated. A known compression of two related but distinct concepts; cleanup is a future refinement.
- **Stewardship tier is cached at first lookup.** `_agent_tier` (`wise_bus.py:62,125-126`) is cached, so a tier change isn't re-checked on every action. Per-action recheck is tracked at [CIRISAgent#810](https://github.com/CIRISAI/CIRISAgent/issues/810); the upstream temporal-drift detector in CIRISLens is the cross-deployment backstop today.
- **Federation citation by ID is post-2.9.4.** The data is already in the per-deferral context (`wise_bus.py:248-257`); the wire-side join lands with the upstream substrate work.

## Tracked requirements

- **Umbrella(s)**: `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)
- **2.9.6**: `CIRISAgent#810` — tier re-check per action
- **2.9.7**: `CIRISAgent#821` — scale-escalation assertion in wise_bus

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
