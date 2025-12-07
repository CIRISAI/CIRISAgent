"""
Adapter-specific schemas.

These schemas are used for adapter registration and management.
"""

from .registration import AdapterServiceRegistration
from .runtime_context import AdapterStartupContext

__all__ = [
    "AdapterServiceRegistration",
    "AdapterStartupContext",
]
