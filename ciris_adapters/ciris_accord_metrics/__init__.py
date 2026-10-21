"""
CIRIS Accord Metrics Adapter — the reasoning-observability spine.

2.9.6+ (CIRISAgent#866 LensCore fold): this adapter is REQUIRED and always
loaded at bootstrap (runtime/bootstrap_helpers.py), like ciris_verify — an
agent that cannot witness its own reasoning is non-conformant, not merely
unconfigured. The trace-emit pipeline is orchestrated by the ciris-lens-core
substrate (LensClient: capture → seal → Ed25519-sign → receive_and_persist),
composing against the required persist Engine + edge runtime (both block
boot in their own init paths).

CONSENT MODEL (the load-bearing distinction):
1. Capture is constitutive — traces are the agent's local self-witness
   ledger (CEG cohort_scope: self), like the audit trail. Nobody opts in
   to having an audit trail.
2. Consent governs SHARING and is a CEG WIRE ARTIFACT, not config: the
   accord-traces opt-in writes a `consent:community_trust:v1` grant
   attestation (the CEG promotion event self → community — agreement to
   share with the canonical CIRIS community + trusted peers advertising
   `observer`); revocation writes withdraws/recants. lens-core's gate
   resolves that dimension (newest-wins) at EVERY seal — a recant is a
   hard stop config cannot override. The CIRIS_ACCORD_METRICS_CONSENT*
   env vars survive only as a QA-runner override.

Example importing for custom usage:
    from ciris_adapters.ciris_accord_metrics import (
        Adapter,  # BaseAdapterProtocol-compliant wrapper
        AccordMetricsAdapter,
        AccordMetricsService,
    )
"""

from .adapter import AccordMetricsAdapter
from .services import AccordMetricsService, TraceDetailLevel

# Export as Adapter for load_adapter() compatibility
Adapter = AccordMetricsAdapter

__all__ = [
    "Adapter",  # Primary export for dynamic loading
    "AccordMetricsAdapter",
    "AccordMetricsService",
    "TraceDetailLevel",
]
