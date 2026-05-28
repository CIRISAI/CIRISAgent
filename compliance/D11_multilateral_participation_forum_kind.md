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
## What this dimension covers

Operators of AI systems often participate in external multilateral forums — UN bodies, EU Parliament processes, ASEAN working groups, IEEE international R&D collaborations — and that participation carries weight in trustworthy-AI claims. This dimension tracks who's in which forum and what kind of seat they hold (membership, voting, proposal-filing, observer). Thirty-seven attestations across MH, EU, IEEE, and ASEAN treat multilateral engagement as a structural integrity concern; ASEAN alone exercises eleven distinct forum-kinds, the densest single-forum saturation seen so far.

## How CIRIS implements this today

This dimension is mostly carried at the operator and registry layer, not by the agent at runtime. The agent's job here is to be a credible federation peer (a single node in the federation network) whose signed reasoning corpus gives the operator's multilateral claims their evidentiary basis. Four concrete surfaces matter: federation peer membership, jurisdictional metadata on the agent's certificate, the data-subject rights workflow (one real multilateral framework operationalised at runtime), and the Accord that the federation ratifies against.

**Federation peer membership: the agent as a participating node.** The agent ships signed traces, holds a Registry-issued license, and is bound by the Accord.
- The set of federation peers is enumerated at `MISSION.md:494-505`: Registry, Lens, Persist, Verify, Bridge, Manager, Node, Portal.
- The operator's multilateral claim ("we participate in forum X") gets its evidentiary weight from the trace corpus the agent produces.

**Jurisdictional metadata on the Wise Authority certificate.** The operator's jurisdiction (EU, ASEAN, etc.) flows through the Wise Authority certificate today.
- `WACertificate` carries `scopes_json` and `jwt_kid` — see `ciris_engine/logic/services/governance/wise_authority/README.md:44-56`.
- A dedicated `forum` / `kind` enum doesn't yet exist on the agent side; jurisdiction sits inside `scopes_json` as operator-attested metadata.

**The DSAR workflow: one multilateral framework operationalised at runtime.** Data-subject access requests are the concrete agent-side surface for EU GDPR and analogous regional rights frameworks.
- The orchestrator is at `ciris_engine/logic/services/governance/dsar/orchestrator.py`; the rights-request handler is documented in CLAUDE.md.
- The signature service at `ciris_engine/logic/services/governance/dsar/signature_service.py` produces a cryptographic record of each rights exercise — the per-incident evidence base for EU and ASEAN multilateral claims.

**The Accord as the agent's binding text.** The Accord is what the multilateral fabric ratifies against.
- The canonical text lives at `ciris_engine/data/accord_1.2b.txt`; the polyglot variant is at `ciris_engine/data/localized/accord_1.2b_POLYGLOT.txt`.
- The federation primitive specification is in `MISSION.md:472-481` and `FSD/PROOF_OF_BENEFIT_FEDERATION.md`. The N_eff independence claim (peaking at 9.51 on 17-dimensional constraint vectors, `MISSION.md:478`) is the structural evidence that participation is genuinely plural.

**Tests covering this behaviour:**
- No agent test directly exercises the multilateral-participation primitive (it's operator-attested upstream).
- Closest agent-side analogues: the DSAR ticket flow (`ciris_engine/logic/services/governance/dsar/orchestrator.py`) and Wise Authority scope enforcement (`tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`).
- Federation trace emission is covered indirectly through audit and telemetry tests.
- Per `docs/grant/ROUND1_BASELINE_2026-04-22.md`, the agent reports 22 core services, 257 routes, and 10,662 tests at baseline — the structural-evidence corpus federation peers cite.

Proposed pointer (from seed): `CIRISNodeCore multilateral module (pending E-4 implementation)` — confirmed; the multilateral-participation registry lives in NodeCore (the absorbing substrate per `MISSION.md:480-481`) and Registry, not the agent.

This work sits in step 4 of the substrate substitution trajectory (the upstream CIRIS components being progressively replaced with Rust-native implementations — Persist → Edge → LensCore → NodeCore). The agent today is at step 0; 2.8.10 was step-0 prep.

## How you can tell it's working (observability)

If you want to verify the agent is contributing credibly to its operator's multilateral participation claims, here's what to check.

- **Signed trace corpus.** Every reasoning step is signed by `GraphAuditService.log_event` (`ciris_engine/logic/services/graph/audit_service/service.py:366`). The upstream observatory layer (CIRISLens, `MISSION.md:498`) picks these up; they form the evidence base operator claims cite.
- **Per-agent operational telemetry.** `ciris_engine/logic/services/graph/telemetry_service/` exposes the data Registry and Portal use to compute participation status.
- **DSAR signature trail.** `ciris_engine/logic/services/governance/dsar/signature_service.py` produces cryptographic records of each rights exercise — the per-incident evidence for EU and ASEAN claims.
- **Cross-platform independence signal.** The federation tracks N_eff independence (peaking at 9.51 on 17-dimensional constraint vectors, `MISSION.md:478`). That's the macro-level evidence that participation is genuinely plural rather than synthetic.
- **Federation citation by ID.** This dimension is operator-attested at the Registry layer, so `evidence_refs.dimensions = ["D11"]` is emitted by Registry, not by the agent. The agent contributes the trace corpus the registry cites.
- **Upstream cross-agent detection.** The cross-agent divergence detector (D05 family) catches drift between agents in a shared forum (e.g. EU-jurisdiction Together-AI-using fleet). Lives in CIRISLens.

## Current limitations & next steps

This dimension is intentionally upstream-owned. The agent already produces the evidence base; the remaining steps connect it to a forum/kind taxonomy hosted in Registry and NodeCore.

- **Forum/kind taxonomy lives upstream.** The federation surface (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.9`) defines `multilateral_participation:{forum}:{kind}` with `{kind}` ∈ `membership`, `voting`, `proposal_filing`, `observer_status` and `{forum}` a named federated body. Agent picks this up via Wise Authority certificate scope once Registry exposes the taxonomy through `LookupPartner` and `RegisterPartner` (FSD-002 §7.7, lines 1397, 1418). Shared roadmap with Registry ([CIRISRegistry#25](https://github.com/CIRISAI/CIRISRegistry/issues/25)).
- **Multilateral consensus rides on the witness set.** Federation-level multilateral consensus composes via the multi-source witness set (FSD-002 §3.6.3, NodeCore §2 P10) with the four-axis diversity bar (jurisdictional, organisational, software-stack, cell-expertise). The agent will read witness-set composition once NodeCore's P10 primitive and the P7 weighted-aggregate view ship. Shared roadmap with NodeCore ([CIRISNodeCore#15](https://github.com/CIRISAI/CIRISNodeCore/issues/15)).
- **Citation by ID is operator-attested, not agent-attested.** The agent emits structurally rich reasoning traces; the federation envelope's `evidence_refs.dimensions = ["D11"]` is added by Registry. This is the intended division of labour — same "trace vs. wire" boundary as D06 and D13.
- **DSAR is the only concrete multilateral framework operationalised at runtime today.** EU GDPR and analogous regional rights frameworks land through `ciris_engine/logic/services/governance/dsar/`. UN, ASEAN E-series, and IEEE Ch10 framings are currently policy-level operator commitments rather than runtime primitives.
- **Registry-to-agent capability injection is a future surface.** A multilateral-participation registry record cannot yet inject capabilities or restrictions into the agent's Wise Authority service domain set. The routing layer (`ciris_engine/logic/buses/wise_bus.py:166-211`) currently reads operator-declared `supported_domains` rather than an external forum registry.
- **Cyber-norms forum is currently expressed apophatically.** MH §§224-227 names cyber-norms diplomacy as a multilateral kind. The agent's contribution today is structural refusal: the CYBER_OFFENSIVE prohibition in `ciris_engine/logic/buses/prohibitions.py` is its non-participation in cyber-offensive capability — not direct cyber-norms attestation.
- **Operator-claimed jurisdiction isn't cross-checked against operating jurisdiction.** The upstream temporal-drift detector catches the worst cases; on-agent cross-check is a complementary next step.
- **Single-key model: one runtime, one identity.** Per the persist-cohabitation issue set, a runtime carries a single Ed25519 identity; multi-occurrence deployments share the operator identity, so multilateral participation is attested at the operator level. Cohabitation issues #75-78 gate the 2.9.0 PyEngine runtime-per-call work.

## Tracked requirements

- **Umbrella(s)**: `CIRISLensCore#26` — F-3 detector family per FSD-002 §3.5.3; `CIRISRegistry#25` — Federation taxonomy expansion (forum/partner_role/jurisdiction/dual_remit); `CIRISNodeCore#15` — Step-4 primitives (P8 moderation + E-4 multilateral + P11 ReconsiderationRequest + P2 CommonsCredits + 4-primitive retraction)

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
