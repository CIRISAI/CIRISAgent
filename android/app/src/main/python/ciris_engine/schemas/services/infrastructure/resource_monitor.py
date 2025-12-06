"""
Schemas for Resource Monitor Service.

Re-exports resource monitoring schemas from resources_core for proper
directory alignment.
"""

# ResourceUsage is in runtime.resources, not resources_core
from ciris_engine.schemas.runtime.resources import ResourceUsage

# Re-export from resources_core to maintain clean directory structure
from ciris_engine.schemas.services.resources_core import ResourceAction, ResourceBudget, ResourceLimit, ResourceSnapshot

__all__ = [
    "ResourceAction",
    "ResourceBudget",
    "ResourceLimit",
    "ResourceSnapshot",
    "ResourceUsage",
]
