"""Multi-source DSAR orchestration.

This package handles DSAR coordination across multiple data sources.

For CIRIS-only DSAR (fast path), use DSARAutomationService in consent/.
For multi-source DSAR (comprehensive), use DSAROrchestrator here.

Architecture:
- DSAROrchestrator coordinates across CIRIS + external data sources
- Uses ToolBus to discover SQL/REST/HL7 connectors
- Uses identity resolution to map users across systems
- Aggregates results into unified DSAR packages
"""

from .orchestrator import DSAROrchestrator
from .schemas import (
    DataSourceExport,
    MultiSourceDSARAccessPackage,
    MultiSourceDSARDeletionResult,
    MultiSourceDSARExportPackage,
)

__all__ = [
    "DSAROrchestrator",
    "DataSourceExport",
    "MultiSourceDSARAccessPackage",
    "MultiSourceDSARExportPackage",
    "MultiSourceDSARDeletionResult",
]
