"""Infrastructure service protocols."""

from .authentication import AuthenticationServiceProtocol
from .database_maintenance import DatabaseMaintenanceServiceProtocol
from .ingress_auth import IngressAuthProviderProtocol, IngressUser
from .resource_monitor import ResourceMonitorServiceProtocol

__all__ = [
    "AuthenticationServiceProtocol",
    "IngressAuthProviderProtocol",
    "IngressUser",
    "ResourceMonitorServiceProtocol",
    "DatabaseMaintenanceServiceProtocol",
]
