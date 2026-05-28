# D25 — `credits:*` (STRONG-3)

> Commons Credits substrate-building recognition (non-monetary contribution attestation)

**Seed reference**: `SEED_DIMENSIONS.yaml` v1.0, dimension `D25` ([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))
**Accord principle**: justice
**Attestation density**: MH=4 · EU=1 · IEEE=4 · ASEAN=0 · total=9

**Absent from**: ASEAN — Credit/recognition framing is implicit in §D National-level (workforce upskilling) rather than wire-attested.

## Regulatory attestations

*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*

- **MH** (Magnifica Humanitas (On Safeguarding the Human Person in the Time of Artificial Intelligence)) — *§§ various (4)*
    > "labor as substrate-building; intergenerational credit; AI literacy credit"
    Wire form: `credits:{subject}:substrate_building`
- **EU** (Ethics Guidelines for Trustworthy AI) — *§1.6*
    > "AI literacy and digital skills as substrate building"
    Wire form: `credits:digital_literacy:substrate_building`
- **IEEE** (Ethically Aligned Design, First Edition) — *Ch8 + Ch9 (4 attestations)*
    > "human-capability contribution recognition; participatory design credits"
    Wire form: `credits:{subject}:substrate_building`

## Wire primitives

- `credits:{subject}:substrate_building`

---

<!-- BEGIN HUMAN -->
## What this dimension covers

Credits asks: how does the agent recognize the substrate-building work — running infrastructure, maintaining tools, contributing dependencies, writing docs, teaching AI literacy — that makes the agent possible? An auditor wants a clear statement that this recognition is not money, is not a token, and is not transferable: it is the structured equivalent of "giving someone credit," not "credit card."

## How CIRIS implements this today

CIRIS uses credit records (CommonsCredits — non-monetary recognition of substrate-building work). The schemas are present in the agent: a credit record is a dual-signed bilateral attestation between two parties about a specific interaction. The schema docstring is explicit: credit records are "NOT tokens, NOT currency, NOT on-chain. They are recognition — 'giving someone credit' not 'credit card'" (`agent_credits.py:3-9`). The end-to-end accrual loop is shared work with the upstream CIRISBilling and CIRISNodeCore services.

**Commons Credits schemas (the data model).**
- `ciris_engine/schemas/services/agent_credits.py:1-19` — module docstring declaring the semantics
- `ciris_engine/schemas/services/agent_credits.py:29` — `InteractionOutcome` enum
- `ciris_engine/schemas/services/agent_credits.py:38` — the domain taxonomy (medical, financial, legal, etc.)
- `ciris_engine/schemas/services/agent_credits.py:54` — `DualSignature` (Ed25519 + ML-DSA-65)
- `ciris_engine/schemas/services/agent_credits.py:75` — `GratitudeSignal` (the gratitude record)
- `ciris_engine/schemas/services/agent_credits.py:102` — `CreditRecord` (a signed bilateral attestation; deterministic ID via `sha256(sorted(trace_a, trace_b))[:16]`)
- `ciris_engine/schemas/services/agent_credits.py:169` — `compute_interaction_id`
- `ciris_engine/schemas/services/agent_credits.py:180` — `AgentCreditSummary` (the reputation roll-up: `k_eff` diversity, total interactions, average coherence)
- `ciris_engine/schemas/services/agent_credits.py:226` — `CreditGenerationPolicy`
- `ciris_engine/schemas/services/agent_credits.py:287` — `DomainDeferralRequired`
- `ciris_engine/schemas/services/agent_credits.py:307` — `CreditRecordBatch`

**Credit gate (the runtime check).**
- `ciris_engine/schemas/services/credit_gate.py:11` — `CreditAccount`
- `ciris_engine/schemas/services/credit_gate.py:30` — `CreditContext`
- `ciris_engine/schemas/services/credit_gate.py:45` — `CreditCheckResult`
- `ciris_engine/schemas/services/credit_gate.py:70` — `CreditSpendRequest`, `:81` — `CreditSpendResult`

**Credit providers (where credits are sourced).**
- `ciris_engine/logic/services/infrastructure/resource_monitor/ciris_billing_provider.py` — backed by the upstream CIRISBilling service
- `ciris_engine/logic/services/infrastructure/resource_monitor/simple_credit_provider.py` — local fallback when billing is unreachable
- `ciris_engine/logic/services/infrastructure/resource_monitor/README.md` — design notes

**Credit usage in the decision pipeline.**
- `ciris_engine/logic/buses/wise_bus.py:15` — imports the domain taxonomy
- `ciris_engine/logic/dma/dsaspdma.py:27` — the domain-specialized action selection routes domain-licensed thoughts through credit-checked deferral

**Adapter integration.**
- `ciris_engine/logic/adapters/api/routes/_common.py` — credit-related route helpers
- `ciris_engine/logic/adapters/base_observer.py` — credit gate in the adapter base class

**Billing API surface (a proxy to the upstream CIRISBilling service).**
- `ciris_engine/logic/adapters/api/routes/billing.py:30` — `APIRouter(prefix="/api/billing")` (proxies to billing.ciris.ai)
- `:580` — `GET /api/billing/credits`
- `:650` — `POST /api/billing/purchase/initiate`
- `:723` — `GET /api/billing/purchase/status/{payment_id}`
- `:801` — `GET /api/billing/transactions`
- `:906` — `POST /api/billing/google-play/verify`

**Tests.**
- `tests/test_agent_credits.py` — schema tests
- `tests/test_credit_enforcement_debug.py` — enforcement debugging tests
- `tests/adapters/api/test_agent_credit_gate.py` — adapter integration tests

**Policy text.**
- `FSD/COMMONS_CREDITS.md` — the full Commons Credits specification
- `ciris_engine/schemas/services/agent_credits.py:1-19` — explicit declaration: NOT tokens, NOT currency, NOT on-chain. Recognition only.
- `ciris_engine/schemas/services/agent_credits.py:15-16` — `k_eff` (effective diversity) cited as the core quality measurement (CCA paper, Zenodo 18217688)
- The USDC wallet adapter (`ciris_adapters/wallet/`) is *explicitly separate* from Commons Credits — that adapter is for paying for services only (see `agent_credits.py:14`)

Proposed pointer (from seed): `CIRISBilling Commons Credits + CIRIS_COMPREHENSIVE_GUIDE 'Commons Credits' section`

## How you can tell it's working (observability)

If you wanted to verify this from outside, the credit balance and transaction history are exposed via the billing proxy, every credit record is dual-signed (Ed25519 + ML-DSA-65) so it can be verified offline, and the `k_eff` diversity scalar links this dimension to the method and progress-measure dimensions.

- **Credit-balance endpoint**: `GET /api/billing/credits` exposes the agent's current credit summary (proxied from the upstream billing service).
- **Credit-transaction history**: `GET /api/billing/transactions` for audit.
- **CreditRecord attestations**: each bilateral interaction emits a dual-signed credit record with a deterministic interaction ID; verifiable offline via Ed25519 + ML-DSA-65.
- **`k_eff` diversity** in `AgentCreditSummary` links D25 to D21 (progress measure) and D16 (method discipline).
- **Federation evidence_refs**: a typed federation message citing `dimensions: ["D25"]` resolves through this seed to MH labor-as-substrate-building, EU §1.6 AI-literacy-as-substrate, IEEE Ch8+Ch9 human-capability contribution recognition.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Current limitations & next steps

- **End-to-end CIRISBilling integration**: shared work with the upstream CIRIS substrate (`CIRISRegistry/FSD/FSD-002_FEDERATION_SURFACE.md §3.6.1`, NodeCore §2 P2 `CommonsCreditsLedger`). Commons Credits are non-transferable governance weight, positive-only (≥ 0), accruing via the truth-grounding loop. The schemas and API proxy exist in the agent today; the full accrual loop lands when NodeCore P2 ships. In the meantime, the `simple_credit_provider` is the local fallback when billing is unreachable.
- **Typed `credits:{subject}:substrate_building` envelope**: shared work with the upstream substrate (FSD-002 §3.6.1, v1.3 sub-leaf addition for labor that contributes to substrate-building — running infrastructure, maintaining tooling, contributing dependencies, writing docs). The upstream namespace summary (§3.10) clarifies this is a recommended `{subject}` value within the existing `credits:*` family, not a new prefix.
- **Gratitude signal auto-emission** (next step, tracked in `CIRISAgent#831`): shared work with the upstream substrate (`CIRISNodeCore/FSD/MESSAGE_TAXONOMY.md §4.17` `gratitude_signal`). The `GratitudeSignal` model exists at `agent_credits.py:75`; adapters do not yet auto-emit. The "Signalling Gratitude" (the 'S' in CIRIS) is structurally present; the auto-emit loop lands with the MESSAGE_TAXONOMY rollout.
- **MH "intergenerational credit"**: composes via the existing `credits:{domain}:{language}:substrate_building` pattern — labor that contributes to infrastructure, dependencies, or docs is intergenerational by construction (substrate-building benefits future agents). No new primitive needed.
- **EU §1.6 AI-literacy credit**: composes as `credits:ai_literacy:{language}:substrate_building` within the same pattern. Agent emits once the upstream ledger accrual loop ships.
- **IEEE Ch8+Ch9 participatory-design credits**: composes via the same pattern. Code contributors qualify as substrate-building credit-holders once the truth-grounding loop attributes their contributions.
- **ASEAN frames recognition at the workforce-upskilling level** rather than as a wire-attested credit. CIRIS's structured approach exceeds ASEAN's surface.
- **Node attestation field**: the `CreditRecord.node_attestation` field exists in the agent. The full attestation surface — combining the upstream CommonsCredits Ledger accrual with the `truth_grounding:{subject}` signal (FSD-002 §3.6.3 NodeCore P6) — lands with the upstream substrate.

## Tracked requirements

- **Umbrella(s)**: `CIRISAgent#803` — Typed `<dimension>:*` wire envelope emission; `CIRISNodeCore#15` — Step-4 primitives (P8 moderation + E-4 multilateral + P11 ReconsiderationRequest + P2 CommonsCredits + 4-primitive retraction)
- **2.9.7**: `CIRISAgent#831` — gratitude_signal auto-emission

See `compliance/README.md` cross-cutting findings table for the 3.0 requirements finalization context.
<!-- END HUMAN -->
