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
    connectors,
    consent,
    dsar,
    dsar_multi_source,
    emergency,
    memory,
    partnership,
    system,
    system_extensions,
    telemetry,
    tickets,
    transparency,
    users,
    verification,
    wa,
)

__all__ = [
    "agent",
    "audit",
    "auth",
    "billing",
    "config",
    "connectors",
    "consent",
    "dsar",
    "dsar_multi_source",
    "emergency",
    "memory",
    "partnership",
    "system",
    "system_extensions",
    "telemetry",
    "tickets",
    "transparency",
    "users",
    "verification",
    "wa",
]
