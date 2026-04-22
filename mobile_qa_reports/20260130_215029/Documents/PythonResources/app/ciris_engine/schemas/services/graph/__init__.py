"""
Graph service schemas.

Provides strongly-typed schemas for all graph service operations.
"""

from ciris_engine.schemas.services.graph.attributes import (
    AnyNodeAttributes,
    ConfigNodeAttributes,
    LogNodeAttributes,
    MemoryNodeAttributes,
    NodeAttributesBase,
    TelemetryNodeAttributes,
    create_node_attributes,
)

__all__ = [
    # Node attributes
    "NodeAttributesBase",
    "MemoryNodeAttributes",
    "ConfigNodeAttributes",
    "TelemetryNodeAttributes",
    "LogNodeAttributes",
    "AnyNodeAttributes",
    "create_node_attributes",
]
