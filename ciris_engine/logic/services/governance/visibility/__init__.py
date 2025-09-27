"""
Visibility Service Module.

Provides TRACES - the "why" of agent behavior through reasoning transparency.

This is one of three observability pillars:
1. TRACES (this service) - Why decisions were made, reasoning chains
2. LOGS (AuditService) - What happened, who did it, when
3. METRICS (TelemetryService/TSDBConsolidation/ResourceMonitor) - Performance data

VisibilityService focuses exclusively on reasoning traces and decision history.
It does NOT provide service health, metrics, or general system status.
"""

from .service import VisibilityService

__all__ = ["VisibilityService"]
