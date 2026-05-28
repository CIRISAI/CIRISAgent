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
## CIRIS-side compliance implementation

`partner_role:*` is the CIRIS Registry partner-role taxonomy: ethics boards, audit bodies, certification bodies, HRIA/AIA stewards, trusted disclosure stewards, regional intergovernmental working groups, etc. This is a **CIRISRegistry-owned dimension**; CIRISAgent's runtime surface is limited to three consumption paths:

1. Consuming registry-issued WA certificates with partner-role-shaped scopes.
2. Accepting accord-invocation events from authority partners.
3. Emitting audit traces that partner-role auditors verify.

**CIRISRegistry as the partner-role authority (the federation-level owner)**
- `MISSION.md:500` defines CIRISRegistry as the "Identity / build / license / revocation directory. Dual-region (US/EU) Rust gRPC service deployed at `*.ciris-services-1.ai`. SOC2/HIPAA/GDPR-compliant. The bootstrap node."
- Partner-role attestation is structurally a CIRISRegistry artifact; the agent receives only the resolved license + WA certificate.
- Per `MISSION.md:486-510` the federation has "more named pieces than fit cleanly in a table" — the partner-role taxonomy is one of those moving pieces.

**WACertificate.role (the closest agent-side primitive)**
- `ciris_engine/logic/services/governance/wise_authority/README.md:44-62` defines `WARole = {ROOT, AUTHORITY, OBSERVER}`.
- The role hierarchy is a coarse 3-bucket approximation of partner-role taxonomy — sufficient for runtime authorization decisions, but not for the 19-distinct-roles IEEE taxonomy or ASEAN's regional-intergovernmental-working-group dual remit.
- `WACertificate` carries `wa_id` (format `wa-YYYY-MM-DD-XXXXXX`), `pubkey` (Ed25519), `jwt_kid`, and `scopes_json`; the partner-role-shaped attributes live in `scopes_json` as registry-issued metadata.

**Accord invocation as authority-partner kill switch**
- `ciris_engine/logic/buses/wise_bus.py:321-` `handle_accord_invocation()` validates that the signing WA has ROOT or AUTHORITY role (`wise_bus.py:371-376`); only authority-partner WAs can trigger constitutional kill.
- This is the agent's runtime hook to IEEE's "trusted_disclosure_steward" / "Chief Values Officer" partner-role shapes.
- The Ed25519 signature requirement (`wise_bus.py:378-401`) is the cryptographic binding that gives partner-role attestation its evidentiary basis.

**`DomainCategory` as partial partner-role specialization slot**
- `ciris_engine/schemas/services/agent_credits.py:38-51` `DomainCategory = {MEDICAL | FINANCIAL | LEGAL | HOME_SECURITY | IDENTITY_VERIFICATION | CONTENT_MODERATION | RESEARCH | INFRASTRUCTURE_CONTROL}` is the agent's licensed-domain enum.
- A WA service advertising `supported_domains=[MEDICAL]` is the runtime expression of "registered medical partner"; the agent uses domain_hint to route deferrals to the correct partner.
- This is partner-role taxonomy at the domain-specialization granularity, not the institutional-shape granularity. A medical-licensed `partner_role:audit_body` and a medical-licensed `partner_role:certification_body` look identical from the agent's perspective today.

**Adapter manifest declaration (the runtime peer-partner record)**
- Per `CLAUDE.md` § "Adapter Development", every adapter ships a `manifest.json` declaring its capabilities.
- Adapters are the closest thing to a partner-role at runtime; their manifest is the agent-side trace that "this peer has this declared partner shape."
- Reference implementations at `ciris_adapters/sample_adapter/`, `ciris_adapters/home_assistant/`, `ciris_adapters/wallet/` (the wallet example uses `dma_guidance=ToolDMAGuidance(requires_approval=True)` — the partner-role financial-tool gate).

**WA scopes_json (the per-partner scope-of-authority record)**
- `ciris_engine/logic/services/governance/wise_authority/README.md:53` `scopes_json: str  # JSON array of permitted scopes`.
- This carries the per-partner WA's scope of authority as registry-issued metadata.
- The agent enforces but does not author scopes_json; it is the Registry's per-partner attestation that the agent runs against.

**Test coverage**
- WA-cert + scope validation in `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`.
- Partner-domain routing in `tests/logic/buses/test_wise_bus_safe_domains.py`.
- Bus prohibition validation at registration time in `tests/test_wise_bus_deferrals.py`.
- JWT auth + role checks in `tests/adapters/api/test_jwt_auth.py`.

Proposed pointer (from seed): `CIRISRegistry partner role registry` — confirmed; primary owner is the Registry, agent runtime consumes resolved certificates only.

## Observability hooks

- **Audit chain on partner role usage** — every guidance / deferral / accord-invocation event from a partner-role WA is signed into the audit chain via `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`). Downstream verifier queries the chain to confirm "this action was authorized by a partner with role X."
- **`_validate_wa_capabilities_at_registration()`** (per `MISSION.md:132-138`) — every partner-role WA registration is validated against the 22-category prohibition table. Misconfigured or compromised partners cannot enter the registry at runtime; the validation event is logged.
- **`get_pending_deferrals(wa_id)` (per-partner deferral queue)** — `ciris_engine/logic/services/governance/wise_authority/README.md:139-143`; each partner-role WA can be queried for their pending deferrals, giving per-partner operational observability.
- **Live-lens trace stream carries partner-role provenance** — when `--live-lens` is on, every guidance response in `accord-batch-*.json` carries the WA signature and (where available) the partner-role context. The wa_id is the per-partner identifier.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D19"]` will be emitted by CIRISRegistry on partner-role attestations, not by the agent. Agent-side contribution is the audit-chain trace that "the partner-role-X action took place"; registry-side claim is "the partner has role X."
- **F-3 detector adjacency** — D02 integrity:* family and D05 detection:* family in CIRISLens jointly verify that partner roles are not silently shifted post-registration; agent emits the data, lens correlates.

## Known gaps / not-yet-implemented

- **No `partner_role:{role}` enum on the agent side.** Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.9` as `partner_role:{role}` with enum: `COMMUNITY` / `COMMUNITY_PLUS` / `PROFESSIONAL_MEDICAL` / `PROFESSIONAL_LEGAL` / `PROFESSIONAL_FINANCIAL` / `PROFESSIONAL_FULL` (citing `CLAUDE.md` "License Types"). IEEE's 19 distinct values (Chief Values Officer, ethics committees, certification bodies, …) compose via the `PROFESSIONAL_*` enum + co-owned `licensure:{authority_id}` (FSD-002 §3.9, §3.2 — co-owned with Verify per §13.3). Agent consumes via WACertificate + `LookupPartner` (FSD-002 §7.7 endpoint shape, line 1397) once Registry exposes the taxonomy. Today this surface is implicit / WARole is a 3-element approximation. **Substrate-gated, not absent.**
- **Substrate gate: CIRISRegistry partner-role registry.** Closure depends on the Registry exposing the partner-role taxonomy with per-role attestation chain. The `RegisterPartner` endpoint (FSD-002 line 1418) writes `scores` attestations on `partner_role:{role}`, `licensure:{authority}`, `bond_posted:{currency}` per partner request. Per `MISSION.md:500` Registry is Rust gRPC, dual-region, SOC2/HIPAA/GDPR-compliant.
- **Substrate gate: T3-07 `partner_role:trusted_disclosure_steward:{authority}` (IEEE-reinforced).** Closest substrate primitive is `partner_role:{role}` extended via `delegates_to` authority-source claims (FSD-002 §2.2.1 v1.3 pattern — a constitutional or framework claim names its source-of-authority by emitting `delegates_to` against an `attested_key_id` representing the framework, with `delegated_scope` naming the principle). T3-07 v1.5+ candidate uses this pattern to bind a steward role to an authority pointer; depends on Registry exposing both the steward role and the authority pointer chain.
- **Substrate gate: T3-08 `partner_role:regional_intergovernmental_working_group_dual_remit` (ASEAN-reinforced).** ASEAN Working Group on AI Governance composes via `partner_role:{role}` + `multilateral_participation:{forum}:{kind}` (FSD-002 §3.9 — `{forum}` ∈ named federated body, `{kind}` ∈ `membership` | `voting` | `proposal_filing` | `observer_status`). Dual-remit is the joint claim across both prefixes; Registry-side schema work pending. CIRISAgent has no concept of "dual remit" today.
- **Sovereign vs Registered equivalence.** Substrate-specced in FSD-002 §6.4 — Sovereign-Registered equivalence is wire-symmetric (a Sovereign agent scoring `licensure:CA_medical_board: +1.0` is wire-format identical to a Registry-steward scoring the same) and policy-differentiated. Consumer policy weights by attester source; the substrate is source-neutral. This means partner_role attestations can be emitted by either sovereign or registered agents; CIRIS today is registered-only.
- **No agent-side `Chief Values Officer` / `certification body` / `accreditation body` / `ISO-like body` shape.** These are operator-organizational roles, not runtime partner roles. Agent observes them only when their action arrives as a signed WA certificate.
- **No federation-wire emission of D19 by id.** Agent emits per-event audit data; Registry-side `evidence_refs.dimensions = ["D19"]` join on partner attestations is downstream substrate work (post-2.9.4).
- **`WiseBus.handle_accord_invocation` checks ROOT/AUTHORITY but not partner-role specialization.** A FINANCIAL-licensed AUTHORITY WA could in principle trigger an accord invocation about a MEDICAL incident; today no partner-role-domain join is enforced beyond the ROOT/AUTHORITY gate. Closure depends on the Registry exposing partner-role-domain bindings + WiseBus consuming them.
- **No partner-role attestation refresh.** Once a partner-role WA is registered, the agent does not re-attest its role periodically. Drift / role change is caught only at next certificate refresh; CIRISLens RATCHET temporal-drift detector is the off-agent backstop.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
