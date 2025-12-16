"""
Adapter Service Registration Schema

Unified schema for adapter service registration that supports:
- Multiple adapters of the same type
- Hot loading/unloading
- Persistent observer keys
- Platform requirements for security-bound services
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.platform import PlatformRequirement
from ciris_engine.schemas.runtime.enums import ServiceType


@dataclass
class AdapterServiceRegistration:
    """Registration info for services provided by adapters.

    This is used by adapters to register themselves as providers of various
    service types (communication, tools, wise authority, etc.).

    Note: Observer persistence is handled by the AuthenticationService via
    the wa_cert table using the adapter's adapter_id.
    """

    service_type: ServiceType  # What type of service
    provider: Any  # The actual service instance (adapter)
    priority: Priority = Priority.NORMAL  # Registration priority
    handlers: Optional[List[str]] = None  # Specific handlers or None for global
    capabilities: List[str] = field(default_factory=list)  # What the service can do

    # Platform requirements for the entire service
    # If not satisfied, the service will not be registered
    platform_requirements: List[PlatformRequirement] = field(default_factory=list)
    platform_requirements_rationale: Optional[str] = None

    def __post_init__(self) -> None:
        # Ensure handlers is either None or a list
        if self.handlers is not None and not isinstance(self.handlers, list):
            self.handlers = [self.handlers]


__all__ = ["AdapterServiceRegistration"]
