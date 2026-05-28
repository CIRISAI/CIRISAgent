# D19 — `partner_role:*` (STRONG-3)

> CIRIS Registry partner-role taxonomy (ethics boards, audit bodies, stewards)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D19` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=0 · EU=1 · IEEE=19 · ASEAN=1 · total=21

**Absent from**: MH — MH names ecclesial relations rather than secular institutional partner-role taxonomies.
  *Functional analogue*: Ecclesial-magisterial relations carry analogous structural role but in different vocabulary

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **EU** (Ethics Guidelines for Trustworthy AI) — *§III.7*
    > "audit/compliance partners"
    Wire form: `partner_role:audit_body`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch7 + Ch9 + Ch10 + Ch11 (19 attestations)*
    > "Chief Values Officer, ethics committees, certification bodies, ISO-like body, accreditation bodies, HRIA/AIA stewards, trusted disclosure stewards"
    Wire form: `partner_role:{19 distinct roles}`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§E.001*
    > "ASEAN Working Group on AI Governance (regional intergovernmental dual-remit)"
    Wire form: `partner_role:regional_intergovernmental_working_group`

## Wire primitives

- `partner_role:{role}`

## Convergence note

REINFORCED v1.5+ T-3 candidate here: specialization-pattern proposal covers dual-remit (ASEAN) + trusted-disclosure-steward (IEEE).

## v1.5+ T-3 candidates affecting this dimension

- **T3-07** `partner_role:trusted_disclosure_steward:{authority}` (priority MEDIUM, source(s): ieee_ead_v1)
- **T3-08** `partner_role:regional_intergovernmental_working_group_dual_remit` (priority MEDIUM, source(s): asean_guide_v1)

---

<!-- BEGIN HUMAN -->
## What this dimension covers

In a real federation, partners come in many shapes — ethics boards, audit bodies, certification bodies, human-rights / AI-impact stewards, trusted disclosure stewards, regional intergovernmental working groups, ISO-like accreditation bodies (the role a federation peer plays — partner role). Twenty-one attestations (IEEE alone contributes 19 distinct role values) treat the partner-role taxonomy as a structural integrity requirement; ASEAN contributes the dual-remit shape; Magnifica Humanitas, notably, names ecclesial-magisterial relations rather than secular institutional roles in its functional analogue.

## How CIRIS implements this today

This dimension is owned by the CIRIS Registry, not the agent. The agent's job is to consume the resolved partner credentials Registry issues, accept signed events from authority partners, and emit audit traces that partner-role auditors can verify. Three concrete surfaces matter at runtime: the Wise Authority certificate (a human or panel the agent escalates to — Wise Authority), the Accord invocation path (the cryptographically-signed kill-switch that flips every prohibition to ALL when triggered), and the per-partner deferral queue.

**Registry as the partner-role authority.** Per `MISSION.md:500`, the Registry is the federation's identity, build, license, and revocation directory — a dual-region (US/EU) Rust gRPC service deployed at `*.ciris-services-1.ai`, SOC2/HIPAA/GDPR-compliant. It is the bootstrap node. Partner-role attestation is a Registry artifact; the agent receives the resolved certificate.

**Wise Authority role hierarchy (the closest agent-side primitive).** The agent has a three-bucket approximation of partner-role taxonomy.
- `ciris_engine/logic/services/governance/wise_authority/README.md:44-62` defines `WARole = {ROOT, AUTHORITY, OBSERVER}`.
- A coarse three-element hierarchy is enough for runtime authorisation but isn't expressive enough for IEEE's 19-distinct-role taxonomy or ASEAN's dual-remit shape.
- `WACertificate` carries `wa_id` (format `wa-YYYY-MM-DD-XXXXXX`), `pubkey` (Ed25519), `jwt_kid`, and `scopes_json`; the partner-role-shaped attributes live inside `scopes_json` as Registry-issued metadata.

**Accord invocation as the authority-partner kill-switch.** The constitutional kill-switch is the agent's runtime hook to IEEE's "trusted disclosure steward" / "Chief Values Officer" partner-role shapes.
- `ciris_engine/logic/buses/wise_bus.py:321-` `handle_accord_invocation()` validates that the signing Wise Authority has ROOT or AUTHORITY role (`wise_bus.py:371-376`).
- The Ed25519 signature (`wise_bus.py:378-401`) is the cryptographic binding that gives partner-role attestation its evidentiary basis.

**Domain category as a partner-role specialisation slot.** The agent has a licensed-domain enum that approximates institutional specialisation.
- `ciris_engine/schemas/services/agent_credits.py:38-51` defines `DomainCategory = {MEDICAL | FINANCIAL | LEGAL | HOME_SECURITY | IDENTITY_VERIFICATION | CONTENT_MODERATION | RESEARCH | INFRASTRUCTURE_CONTROL}`.
- A Wise Authority advertising `supported_domains=[MEDICAL]` is the runtime expression of "registered medical partner"; escalations route by domain hint.
- This is partner-role at the domain-specialisation level, not the institutional-shape level — a medical audit-body and a medical certification-body look identical to the agent today.

**Adapter manifest as the runtime peer-partner record.** Per `CLAUDE.md` § "Adapter Development", every adapter ships a `manifest.json` declaring its capabilities. Adapters are the closest thing to a partner-role at runtime; reference implementations are at `ciris_adapters/sample_adapter/`, `ciris_adapters/home_assistant/`, and `ciris_adapters/wallet/` (the wallet example uses `dma_guidance=ToolDMAGuidance(requires_approval=True)` — the partner-role financial-tool gate).

**`scopes_json` as the per-partner scope-of-authority record.** `ciris_engine/logic/services/governance/wise_authority/README.md:53` carries the partner's permitted scopes as a JSON array of Registry-issued metadata. The agent enforces but does not author the scopes.

**Tests covering this behaviour:**
- Wise Authority certificate and scope validation: `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`
- Partner-domain routing: `tests/logic/buses/test_wise_bus_safe_domains.py`
- Registration-time prohibition validation: `tests/test_wise_bus_deferrals.py`
- JWT auth and role checks: `tests/adapters/api/test_jwt_auth.py`

Proposed pointer (from seed): `CIRISRegistry partner role registry` — confirmed; primary owner is the Registry, agent runtime consumes resolved certificates only.

## How you can tell it's working (observability)

If you want to verify partner-role authorisation is alive in production, here's what to check.

- **Signed audit chain.** Every guidance, escalation, and Accord-invocation event from a partner is signed by `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`). Downstream verifiers confirm "this action was authorised by a partner with role X."
- **Registration validation log.** `_validate_wa_capabilities_at_registration()` (per `MISSION.md:132-138`) validates every partner registration against the 22-category prohibition table; the validation event is logged. Misconfigured or compromised partners can't enter the routing layer at runtime.
- **Per-partner pending queue.** `get_pending_deferrals(wa_id)` (`ciris_engine/logic/services/governance/wise_authority/README.md:139-143`) gives per-partner operational visibility.
- **Live reasoning stream.** When live-lens tracing is on, every guidance response in `accord-batch-*.json` carries the Wise Authority signature and (where available) the partner-role context; `wa_id` is the per-partner identifier.
- **Federation citation by ID.** This dimension is Registry-attested, so `evidence_refs.dimensions = ["D19"]` is emitted by Registry on partner attestations. The agent contributes the audit-chain trace ("the partner-X action took place"); Registry contributes the role claim ("the partner has role X").
- **Upstream integrity and pattern detectors.** D02 integrity and D05 detection families in CIRISLens jointly verify that partner roles aren't silently shifted post-registration; agent emits the data, Lens correlates.

## Current limitations & next steps

This dimension is intentionally Registry-owned. The agent's current limitations are mostly about expressiveness — a three-bucket role hierarchy that gets richer once the upstream taxonomy ships.

- **Full partner-role taxonomy lives upstream.** The federation surface defines `partner_role:{role}` (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.9`) with enum values `COMMUNITY`, `COMMUNITY_PLUS`, `PROFESSIONAL_MEDICAL`, `PROFESSIONAL_LEGAL`, `PROFESSIONAL_FINANCIAL`, `PROFESSIONAL_FULL` (citing `CLAUDE.md` "License Types"). IEEE's 19 distinct roles compose via the `PROFESSIONAL_*` enum plus the co-owned `licensure:{authority_id}` field (FSD-002 §3.9, §3.2; co-owned with Verify per §13.3). The agent picks this up via the certificate plus `LookupPartner` (FSD-002 §7.7, line 1397) once Registry exposes the taxonomy. Shared roadmap with Registry ([CIRISRegistry#25](https://github.com/CIRISAI/CIRISRegistry/issues/25)).
- **Per-role attestation chain is Registry-side.** Closure depends on Registry exposing the per-role attestation chain. The `RegisterPartner` endpoint (FSD-002 line 1418) writes attestations on `partner_role:{role}`, `licensure:{authority}`, and `bond_posted:{currency}` per partner request.
- **Trusted-disclosure-steward role (T3-07).** Uses the `delegates_to` authority-source pattern (FSD-002 §2.2.1 v1.3): a partner names its source of authority by emitting `delegates_to` against an attested key representing the framework, with `delegated_scope` naming the principle. Depends on Registry exposing both the steward role and the authority pointer chain.
- **Dual-remit (T3-08).** The ASEAN Working Group on AI Governance composes via `partner_role:{role}` plus `multilateral_participation:{forum}:{kind}` (FSD-002 §3.9). Dual-remit is the joint claim across both prefixes; Registry-side schema work is shared roadmap. Agent has no concept of "dual remit" today.
- **Sovereign and Registered partners are wire-equivalent, policy-differentiated.** FSD-002 §6.4 makes Sovereign-Registered equivalence wire-symmetric (the bytes are identical) and policy-differentiated (consumer policy weights by attester source). The substrate is source-neutral; CIRIS today operates registered-only. The wire-compatible path for sovereign partners is in place.
- **Chief Values Officer / certification body / accreditation body / ISO-like body shapes are operator-organisational.** They aren't runtime partner roles; the agent observes them only when their action arrives as a signed Wise Authority certificate.
- **Federation citation by ID is post-2.9.4.** Same trace-vs.-wire boundary as D11, D13, D14, D15; Registry-side `evidence_refs.dimensions = ["D19"]` lands with the upstream substrate work.
- **Partner-role-domain join on Accord invocation.** Today the kill-switch checks ROOT/AUTHORITY but doesn't yet enforce that a FINANCIAL-licensed AUTHORITY can only invoke against a FINANCIAL incident. Closure depends on Registry exposing partner-role-domain bindings and the routing layer consuming them.
- **Periodic partner-role re-attestation.** Drift or role change is caught at the next certificate refresh; the upstream temporal-drift detector is the cross-deployment backstop.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
