"""
TSDB Consolidation Service Module.

This module consolidates telemetry and graph data into 6-hour summaries
for long-term memory retention.

Components:
- service.py: Main service class and lifecycle management
- consolidators/: Individual consolidation strategies by data type
- edge_manager.py: Proper edge creation and management
- query_manager.py: Querying nodes and correlations for consolidation
- period_manager.py: Time period calculations and management
"""

from .service import TSDBConsolidationService

__all__ = ["TSDBConsolidationService"]
