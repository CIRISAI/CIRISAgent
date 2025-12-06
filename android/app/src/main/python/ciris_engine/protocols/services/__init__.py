"""Service protocols package - organized by functional area."""

# Re-export base protocols from runtime
from ..runtime.base import CoreServiceProtocol, GraphServiceProtocol, ServiceProtocol
from ..runtime.base import VisibilityServiceProtocol as BaseVisibilityServiceProtocol

# Backward compatibility alias
Service = ServiceProtocol

# Adaptation service protocols - self-improvement
from .adaptation import SelfObservationServiceProtocol

# Governance service protocols - security and oversight
from .governance import AdaptiveFilterServiceProtocol
from .governance import CommunicationServiceProtocol as CommunicationService
from .governance import VisibilityServiceProtocol
from .governance import WiseAuthorityServiceProtocol as WiseAuthorityService

# Graph service protocols - data persistence layer
from .graph import AuditServiceProtocol as AuditService
from .graph import GraphConfigServiceProtocol as ConfigService
from .graph import MemoryServiceProtocol as MemoryService
from .graph import TelemetryServiceProtocol as TelemetryService

# Infrastructure service protocols
from .infrastructure import AuthenticationServiceProtocol

# Lifecycle service protocols - system state management
from .lifecycle import (
    InitializationServiceProtocol,
    ShutdownServiceProtocol,
    TaskSchedulerServiceProtocol,
    TimeServiceProtocol,
)

# Runtime service protocols - core operations
from .runtime import LLMServiceProtocol as LLMService
from .runtime import RuntimeControlServiceProtocol as RuntimeControlService
from .runtime import SecretsServiceProtocol as SecretsService
from .runtime import ToolServiceProtocol as ToolService


# Legacy protocol for compatibility
class GraphMemoryServiceProtocol(ServiceProtocol):
    """Legacy protocol for graph memory service operations."""


__all__ = [
    # Base protocols
    "Service",
    "ServiceProtocol",
    "GraphServiceProtocol",
    "CoreServiceProtocol",
    "BaseVisibilityServiceProtocol",
    # Graph services (5)
    "MemoryService",
    "AuditService",
    "TelemetryService",
    "ConfigService",
    # Runtime services (4)
    "LLMService",
    "ToolService",
    "SecretsService",
    "RuntimeControlService",
    # Lifecycle services (4)
    "TimeServiceProtocol",
    "ShutdownServiceProtocol",
    "InitializationServiceProtocol",
    "TaskSchedulerServiceProtocol",
    # Governance services (5)
    "AuthenticationServiceProtocol",
    "WiseAuthorityService",
    "VisibilityServiceProtocol",
    "AdaptiveFilterServiceProtocol",
    "CommunicationService",
    # Adaptation services (1)
    "SelfObservationServiceProtocol",
    # Legacy
    "GraphMemoryServiceProtocol",
]
