"""
Graph service schemas.

Provides strongly-typed schemas for all graph service operations.
"""

from ciris_engine.schemas.services.graph.attributes import (
    AnyNodeAttributes,
    ConfigNodeAttributes,
    JSONDict,
    MemoryNodeAttributes,
    TelemetryNodeAttributes,
    create_node_attributes,
)

__all__ = [
    # Node attributes
    "JSONDict",
    "MemoryNodeAttributes",
    "ConfigNodeAttributes",
    "TelemetryNodeAttributes",
    "AnyNodeAttributes",
    "create_node_attributes",
]
