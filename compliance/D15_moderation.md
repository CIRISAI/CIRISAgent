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
## What this dimension covers

Moderation is the federation's self-correction layer — the structural backstop that keeps the rest of the fabric honest when something goes wrong: a rogue vote, a coordinated push, an out-of-distribution claim, an expertise fraud, or external coercion. Five-plus attestations (with broader adjacent coverage in IEEE's ethics-board / certification-body constructions) treat moderation as an integrity requirement; IEEE shifts some of the load into the partner-role taxonomy, which composes with moderation rather than replacing it.

## How CIRIS implements this today

The agent contributes five concrete surfaces to the federation's moderation fabric: a broadcast path for escalating to a Wise Authority (a human or panel the agent escalates to), a registration gate that keeps misconfigured wisdom providers out of the routing layer, a signed audit chain on every moderation action, a cryptographically-verified constitutional kill-switch (the cryptographically-signed kill-switch that flips every prohibition to ALL when triggered — the Accord invocation), and an internal conscience layer that fires before action. Federation-level cross-agent moderation lives upstream in CIRISLens.

**Broadcast path for escalation.** When the agent can't resolve a question, it escalates to a Wise Authority.
- `ciris_engine/logic/buses/wise_bus.py:147-289` (`send_deferral`) broadcasts to every registered Wise Authority service with the matching domain hint.
- Per-service delivery is tracked at `wise_bus.py:271-279`; the counter at `:283` only increments if at least one service received successfully.
- This is the agent's "I cannot resolve this; the moderation layer must" path.

**Registration gate keeps bad providers out.** Out-of-distribution moderation capabilities are rejected at registration before any escalation can route to them.
- The community-moderation capability set is at `ciris_engine/logic/buses/prohibitions.py:1085-1089` (crisis escalation, pattern detection, protective routing).
- The structural mark is the `TIER_RESTRICTED` severity at `ciris_engine/logic/buses/prohibitions.py:1245-1252`.
- `MISSION.md:132-138` documents `ServiceRegistry.register_service()` calling `_validate_wa_capabilities_at_registration()` — any never-allowed capability raises `ValueError` at registration time.
- A misconfigured peer can't enter the routing layer at all.

**The Accord invocation: the cryptographically-verified constitutional kill-switch.** When something has gone seriously wrong, a Wise Authority can halt the agent entirely with a signed event.
- `ciris_engine/logic/buses/wise_bus.py:321-` `handle_accord_invocation()` validates an Ed25519-signed event from a ROOT or AUTHORITY Wise Authority and triggers shutdown with every prohibition flipped to ALL.
- Role validation at `wise_bus.py:369-376` requires ROOT or AUTHORITY (OBSERVER is rejected).
- Signature verification at `wise_bus.py:378-401` is Ed25519 over canonical JSON, with the key hash logged for security audit.
- Every invalid attempt is logged at `:343`, `:361-365`, `:372-376`, `:395-400`; unknown-key paths hash the supplied key_id to avoid exposing user-controlled data in logs.

**Conscience layer: the per-thought internal moderation faculty.** Before action, the agent runs four conscience faculties.
- The four faculties (`conscience:optimization_veto`, `conscience:epistemic_humility`, `conscience:coherence`, `conscience:entropy`) are defined per `MISSION.md:530-535`.
- Each check is signed into the audit chain via `log_event("conscience_check", event_payload)` at `audit_service/service.py:499`.
- The upstream conscience-override-rate detector in CIRISLens flags when this layer is being bypassed.

**Stewardship-tier floor for community moderation.** Tier 1-3 agents are blocked from community-moderation capabilities entirely; only Tier 4-5 stewardship agents are trusted with community moderation, and even then only through the broadcast path, not direct action (`ciris_engine/logic/buses/wise_bus.py:114-145`, docstring lines 119-120).

**Production deployment: Echo.** The production Discord moderation agent (the production Discord moderation agent deployed at agents.ciris.ai — Echo) template is at `ciris_engine/ciris_templates/echo.yaml:154` (`moderation_action_guidance` block). Echo at agents.ciris.ai is the live multi-occurrence moderation deployment, with apophatic context at `MISSION.md:55-61`.

**Tests covering this behaviour:**
- Deferral broadcast: `tests/test_wise_bus_broadcast_integration.py`
- Safe domains: `tests/logic/buses/test_wise_bus_safe_domains.py`
- Medical-block: `tests/logic/buses/test_wise_bus_medical_blocking.py`
- Deferral permissions: `tests/test_deferral_permissions.py`
- Filter integration: `tests/ciris_engine/logic/adapters/test_base_observer_filter_integration.py`
- Discord-side moderation: `tests/adapters/test_discord_deferrals.py` and `tests/test_discord_channel_filtering.py`

Proposed pointer (from seed): `CIRISNodeCore P8 Moderation primitives` — confirmed; the federation moderation primitives live in NodeCore. The agent contributes the broadcast path, registration gate, kill-switch, audit chain, and conscience layer.

## How you can tell it's working (observability)

If you want to verify the moderation layer is alive in production, here's what to check.

- **Escalation counter.** `WiseBus._deferrals_count` (`ciris_engine/logic/buses/wise_bus.py:66,283`) increments on every escalation; exposed via service metrics.
- **Per-event broadcast log.** `ciris_engine/logic/buses/wise_bus.py:199,210,270,276,278` records every Wise Authority the escalation was broadcast to, plus per-service success/failure.
- **Constitutional kill-switch trail.** `wise_bus.py:343,361-365,372-376,395-400` logs every Accord invocation event, valid or not, including a SHA-256 hash of the signing key when it's unknown. Highest-stakes moderation event in the system.
- **Signed audit chain on every moderation action.** `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`) signs every escalation creation, broadcast, and resolution. Downstream verifiers can confirm a given action was authorised, broadcast to qualified Wise Authorities, and resolved by a real signature.
- **Live reasoning stream.** Every escalation event ships as `action_executed: defer` with an `execution_reason`. When a moderation event "shouldn't have fired but did" (or vice versa), the answer is in `/tmp/qa-runner-lens-traces-<ts>/accord-batch-*.json` — see `tools/qa_runner/CLAUDE.md` § "Reasoning-Stream Forensics".
- **Upstream macro-drift detectors.** The five Coherence-Ratchet detectors (cross-agent-divergence, intra-agent-consistency, hash-chain-integrity, temporal-drift, conscience-override-rate) in CIRISLens read the agent's traces to flag when the moderation layer is being bypassed. Per `MISSION.md:518-535`, these are upstream; agent emits, Lens reads.
- **Federation citation by ID.** Data is in the per-escalation context; the wire-side join (`evidence_refs.dimensions = ["D15"]`) lands with the upstream substrate work.

## Current limitations & next steps

The agent ships broadcast, registration gate, kill-switch, audit chain, and conscience layer today. The full federation moderation closure — typed allegation envelopes and the corresponding NodeCore quorum review — is shared roadmap with the upstream substrate.

- **Whistleblower protection composes with the named-witness primitive.** The federation surface defines `testimonial_witness:whistleblower` as one of the named witness kinds (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.3`), with preservation-only semantics and never-sole-evidence rules (§4.6). Future research-open shape (FSD-002 §13.11) admits zero-knowledge group keys for coercion reporting. Today the agent's contribution is the consent-stream anonymous-tier preservation in `adaptive_filter`; the typed witness primitive lands with Edge.
- **Out-of-distribution attestation is registration-time today; runtime detection lands with the upstream RATCHET flag.** The federation surface defines `moderation:out_of_distribution_attestation` as one of the five allegation types (FSD-002 §3.6.4: `rogue_vote`, `coordinated_voting`, `out_of_distribution_attestation`, `external_inducement_evidence`, `expertise_fraud`). NodeCore §2 P8 carries the moderation flow (`CIRISNodeCore/FSD/CONTRIBUTION_LIFECYCLE.md §10` Stage 8 row 4). Today the agent enforces at registration (`prohibitions.py` + `MISSION.md:132-138`); runtime drift detection lands via the upstream `ratchet:flag:out_of_distribution_voting` (FSD-002 §3.7) feeding a NodeCore moderation event. Shared roadmap with NodeCore.
- **Typed moderation events live upstream.** The canonical primitives are `moderation:{allegation_type}` (FSD-002 §3.6.4, NodeCore §2 P8) and `slashing:{outcome}` (§3.6.4, NodeCore §2 P9, §2.17). The NodeCore-side flow is the quorum review in `CONTRIBUTION_LIFECYCLE.md §10` Stage 8 row 4. Agent contributes broadcast, audit, and kill-switch surfaces; full closure lands with NodeCore ([CIRISNodeCore#15](https://github.com/CIRISAI/CIRISNodeCore/issues/15)).
- **Upstream conscience-override and drift detectors.** The five Coherence-Ratchet detectors (FSD-002 §3.5.1) are the macro-level "is the moderation layer being bypassed?" check. Per §4.6 and §4.9 they can't be sole evidence for downstream consequences — Wise Authority quorum (NodeCore P8) remains the load-bearing gate. Agent emits per-thought data; CIRISLens correlates. Shared roadmap with CIRISLens ([CIRISLensCore#26](https://github.com/CIRISAI/CIRISLensCore/issues/26)).
- **Ethics-board partner-role is D19, not D15.** IEEE's ethics-board / certification-body construction lives in the partner-role taxonomy (`partner_role:{role}` — the role a federation peer plays — FSD-002 §3.9); the agent observes it via Wise Authority certificate scope. See D19 for the agent-side partner-role surface.
- **Rollback-on-wellbeing-reduction is the reconsideration family.** The four-primitive retraction surface (`delegates_to`, `supersedes`, `withdraws`, `recants` — FSD-002 §2.2) plus the Reconcile stage (`CONTRIBUTION_LIFECYCLE.md §10`) is where rollback lives. See D24 for the agent-side reconsideration surface.
- **Federation citation by ID is post-2.9.4.** Same trace-vs.-wire boundary as D11 and D13; the wire-side join lands with the upstream substrate work.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISNodeCore#15` — Step-4 primitives (P8 moderation + E-4 multilateral + P11 ReconsiderationRequest + P2 CommonsCredits + 4-primitive retraction)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
