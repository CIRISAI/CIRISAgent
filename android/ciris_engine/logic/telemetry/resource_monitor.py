# This module has been moved to services/infrastructure/resource_monitor.py
# NO BACKWARDS COMPATIBILITY - Update your imports immediately

from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService as ResourceMonitor
from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceSignalBus

__all__ = ["ResourceMonitor", "ResourceSignalBus"]
