# D11 — `multilateral_participation:{forum}:{kind}` (STRONG-4)

> v1.3 closure for federation participation in external multilateral processes

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D11` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: integrity
**Attestation density**: MH=13 · EU=3 · IEEE=10 · ASEAN=11 · total=37

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§200-203 + 224-227 (8 MH attestations)*
    > "UN-system reform advocacy; cyber-norms diplomacy"
    Wire form: `multilateral_participation:un_system:reform_advocacy + multilateral_participation:cyber_norms:shared_regulations`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§A + §C*
    > "European Parliament resolution support; UN human rights treaties"
    Wire form: `multilateral_participation:european_parliament:resolution_support + multilateral_participation:un_human_rights_treaties:legal_binding`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch10*
    > "international R&D collaboration; cross-border policy exchange"
    Wire form: `multilateral_participation:international_rd_collaboration:standards_setting + multilateral_participation:cross_border_policy_exchange:knowledge_sharing`
- **ASEAN** (ASEAN Guide on AI Governance and Ethics) — *§E (11 distinct :asean:{kind} envelopes — densest single-forum exercise in federation mapping history)*
    > "ASEAN-internal coordination + working-group membership + framework drafting + governance evolution"
    Wire form: `multilateral_participation:asean:{11 distinct kinds}`

## Wire primitives

- `multilateral_participation:{forum}:{kind}`

## Convergence note

ASEAN's 11-{kind} saturation under a single forum is the first stress test showing the {kind} slot scales gracefully.

---

<!-- BEGIN HUMAN -->
## CIRIS-side compliance implementation

`multilateral_participation:{forum}:{kind}` is a **federation-substrate-gated dimension**. CIRISAgent is a single node in the federation (`MISSION.md:472-510`); participation in external multilateral forums (UN, EU Parliament, ASEAN working groups, IEEE international R&D collaboration, etc.) is not an agent runtime capability — it is a CIRISRegistry partner-role attribute attached to the deploying organization. The agent's role is limited to four surfaces:

1. Federation peer membership (the trace contribution that gives the operator's multilateral claim its evidentiary basis).
2. License / jurisdiction metadata consumption (the agent observes its WA-cert scope, including jurisdictional binding).
3. DSAR ticket externalization (one concrete multilateral kind: GDPR / regional data-rights frameworks operationalized at runtime).
4. Accord binding (the agent's normative text the federation ratifies against).

**Federation peer membership (the substrate that admits participation)**
- The agent ships signed traces to CIRISLens and a CIRISPersist chain, holds a CIRISRegistry-issued license, and is bound by `ACCORD.md`.
- `MISSION.md:494-505` enumerates the peers: CIRISRegistry, CIRISLens, CIRISPersist, CIRISVerify, CIRISBridge, CIRISManager, CIRISNode, CIRISPortal.
- Multilateral participation as a wire-primitive is the registry-side claim that the agent's *operator* is engaged in a named external forum; the agent contributes the trace corpus that gives the claim evidentiary weight.

**License / jurisdiction metadata flow**
- `ciris_engine/logic/services/governance/wise_authority/README.md:44-56` `WACertificate` carries `scopes_json` (operator-attested scope of authority) and `jwt_kid` (key identifier).
- Jurisdictional scope (EU operator, ASEAN operator) flows through here today via the operator's WA-cert metadata.
- There is no `forum` / `kind` enum on the agent side yet; the operator's jurisdictional binding is structurally implicit in the scopes_json.

**DSAR ticket externalization (one concrete multilateral kind)**
- `ciris_engine/logic/services/governance/dsar/` is the rights-request handler that operationalizes EU GDPR / ASEAN data-rights frameworks at agent runtime.
- This is the closest existing agent-side surface to `multilateral_participation:european_parliament:resolution_support` and `multilateral_participation:un_human_rights_treaties:legal_binding` (per seed regulatory_attestations).
- Per CLAUDE.md DSAR is the rights-request handler; `ciris_engine/logic/services/governance/dsar/orchestrator.py` is the per-ticket workflow.
- Signature service at `ciris_engine/logic/services/governance/dsar/signature_service.py` produces a cryptographic record of every rights-exercise, which gives multilateral attestations their per-incident evidentiary basis.

**Accord (the agent's binding to the multilateral fabric)**
- `ciris_engine/data/accord_1.2b.txt` and the polyglot accord at `ciris_engine/data/localized/accord_1.2b_POLYGLOT.txt` are the agent-side normative text the multilateral fabric ratifies against.
- `MISSION.md:472-481` and `FSD/PROOF_OF_BENEFIT_FEDERATION.md` are the federation-primitive spec; per MISSION.md:478 the N_eff independence claim (peaking at 9.51 on 17-dim constraint vectors) is the structural multilateral-participation evidence the corpus produces.

**Test coverage**
- No agent-side test directly exercises `multilateral_participation:{forum}:{kind}`.
- Closest analogue: DSAR ticket flow (`ciris_engine/logic/services/governance/dsar/orchestrator.py`) and WA-cert scope enforcement (`tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`).
- Federation trace emission is covered indirectly through audit / telemetry tests.
- Per `docs/grant/ROUND1_BASELINE_2026-04-22.md`, the agent reports 22 core services + 257 method+path routes + 10,662 collected tests at baseline — the multi-source structural-evidence corpus the federation peers cite.

Proposed pointer (from seed): `CIRISNodeCore multilateral module (pending E-4 implementation)` — confirmed; the agent does not host the multilateral-participation registry. CIRISNodeCore (NodeCore is the absorbing substrate per `MISSION.md:480-481`) and CIRISRegistry are the named owners.

Per user-memory `project_substrate_substitution_trajectory`, the substrate substitution sequence is Persist → Edge → LensCore → NodeCore; D11's E-4 multilateral module lands in step 4 (NodeCore). Today the agent is at step 0 (2.8.10 was step-0 prep).

## Observability hooks

- **Audit chain coverage (per-trace)** — the agent emits signed traces via `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`); these traces are picked up by CIRISLens (the observatory peer, `MISSION.md:498`) and contribute to the multi-source structural-evidence basis that the multilateral participation attestation cites.
- **Federation peer telemetry** — `ciris_engine/logic/services/graph/telemetry_service/` emits the per-agent operational telemetry that downstream Registry / Portal pieces use to compute participation status.
- **DSAR signature trail** — `ciris_engine/logic/services/governance/dsar/signature_service.py` produces cryptographic records of GDPR / regional-rights-framework exercises; these are the per-incident structural-evidence basis for the EU/ASEAN multilateral participation claims.
- **N_eff cross-platform constraint vector** — per `MISSION.md:478` the federation tracks N_eff independence (peaking at 9.51 on 17-dim constraint vectors); this is the macro-level RATCHET signal that multilateral participation is real (the corpus is genuinely diverse across forums), not synthetic.
- **Federation evidence_refs** — `evidence_refs.dimensions = ["D11"]` will be emitted by the CIRISRegistry side (operator-attested), not the agent. Agent-side contribution is the trace corpus the registry cites; agent does not self-attest multilateral participation.
- **RATCHET detector adjacency** — D05 cross-agent divergence (per seed) is the federation-level detector that surfaces whether agents in a given multilateral forum (e.g. EU-jurisdiction Together-AI-using fleet) are drifting from each other. Lives in CIRISLens, not the agent.

## Known gaps / not-yet-implemented

- **No agent-side `forum`/`kind` enum.** Substrate-specced in `CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.9` as `multilateral_participation:{forum}:{kind}` where `{kind}` ∈ `membership` | `voting` | `proposal_filing` | `observer_status` and `{forum}` is a named federated body or compact (e.g., `regional_health_compact`, `cross_jurisdictional_review_board`). Added v1.3 per FSD-002 §3.9. Agent consumes via WACertificate scope binding once Registry exposes the forum/kind taxonomy via license metadata; today the Python schema is absent.
- **Substrate gate: CIRISRegistry**. The partner-role / multilateral-membership registry is a Registry artifact (FSD-002 §3.9, `multilateral_participation:{forum}:{kind}` joint with `partner_role:{role}`). Per `MISSION.md:500` Registry is "Identity / build / license / revocation directory. Dual-region (US/EU) Rust gRPC service deployed at `*.ciris-services-1.ai`." Agent-side closure of D11 depends on Registry exposing the forum/kind enum and license-bound forum membership through `LookupPartner` + `RegisterPartner` (FSD-002 endpoint shapes §7.7, table at lines 1397, 1418).
- **Substrate gate: CIRISNodeCore P10 witness-set composition.** Federation-level multilateral consensus composes via `witness_diversity:{contribution_id}` (FSD-002 §3.6.3 NodeCore §2 P10; N=3 default; jurisdictional + organizational + software-stack + cell-expertise bars) — the multilateral attestation rides on whatever witness-set the Contribution carries. Cross-federation participation depth is then weighted by the §6.1.2 / §6.1.3 trust composition policies (one-hop transitive or weighted-graph EigenTrust-style). Agent will consume the witness-set composition once NodeCore P10 ships and the federation-wide P7 weighted_aggregate exposes multilateral-weighted views.
- **No federation-wire emission of D11 by id.** The trace ≠ wire contribution boundary (user-memory `feedback_trace_vs_wire_contributions`) applies: the agent ships traces, but neither the trace envelope nor the per-thought DMA result carries `evidence_refs.dimensions = ["D11"]`. This is by design — D11 is operator-attested, not agent-attested.
- **DSAR ticket flow is the only concrete forum-binding today.** EU GDPR + analogous regional data-rights frameworks are operationalized through `ciris_engine/logic/services/governance/dsar/`; the rest of the {forum} space (UN, ASEAN E-series, IEEE Ch10) is currently policy-level operator commitment, not runtime primitive.
- **No registry → agent capability injection yet.** A multilateral-participation registry record cannot today inject capabilities or restrictions into the agent's WA service domain set. The bus prohibition gate (`ciris_engine/logic/buses/wise_bus.py:166-211`) reads operator-declared `supported_domains`; it does not consult an external forum registry.
- **`cyber_norms` forum has no agent-side surface.** MH §§224-227 invokes cyber-norms diplomacy as a multilateral participation kind; the agent has no runtime hook into cyber-norms attestation flows. The closest analogue is the apophatic CYBER_OFFENSIVE prohibition (`ciris_engine/logic/buses/prohibitions.py`) — refraining from cyber-offensive capability is the agent-side contribution to cyber-norms compliance, not direct participation.
- **No federation-emit verification of operator-attested forum membership.** A misconfigured deployment could in principle claim ASEAN-jurisdiction without supporting evidence; today the agent does not cross-check the operator's claimed forum binding against actual operating jurisdiction. RATCHET-side temporal-drift detection would catch the worst cases; agent-side does not.
- **Single-key model gates multilateral participation per occurrence.** Per user-memory `project_persist_cohabitation_issues`, one runtime = one Ed25519 identity; multi-occurrence shared-task deployments (CLAUDE.md § "Multi-Occurrence Deployment Support") still share the operator identity, so multilateral participation is attested at the operator level, not the per-occurrence level. Cohabitation issues #75-78 gate 2.9.0 PyEngine runtime-per-call deadlock.
<!-- END HUMAN -->
