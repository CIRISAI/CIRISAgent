"""Infrastructure service protocols."""

from .authentication import AuthenticationServiceProtocol
from .database_maintenance import DatabaseMaintenanceServiceProtocol
from .resource_monitor import ResourceMonitorServiceProtocol

__all__ = [
    "AuthenticationServiceProtocol",
    "ResourceMonitorServiceProtocol",
    "DatabaseMaintenanceServiceProtocol",
]
