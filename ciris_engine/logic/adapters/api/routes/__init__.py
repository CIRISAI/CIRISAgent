"""
API routes module.

Export all route modules for easy import.
"""

# Import all route modules
from . import agent, audit, auth, billing, config, emergency, memory, system, system_extensions, telemetry, users, wa

__all__ = [
    "agent",
    "audit",
    "auth",
    "billing",
    "config",
    "emergency",
    "memory",
    "system",
    "system_extensions",
    "telemetry",
    "users",
    "wa",
]
