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
## CIRIS-side compliance implementation

`credits:*` is partially implemented in CIRIS as the Commons Credits subsystem — schemas exist for the substrate-building recognition layer, but the run-time emission and enforcement loop (per FSD/COMMONS_CREDITS.md) is staged behind the CIRISBilling / CIRISNodeCore surface. The schema declaration is explicit: Commons Credits are "NOT tokens, NOT currency, NOT on-chain. They are recognition — 'giving someone credit' not 'credit card'." (`agent_credits.py:3-9`).

- **Code references** — Commons Credits schemas (the substrate-recognition data model):
    - `ciris_engine/schemas/services/agent_credits.py:1-19` — module docstring declaring Commons Credits semantics
    - `ciris_engine/schemas/services/agent_credits.py:29` — `InteractionOutcome` enum
    - `ciris_engine/schemas/services/agent_credits.py:38` — `DomainCategory` enum (MEDICAL, FINANCIAL, etc.)
    - `ciris_engine/schemas/services/agent_credits.py:54` — `DualSignature` (Ed25519 + ML-DSA-65)
    - `ciris_engine/schemas/services/agent_credits.py:75` — `GratitudeSignal` (the substrate-building gratitude record)
    - `ciris_engine/schemas/services/agent_credits.py:102` — `CreditRecord` (signed bilateral interaction attestation; deterministic interaction_id via `sha256(sorted(trace_a, trace_b))[:16]`)
    - `ciris_engine/schemas/services/agent_credits.py:169` — `compute_interaction_id` (deterministic ID computation)
    - `ciris_engine/schemas/services/agent_credits.py:180` — `AgentCreditSummary` (reputation/governance-weight summary — k_eff diversity + total_interactions + average_coherence)
    - `ciris_engine/schemas/services/agent_credits.py:226` — `CreditGenerationPolicy`
    - `ciris_engine/schemas/services/agent_credits.py:287` — `DomainDeferralRequired`
    - `ciris_engine/schemas/services/agent_credits.py:307` — `CreditRecordBatch`
- **Code references** — Credit gate (the runtime credit-check surface):
    - `ciris_engine/schemas/services/credit_gate.py:11` — `CreditAccount`
    - `ciris_engine/schemas/services/credit_gate.py:30` — `CreditContext`
    - `ciris_engine/schemas/services/credit_gate.py:45` — `CreditCheckResult`
    - `ciris_engine/schemas/services/credit_gate.py:70` — `CreditSpendRequest`, `:81` — `CreditSpendResult`
- **Code references** — Credit provider implementations:
    - `ciris_engine/logic/services/infrastructure/resource_monitor/ciris_billing_provider.py` — CIRISBilling-backed credit provider
    - `ciris_engine/logic/services/infrastructure/resource_monitor/simple_credit_provider.py` — local fallback provider
    - `ciris_engine/logic/services/infrastructure/resource_monitor/README.md` — credit-provider design notes
- **Code references** — Credit usage in WiseBus / DMA chain:
    - `ciris_engine/logic/buses/wise_bus.py:15` — imports `DomainCategory`, `DomainDeferralRequired` from agent_credits
    - `ciris_engine/logic/dma/dsaspdma.py:27` — imports `DomainCategory`; routes domain-licensed thoughts through credit-checked deferral
- **Code references** — Adapter integration:
    - `ciris_engine/logic/adapters/api/routes/_common.py` — credit-related route helpers
    - `ciris_engine/logic/adapters/base_observer.py` — credit gate in adapter base
- **Code references** — Billing API surface (CIRISBilling proxy):
    - `ciris_engine/logic/adapters/api/routes/billing.py:30` — `router = APIRouter(prefix="/api/billing")` (proxies to billing.ciris.ai)
    - `:580` — `GET /api/billing/credits`
    - `:650` — `POST /api/billing/purchase/initiate`
    - `:723` — `GET /api/billing/purchase/status/{payment_id}`
    - `:801` — `GET /api/billing/transactions`
    - `:906` — `POST /api/billing/google-play/verify`
- **Code references** — Test surface:
    - `tests/test_agent_credits.py` — agent-credits schema tests
    - `tests/test_credit_enforcement_debug.py` — credit-enforcement debugging tests
    - `tests/adapters/api/test_agent_credit_gate.py` — credit-gate adapter integration tests
- **Policy text**:
    - `FSD/COMMONS_CREDITS.md` — full Commons Credits specification (the canonical credit:* doctrine)
    - `ciris_engine/schemas/services/agent_credits.py:1-19` — explicit declaration: NOT tokens, NOT currency, NOT on-chain. Recognition only.
    - `ciris_engine/schemas/services/agent_credits.py:15-16` — k_eff (effective diversity) explicitly cited as core quality measurement from CCA paper (Zenodo 18217688)
    - USDC wallet adapter (`ciris_adapters/wallet/`) is *explicitly separate* from Commons Credits — for paying for services only (see `agent_credits.py:14`)

Proposed pointer (from seed): `CIRISBilling Commons Credits + CIRIS_COMPREHENSIVE_GUIDE 'Commons Credits' section`

## Observability hooks

- **Credit-balance endpoint**: `GET /api/billing/credits` exposes the agent's current credit summary (proxied from CIRISBilling).
- **Credit-transaction history**: `GET /api/billing/transactions` for audit.
- **CreditRecord attestations**: each bilateral interaction emits a dual-signed `CreditRecord` with deterministic interaction_id; offline-verifiable via Ed25519 + ML-DSA-65.
- **AgentCreditSummary k_eff observability**: the diversity scalar links D25 to D21 (progress measure) and D16 (method discipline).
- **Federation evidence_refs**: a Contribution citing `dimensions: ["D25"]` resolves through this seed to MH labor-as-substrate-building, EU §1.6 AI-literacy-as-substrate, IEEE Ch8+Ch9 human-capability contribution recognition.

Proposed pointer (from seed): `(none specified in seed; please fill)`

## Known gaps / not-yet-implemented

- **CIRISBilling integration is partial in CIRISAgent**: the schemas exist and the API proxy routes exist, but full end-to-end CreditRecord generation and substrate-building attestation flow is gated behind the CIRISBilling deployment (separate repo / service). In the agent runtime today, credits are enforced via `simple_credit_provider` as a fallback when the billing service is unreachable.
- **No `credits:{subject}:substrate_building` wire-form emission**: CreditRecords are generated as bilateral-interaction attestations, but the substrate-building *subject* (e.g., `credits:digital_literacy:substrate_building` per EU mapping) is not currently tagged on the record. Substrate-building intent is implicit in the interaction outcome, not declared.
- **Gratitude signal is optional and rarely emitted**: the `GratitudeSignal` model exists at `agent_credits.py:75` but adapters do not yet generate gratitude signals automatically. The "Signalling Gratitude" (the 'S' in CIRIS) is structurally present but operationally thin.
- **No intergenerational-credit attestation (MH-distinctive)**: MH's "intergenerational credit" framing has no direct CIRIS analogue.
- **AI-literacy-credit (EU §1.6)**: not implemented; CIRISAgent does not currently attest user AI-literacy gains as substrate-building credits.
- **Participatory-design credits (IEEE Ch8+Ch9)**: not currently emitted — contributors to the CIRIS codebase are not minted as credit holders by the runtime.
- **ASEAN absent_batch** is structural (credit framing implicit in §D workforce-upskilling rather than wire-attested).
- **Node attestation gap**: `CreditRecord.node_attestation` field exists but the CIRISNode (or Veilid WA consensus) signing surface is upstream — not yet implemented in CIRISAgent runtime.
<!-- END HUMAN -->
