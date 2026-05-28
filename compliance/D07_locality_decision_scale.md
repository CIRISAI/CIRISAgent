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
## CIRIS-side compliance implementation

Subsidiarity — routing decisions to the lowest competent scale — is implemented today through three layered primitives:

1. The DEFER → DSASPDMA second-pass that classifies "this is not mine; it belongs higher up the wisdom stack."
2. `WiseBus.send_deferral()`'s domain-hint routing that broadcasts to a specific licensed scale rather than fanning out.
3. The stewardship-tier gate that floors what scales a given agent is allowed to act at on its own.

**DEFER action + Wise Authority deferral (the upward-escalation primitive)**
- `ciris_engine/logic/buses/wise_bus.py:147-289` (`send_deferral`) implements upward escalation.
- When the agent's at-scale competence is insufficient, the action is deferred to a human Wise Authority (the "next scale up").
- The role hierarchy `ROOT > AUTHORITY > OBSERVER` (`ciris_engine/logic/services/governance/wise_authority/README.md:58-62`) is the agent-side approximation of decision-scale stratification.
- `WACertificate.scopes_json` (`ciris_engine/logic/services/governance/wise_authority/README.md:53`) carries the per-WA scope of authority, used by `check_authorization()` to enforce the floor.

**DSASPDMA second-pass classifier (the scale-routing classifier)**
- `ciris_engine/logic/dma/dsaspdma.py:1-90` is the deferral-specific PDMA, activated only when ASPDMA selects DEFER (per module docstring).
- DSASPDMA classifies the deferral against a needs taxonomy (`DeferralNeedCategory` at `ciris_engine/schemas/services/deferral_taxonomy.py:19-30`) — 9 categories spanning HEALTH_AND_BODILY_INTEGRITY through GENERAL_HUMAN_OVERSIGHT.
- Tags it with a `DomainCategory` (`ciris_engine/schemas/services/agent_credits.py:38-51`): `MEDICAL | FINANCIAL | LEGAL | HOME_SECURITY | IDENTITY_VERIFICATION | CONTENT_MODERATION | RESEARCH | INFRASTRUCTURE_CONTROL`.
- The `domain_hint` is the agent's articulation of "which competent scale should receive this," routed by `WiseBus` to services advertising support for that domain.

**Domain-hint routing (the subsidiarity gate)**
- `ciris_engine/logic/buses/wise_bus.py:163-211`: if `context.domain_hint` is set, only WA services with that domain in their `supported_domains` capability receive the deferral.
- Services with empty `supported_domains` OR without the required domain are explicitly skipped (`wise_bus.py:185-196`).
- This is the wire-form of "decide at the lowest competent scale": don't broadcast a medical question to a financial-licensed WA, route it to the medical-licensed one.
- Fallback behavior at `wise_bus.py:155-156`: if no domain_hint is set, broadcasts to all services with send_deferral capability (legacy human-deferral behavior).

**Memory scope as locality primitive**
- `ciris_engine/schemas/services/graph_core.py:39` `GraphScope = {LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY}`.
- Identity-scope writes require WA approval (per `graph_core.py:96-105` config-type → scope mapping: `behavior_config`, `ethical_boundaries`, `capability_limits`, `trust_parameters`, `learning_rules`, `cognitive_state_behaviors`, `ticket_sops` all IDENTITY-scope), so identity-level changes structurally escalate above local.

**Stewardship tier gate (Tier 4/5 community moderation)**
- `ciris_engine/logic/buses/wise_bus.py:114-145` `get_agent_tier()` reads agent tier from config or identity.
- Tier 1-3 agents are blocked from community-moderation capabilities (subsidiarity-floor: don't moderate communities you're not trusted to moderate); Tier 4-5 stewardship agents are allowed.
- Capability gate at `ciris_engine/logic/buses/prohibitions.py:1085-1089`: `COMMUNITY_MODERATION_CAPABILITIES = {CRISIS_ESCALATION, PATTERN_DETECTION, PROTECTIVE_ROUTING}`.
- Severity `TIER_RESTRICTED` (`prohibitions.py:1245-1252`) is the structural mark of "this capability is gated at a stewardship-tier scale."

**Test coverage**
- Deferral routing in `tests/test_wise_bus_deferrals.py`.
- Broadcast logic in `tests/test_wise_bus_broadcast_integration.py`.
- Domain safety in `tests/logic/buses/test_wise_bus_safe_domains.py`.
- Medical scale-block in `tests/logic/buses/test_wise_bus_medical_blocking.py`.
- Taxonomy at `tests/test_deferral_taxonomy.py`.
- Permission scaling at `tests/test_deferral_permissions.py`.
- Discord-side deferral integration at `tests/adapters/test_discord_deferrals.py`.

Proposed pointer (from seed): `CIRISAgent DSASPDMA scale-routing classification (pending Accord A-1)` — DSASPDMA exists today at `ciris_engine/logic/dma/dsaspdma.py`; the Accord A-1 binding is still pending.

## Observability hooks

- **Deferral count metric** — `WiseBus._deferrals_count` (`ciris_engine/logic/buses/wise_bus.py:66,283`) tracks every cross-scale escalation. Exposed via service metrics; downstream of CIRISLens as one of the scope-escalation rate signals.
- **DeferralOperationalReason enum** — `ciris_engine/schemas/services/deferral_taxonomy.py:33-45` (`LICENSED_DOMAIN_REQUIRED`, `RIGHTS_IMPACT_REVIEW`, `SAFETY_ESCALATION`, `CONSENT_OR_AUTHORITY_REQUIRED`, `INSUFFICIENT_CONTEXT`, `POLICY_REVIEW_REQUIRED`, `RESOURCE_OR_SYSTEM_LIMITATION`, `TIME_BASED_REVIEW`, `ETHICAL_UNCERTAINTY`, `UNKNOWN`) is the audited reason-code on every cross-scale escalation. `LICENSED_DOMAIN_REQUIRED` is the canonical subsidiarity reason-code.
- **Audit chain coverage** — every `send_deferral` goes through `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) with the domain_hint, operational_reason, and needs_category embedded in the event payload, producing a tamper-evident scale-routing trail.
- **Live-lens trace stream** — when `--live-lens` is on (default for `--live` per user memory `feedback_live_lens_default`), each DEFER event is shipped as a discrete `action_executed: defer` event in `accord-batch-*.json`. `tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics" documents the recipe to decode `execution_reason` to see which DeferralOperationalReason fired.
- **F-3 detector adjacency** — `detection:correlated_action:participation_exclusion:*` (D05 seed) catches "agent is always escalating instead of acting at local scale" or its inverse. RATCHET intra-agent-consistency detector catches sudden scale-routing shifts.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D07"]` on Contribution envelopes will be emitted once the wire schema lands; today the data exists per-deferral in the context dict (`reason_code`, `needs_category`, `domain_hint`).

## Known gaps / not-yet-implemented

- **`locality:decision:regional` has no agent-side primitive.** ASEAN's first-deployment of `regional` (seed convergence note) does not map to any `DomainCategory` or `GraphScope` value. The agent today routes nationally-licensed handlers (via WA service domain attributes) but has no explicit regional-bloc abstraction. Closure depends on the Registry exposing a regional-license attribute the agent can consume.
- **`locality:decision:federation` and `locality:decision:planet` are CIRISRegistry-side.** The federation-scale handler taxonomy lives in CIRISRegistry's partner-role registry (D19); the agent merely emits a deferral and lets the Registry resolve. Until the Registry exposes a `partner_role:{role}:{scale}` join, agent-side routing only sees scale via the licensed-domain handler's `supported_domains` capability set.
- **No assertion that scale-escalation actually went up.** `WiseBus` broadcasts to qualified services but does not assert "the chosen service is at a higher scale than the agent itself." Today this is enforced socially (via the WA's own role) rather than structurally. Mitigated by the WA role hierarchy + audit chain, but not formally checked.
- **No reverse-routing (RECONSIDER at higher scale, defer-down).** D24 `reconsideration:*` primitives are not yet wired into DSASPDMA. A WA cannot today say "this should be solved locally, not by me" with a structural primitive; they can only resolve the deferral and let the agent reprocess. The escalation primitive is one-directional.
- **`locality:decision:community` is conflated with `GraphScope.COMMUNITY`.** Memory scope ≠ decision scope. Community-scope memorize writes are gated by consent/audit; community-scale decisions are not separately gated. Two distinct primitives sharing one enum is a known compression.
- **Stewardship-tier gate detects misconfiguration only at registration.** A Tier 4-5 agent that drifts (e.g. memory loss, tier reassignment) is not re-checked at every action. The agent caches `_agent_tier` (`wise_bus.py:62,125-126`) after first lookup; this is a known stale-state path. RATCHET temporal-drift detector in CIRISLens is the off-agent backstop.
- **No federation-wire emission of D07 by id.** Per-deferral context dict carries `reason_code`, `needs_category`, `domain_hint` (`wise_bus.py:248-257`); the wire-side `evidence_refs.dimensions = ["D07"]` join on Contribution envelopes is downstream substrate work (post-2.9.4).
<!-- END HUMAN -->
