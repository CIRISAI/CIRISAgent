# Mission Alignment: Unlimit Billing Module

**Meta-Goal Reference**: M-1 — Promote sustainable adaptive coherence while respecting community boundaries.

## Mission Context

The Unlimit billing module enables CIRIS deployments to honour resource stewardship agreements by
ensuring interactions are tied to the agent owner’s credit balance. It protects the wider community by
preventing unpaid utilization without entangling the ethical core of the engine with financial concerns.

## Mission Requirements

1. **Autonomy Preservation** — Billing remains optional and external so the agent can operate
   without it when financial gating is inappropriate.
2. **Transparency** — Credit decisions must be auditable, deterministic, and explainable.
3. **Stewardship** — Outbound spending must require explicit intent and transparent logging.
4. **Safety** — Balance checks default to fail-closed unless explicitly overridden.
5. **Integrity** — Identities are evaluated using typed schemas to avoid ambiguous billing records.

## Architectural Mapping

- **Schemas (WHAT)** — `BillingIdentity`, `BillingContext`, `BillingCheckResult`,
  `BillingChargeResult`, `PaymentRequest`, `InvoiceRequest`, `PayoutRequest`, and `ReportEntry`
  capture mission-critical information: who is billed, by how much, through which channel, and how
  settlements are recorded.
- **Protocols (WHO)** — `UnlimitBillingProtocol` and the AP2 tool service expose spending through
  the sanctioned `TOOL` verb while `UnlimitCommerceService` offers pay-ins, refunds, payouts, and
  reporting without polluting the core runtime.
- **Logic (HOW)** — `UnlimitBillingService` implements credit checks with caching and telemetry,
  `UnlimitCommerceService` calls Unlimit’s REST APIs with payer filtering, and
  `UnlimitBillingToolService` validates AP2 mandate chains before invoking either spending or
  invoice creation.

## Success Criteria

- Optional module can be enabled/disabled without modifying `ciris_engine`.
- Every credit denial returns a typed reason for downstream logging/auditing.
- No untyped dictionaries cross the module boundary.
- Tests demonstrate cache correctness, payer filtering, and mandate-validated payment flows
  consistent with mission goals.
