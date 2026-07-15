"""
TSDB Consolidation Service Module.

Thin cadence-caller over the persist substrate's consolidators
(`Engine.tsdb_consolidate_*` / `telemetry_consolidate_period` /
`tsdb_prune_summaries`). All consolidation compute is substrate-owned.

Components:
- service.py: Cadence loop + substrate calls
- period_manager.py: 6h period boundary math
- date_calculation_helpers.py: weekly/monthly window + retention math
"""

from .service import TSDBConsolidationService

__all__ = ["TSDBConsolidationService"]
