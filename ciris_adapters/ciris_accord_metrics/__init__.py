"""
CIRIS Accord Metrics Adapter.

This adapter provides accord compliance metrics collection for CIRISLens,
reporting WBD (Wisdom-Based Deferral) events and PDMA decision events.

CRITICAL REQUIREMENTS:
1. NOT auto-loaded - Must be explicitly enabled via --adapter
2. Requires EXPLICIT consent via setup wizard
3. No data sent without consent

Usage:
    # Load the accord metrics adapter
    python main.py --adapter api --adapter ciris_accord_metrics

    # Then complete the setup wizard to grant consent

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
