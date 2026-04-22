"""
Adapter Configuration Service module.

Provides interactive configuration workflow management for adapters that
support discovery, OAuth authentication, and step-by-step configuration.
"""

from .service import AdapterConfigurationService, StepResult
from .session import AdapterConfigSession, SessionStatus

__all__ = [
    "AdapterConfigurationService",
    "StepResult",
    "AdapterConfigSession",
    "SessionStatus",
]
