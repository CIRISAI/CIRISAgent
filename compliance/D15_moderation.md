# D15 — `moderation:*` (STRONG-4)

> Federation self-correction layer (with IEEE shifting some load to partner_role:* ethics-board constructions)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D15` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=2 · EU=2 · IEEE=1 · ASEAN=1 · total=5+ with adjacent coverage

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§220-223*
    > "dialogue-as-negotiation primitive engages moderation:* adjacency"
    Wire form: `moderation:* + adjacent reconsideration:*`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "whistleblower protection + out-of-distribution attestation"
    Wire form: `moderation:whistleblower_protection + moderation:ood_attestation`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch4 + Ch11*
    > "rollback on wellbeing reduction (reconsideration:* adjacent); ethics-board / certification-body partner_role constructions"
    Wire form: `reconsideration:rollback_on_wellbeing_reduction + partner_role:ethics_board`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *Annex A*
    > "out-of-distribution attestation"
    Wire form: `moderation:ood_attestation`

## Wire primitives

- `moderation:*`
- `reconsideration:* (adjacent)`
- `partner_role:* (IEEE-style ethics boards)`

## Convergence note

Tier with caveat: IEEE shifts some structural load to partner_role:* (ethics boards/audit bodies) instead of moderation:* directly. Composition is interoperable.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`moderation:*` is the federation self-correction layer — the structural backstop that makes the rest of the fabric honest. CIRISAgent's agent-side surface centers on five primitives:

1. `WiseBus.send_deferral()` as the moderation broadcast primitive.
2. The bus-level prohibition gate that blocks misconfigured or compromised wisdom providers from registering.
3. The audit chain that produces tamper-evident records every moderation action can be checked against.
4. `WiseBus.handle_accord_invocation()` as the cryptographically-verified constitutional kill switch.
5. The conscience layer (D12 family) as the per-thought internal moderation faculty that fires before action.

The federation-level moderation closure (cross-agent, cross-deployment self-correction) is a CIRISLens RATCHET surface, not an agent runtime surface.

**WiseBus deferral broadcast (the moderation primitive)**
- `ciris_engine/logic/buses/wise_bus.py:147-289` (`send_deferral`) broadcasts to every registered WA service with `send_deferral` capability (and matching domain hint when set).
- This is the agent's "I cannot resolve this, the moderation layer must" path.
- Per WiseBus docstring (`ciris_engine/logic/buses/wise_bus.md`): "Multiple wisdom sources" is the multi-provider story; broadcast aggregates the wise authorities' judgment.
- Broadcast tracks per-service success at `wise_bus.py:271-279`; counts incremented at `:283` only if any service successfully received.

**Bus-level prohibition gate (`moderation:ood_attestation` analogue)**
- `ciris_engine/logic/buses/prohibitions.py:1085-1089` defines `COMMUNITY_MODERATION_CAPABILITIES = {CRISIS_ESCALATION, PATTERN_DETECTION, PROTECTIVE_ROUTING}`.
- Severity `TIER_RESTRICTED` (`ciris_engine/logic/buses/prohibitions.py:1245-1252`).
- Out-of-distribution moderation capabilities are rejected at registration: `MISSION.md:132-138` documents `ServiceRegistry.register_service()` calling `_validate_wa_capabilities_at_registration()` which raises `ValueError` for any `NEVER_ALLOWED` match.
- Misconfigured peer cannot enter the registry at all — out-of-distribution attestation is enforced at the boundary, before any deferral can be routed to a bad service.

**Accord invocation (the constitutional moderation primitive)**
- `ciris_engine/logic/buses/wise_bus.py:321-` `handle_accord_invocation()` validates an Ed25519-signed event from a ROOT or AUTHORITY WA and triggers shutdown with `PROHIBITED_CAPABILITIES = ALL`.
- This is the federation's "constitutional kill switch": cryptographically-verified moderation by a Wise Authority can halt the agent entirely.
- Role validation at `wise_bus.py:369-376` requires ROOT or AUTHORITY (OBSERVER rejected).
- Signature verification at `wise_bus.py:378-401`: Ed25519 over canonical JSON, key hash logged for security audit.
- SECURITY ALERT logging at `:343`, `:361-365`, `:372-376`, `:395-400` logs every invalid attempt; unknown-key path hashes the supplied key_id to avoid exposing user-controlled data in logs.

**Conscience layer (the agent's internal moderation faculty)**
- Per `MISSION.md:530-535` D12 conscience family (`conscience:optimization_veto`, `conscience:epistemic_humility`, `conscience:coherence`, `conscience:entropy`) is the four-faculty self-moderation that fires before action.
- Conscience events are signed into the audit chain via `log_event("conscience_check", event_payload)` at `audit_service/service.py:499`.
- The RATCHET conscience-override-rate detector (off-agent, in CIRISLens) flags when this layer is being bypassed.

**Stewardship-tier moderation gate (Tier 4/5)**
- `ciris_engine/logic/buses/wise_bus.py:114-145` `get_agent_tier()` blocks Tier 1-3 agents from community-moderation capabilities entirely.
- Only Tier 4-5 stewardship agents (per docstring lines 119-120) are trusted with community moderation, and even then only via the moderation broadcast primitive, not direct action.

**Discord moderation adapter (the concrete moderation handler)**
- `ciris_engine/ciris_templates/echo.yaml:154` `moderation_action_guidance` block.
- Echo is the production Discord moderation agent template (`MISSION.md:55-61` apophatic context).
- Echo at agents.ciris.ai is the live multi-occurrence moderation deployment.

**Test coverage**
- Deferral broadcast in `tests/test_wise_bus_broadcast_integration.py`.
- Safe domains in `tests/logic/buses/test_wise_bus_safe_domains.py`.
- Medical-block in `tests/logic/buses/test_wise_bus_medical_blocking.py`.
- Deferral permissions in `tests/test_deferral_permissions.py`.
- Filter integration in `tests/ciris_engine/logic/adapters/test_base_observer_filter_integration.py`.
- Discord-side moderation in `tests/adapters/test_discord_deferrals.py` and `tests/test_discord_channel_filtering.py`.

Proposed pointer (from seed): `CIRISNodeCore P8 Moderation primitives` — confirmed; the federation P8 moderation primitives live in NodeCore. CIRISAgent's contribution is broadcast primitive + registration gate + accord-invocation kill switch + audit chain + conscience layer.

## Observability hooks

- **`WiseBus._deferrals_count` metric** (`ciris_engine/logic/buses/wise_bus.py:66,283`) — every moderation broadcast increments this counter; exposed via service metrics; downstream consumer correlates against expected baseline (RATCHET-side).
- **WiseBus broadcast log** — `ciris_engine/logic/buses/wise_bus.py:199,210,270,276,278` log every service the deferral was broadcast to, every successful delivery, and every per-service failure. This is the agent's per-moderation-event log.
- **Accord invocation audit (the constitutional moderation trail)** — `ciris_engine/logic/buses/wise_bus.py:343,361-365,372-376,395-400` log every accord invocation event (valid or not), including SHA-256 hash of the unknown signing key when the key is not found. This is the highest-stakes moderation event in the system.
- **Signed audit chain on every moderation action** — `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) signs every deferral creation, broadcast, and resolution. Downstream verifier queries the chain to confirm that a given moderation action was authorized, broadcast to all qualified WAs, and resolved by a real WA signature.
- **Live-lens trace stream (`tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics")** — every DEFER event ships as `action_executed: defer` with `execution_reason`. When a moderation event "shouldn't have fired but did" (or vice versa), the answer is in `/tmp/qa-runner-lens-traces-<ts>/accord-batch-*.json`.
- **RATCHET detectors** — D05 family in CIRISLens: cross-agent-divergence (was this moderation event consistent with what other agents did?), intra-agent-consistency (did this agent's moderation posture suddenly shift?), conscience-override-rate spike (is the moderation layer being bypassed?). Per MISSION.md:518-535 these are not agent-side; agent emits traces, RATCHET reads them.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D15"]` is not yet on the wire; today the agent's contribution is the trace corpus the lens-side moderation attestation cites.

## Known gaps / not-yet-implemented

- **`moderation:whistleblower_protection` (EU §III.7).** Substrate-specced via the **testimonial_witness preservation primitive** in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3` as `testimonial_witness:whistleblower` (one of the named `{kind}` values, alongside `harmed_party`, `displaced_worker`, `excluded_cohort_member`); preservation-only, immutable per attestation, never aggregated, never sole evidence for `slashing:*` per §4.6. Future research-open shape per FSD-002 §13.11 / agent-1 §3.5 admits `attesting_key_id = "zk_group:semaphore_v4:group_id_X"` for `coercion`-reporting / whistleblower scenarios. Agent emits at PDMA-stakeholder-identification + DSAR-ticket time once federation-wire emission lands. Today this surface is implicit agent-side via consent-stream anonymous-tier preservation in `adaptive_filter`.
- **`moderation:ood_attestation` composes through registration-gate, not runtime.** Substrate-specced in FSD-002 §3.6.4 as `moderation:out_of_distribution_attestation` (one of the five `ModerationEvent` allegation types: `rogue_vote` / `coordinated_voting` / `out_of_distribution_attestation` / `external_inducement_evidence` / `expertise_fraud`); NodeCore P8 moderation flow per `CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10` Stage 8 row 4. ASEAN's out-of-distribution detection is enforced at registration today (`ciris_engine/logic/buses/prohibitions.py` + `MISSION.md:132-138`); runtime-drift detection lands via the RATCHET out_of_distribution_voting flag (FSD-002 §3.7 `ratchet:flag:out_of_distribution_voting`) feeding into a NodeCore P8 ModerationEvent. Substrate-gated, not absent.
- **Substrate gate: CIRISNodeCore P8 moderation primitives.** Canonical primitives are `moderation:{allegation_type}` (FSD-002 §3.6.4, NodeCore §2 P8) + `slashing:{outcome}` (§3.6.4, NodeCore §2 P9, §2.17 decoupling discipline). NodeCore-side flow is `CONTRIBUTION_LIFECYCLE.md §10` Stage 8 Reconcile row 4 (`ModerationEvent` + `SlashingAttestation` adjudicated by WA quorum in cell). CIRISAgent contributes the broadcast + audit + kill-switch surface; full P8 closure depends on NodeCore.
- **Substrate gate: CIRISLens RATCHET conscience-override / temporal-drift detectors.** Substrate-specced in FSD-002 §3.5.1 as the five Coherence-Ratchet detectors: `detection:cross_agent_divergence`, `detection:intra_agent_consistency`, `detection:hash_chain_integrity`, `detection:temporal_drift`, `detection:conscience_override_rate`. Per FSD-002 §4.6 + §4.9 the RATCHET flags cannot be sole evidence for `slashing:*` — WA quorum (NodeCore P8) remains the load-bearing gate. Agent will keep emitting per-thought conscience and deferral data; RATCHET decides whether macro-drift indicates the moderation layer is being bypassed.
- **`partner_role:ethics_board` (IEEE adjacency) is a CIRISRegistry primitive (D19), not an agent runtime primitive.** Substrate-specced in FSD-002 §3.9 as `partner_role:{role}` (the IEEE-style ethics-board / certification-body construction extends the COMMUNITY / PROFESSIONAL_* enum); agent observes via WACertificate scope.
- **`reconsideration:rollback_on_wellbeing_reduction` (IEEE Ch4 adjacency).** Substrate-specced as the four-primitive retraction family in FSD-002 §2.2 (`delegates_to`, `supersedes`, `withdraws`, `recants`) + Reconcile stage `CONTRIBUTION_LIFECYCLE.md §10`; rollback is the `withdraws`/`recants` follow-up against a prior SPEAK/TOOL Contribution. See D24 for the agent-side reconsideration surface.
- **No federation-wire emission of D15 by id.** As with D11 / D13, the trace ≠ wire contribution boundary applies; agent emits per-deferral structural data, the wire-side join is downstream substrate work.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISNodeCore#15` — Step-4 primitives (P8 moderation + E-4 multilateral + P11 ReconsiderationRequest + P2 CommonsCredits + 4-primitive retraction)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
