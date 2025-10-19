"""
Base class and utilities for typed graph nodes.

This module provides the foundation for type-safe graph nodes that can be
stored generically while maintaining full type information.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel

from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.services.graph_core import NodeType

T = TypeVar("T", bound="TypedGraphNode")


class TypedGraphNode(GraphNode, ABC):
    """
    Abstract base class for all typed graph nodes.

    Subclasses must implement to_graph_node() and from_graph_node()
    to handle serialization to/from generic GraphNode storage.
    """

    @abstractmethod
    def to_graph_node(self) -> GraphNode:
        """
        Convert this typed node to a generic GraphNode for storage.

        Should only include extra fields (beyond GraphNode base fields)
        in the attributes dict.
        """

    @classmethod
    @abstractmethod
    def from_graph_node(cls: Type[T], node: GraphNode) -> T:
        """
        Reconstruct a typed node from a generic GraphNode.

        Should handle deserialization of extra fields from attributes.
        """

    def _serialize_extra_fields(self, exclude_fields: Optional[List[str]] = None) -> JSONDict:
        """
        Helper to serialize only the extra fields (not in GraphNode base).

        Args:
            exclude_fields: Additional fields to exclude beyond base fields

        Returns:
            Dict of extra fields suitable for GraphNode attributes
        """
        # Base GraphNode fields to always exclude
        base_fields = {"id", "type", "scope", "attributes", "version", "updated_by", "updated_at"}

        # Add any additional exclusions
        if exclude_fields:
            base_fields.update(exclude_fields)

        # Get all fields from this model
        extra_data: JSONDict = {}
        for field_name, field_value in self.model_dump().items():
            if field_name not in base_fields and field_value is not None:
                # Handle special types
                if isinstance(field_value, datetime):
                    extra_data[field_name] = field_value.isoformat()
                elif isinstance(field_value, BaseModel):
                    extra_data[field_name] = field_value.model_dump()
                else:
                    extra_data[field_name] = field_value

        # Add type hint for deserialization
        extra_data["node_class"] = self.__class__.__name__

        return extra_data

    @classmethod
    def _deserialize_datetime(cls, value: Any) -> Optional[datetime]:
        """Helper to deserialize datetime from string."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"Cannot deserialize datetime from {type(value)}")


class NodeTypeRegistry:
    """
    Registry for typed node classes.

    Allows looking up node classes by type string for deserialization.
    """

    _registry: Dict[str, Type[TypedGraphNode]] = {}

    @classmethod
    def register(cls, node_type: str, node_class: Type[TypedGraphNode]) -> None:
        """Register a node class for a type string."""
        # Allow re-registration with the same class (for multiple keys pointing to same class)
        if node_type in cls._registry and cls._registry[node_type] != node_class:
            raise ValueError(f"Node type {node_type} already registered with a different class")

        # Validate the class has required methods
        if not hasattr(node_class, "to_graph_node"):
            raise ValueError(f"{node_class.__name__} must implement to_graph_node()")
        if not hasattr(node_class, "from_graph_node"):
            raise ValueError(f"{node_class.__name__} must implement from_graph_node()")

        cls._registry[node_type] = node_class

    @classmethod
    def get(cls, node_type: str) -> Optional[Type[TypedGraphNode]]:
        """Get a node class by type string."""
        return cls._registry.get(node_type)

    @classmethod
    def deserialize(cls, node: GraphNode) -> Union[TypedGraphNode, GraphNode]:
        """
        Deserialize a GraphNode to its typed variant if registered.

        Falls back to returning the GraphNode if type not registered.
        """
        # node.type is a NodeType enum, so we need to check both the enum value
        # and the enum name for backward compatibility
        node_type_key = node.type if isinstance(node.type, str) else node.type.value
        node_class = cls._registry.get(node_type_key)

        # Also check by enum name (e.g., "USER" for NodeType.USER)
        if not node_class and hasattr(node.type, "name"):
            node_class = cls._registry.get(node.type.name)

        # Also check by uppercase version of the enum value
        if not node_class:
            node_class = cls._registry.get(node_type_key.upper())

        if node_class:
            # Check if attributes is a dict or has a get method
            if isinstance(node.attributes, dict) or hasattr(node.attributes, "get"):
                # Check if this was serialized from a typed node
                attrs = (
                    node.attributes
                    if isinstance(node.attributes, dict)
                    else node.attributes.model_dump() if hasattr(node.attributes, "model_dump") else {}
                )
                class_name = attrs.get("node_class") if isinstance(attrs, dict) else None
                if class_name:
                    # Try to deserialize to typed node
                    try:
                        return node_class.from_graph_node(node)
                    except Exception:
                        # Fall back to generic if deserialization fails
                        pass

        return node


def register_node_type(node_type: Union[str, "NodeType"]) -> Callable[[Type[TypedGraphNode]], Type[TypedGraphNode]]:
    """
    Decorator to automatically register a node type.

    Usage:
        @register_node_type("CONFIG")
        class ConfigNode(TypedGraphNode):
            ...

        # Or using enum:
        @register_node_type(NodeType.CONFIG)
        class ConfigNode(TypedGraphNode):
            ...
    """

    def decorator(cls: Type[TypedGraphNode]) -> Type[TypedGraphNode]:
        # Handle both string and enum inputs
        if hasattr(node_type, "value") and hasattr(node_type, "name"):
            # It's an enum, register by multiple keys for flexibility
            NodeTypeRegistry.register(node_type.value, cls)  # e.g., "config"
            NodeTypeRegistry.register(node_type.name, cls)  # e.g., "CONFIG"
            NodeTypeRegistry.register(node_type.value.upper(), cls)  # e.g., "CONFIG"
        else:
            # It's a string, register as-is and also lowercase version
            NodeTypeRegistry.register(node_type, cls)
            if isinstance(node_type, str) and node_type.lower() != node_type:
                NodeTypeRegistry.register(node_type.lower(), cls)
        return cls

    return decorator
