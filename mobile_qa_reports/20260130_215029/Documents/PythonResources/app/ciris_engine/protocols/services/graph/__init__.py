"""Graph service protocols."""

from .audit import AuditServiceProtocol
from .config import GraphConfigServiceProtocol  # Alias for backward compatibility
from .config import GraphConfigServiceProtocol as ConfigServiceProtocol
from .incident_management import IncidentManagementServiceProtocol
from .memory import MemoryServiceProtocol
from .telemetry import TelemetryServiceProtocol
from .tsdb_consolidation import TSDBConsolidationServiceProtocol

__all__ = [
    "MemoryServiceProtocol",
    "AuditServiceProtocol",
    "TelemetryServiceProtocol",
    "GraphConfigServiceProtocol",
    "ConfigServiceProtocol",  # Alias
    "TSDBConsolidationServiceProtocol",
    "IncidentManagementServiceProtocol",
]
