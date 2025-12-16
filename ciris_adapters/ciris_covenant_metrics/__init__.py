"""
CIRIS Covenant Metrics Adapter.

This adapter provides covenant compliance metrics collection for CIRISLens,
reporting WBD (Wisdom-Based Deferral) events and PDMA decision events.

CRITICAL REQUIREMENTS:
1. NOT auto-loaded - Must be explicitly enabled via --adapter
2. Requires EXPLICIT consent via setup wizard
3. No data sent without consent

Usage:
    # Load the covenant metrics adapter
    python main.py --adapter api --adapter ciris_covenant_metrics

    # Then complete the setup wizard to grant consent

Example importing for custom usage:
    from ciris_adapters.ciris_covenant_metrics import (
        Adapter,  # BaseAdapterProtocol-compliant wrapper
        CovenantMetricsAdapter,
        CovenantMetricsService,
    )
"""

from .adapter import CovenantMetricsAdapter
from .services import CovenantMetricsService

# Export as Adapter for load_adapter() compatibility
Adapter = CovenantMetricsAdapter

__all__ = [
    "Adapter",  # Primary export for dynamic loading
    "CovenantMetricsAdapter",
    "CovenantMetricsService",
]
