"""
API routes module.

Export all route modules for easy import.
"""

# Import all route modules
from . import (
    agent,
    audit,
    auth,
    billing,
    config,
    consent,
    dsar,
    emergency,
    memory,
    partnership,
    system,
    system_extensions,
    telemetry,
    transparency,
    users,
    wa,
)

__all__ = [
    "agent",
    "audit",
    "auth",
    "billing",
    "config",
    "consent",
    "dsar",
    "emergency",
    "memory",
    "partnership",
    "system",
    "system_extensions",
    "telemetry",
    "transparency",
    "users",
    "wa",
]
