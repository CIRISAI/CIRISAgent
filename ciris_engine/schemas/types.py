"""
Common type aliases for CIRIS schemas.

These provide type safety while maintaining flexibility for dynamic data.
Replaces unconstrained Dict[str, Any] usage with well-defined types.
"""

from typing import Any, Dict, List, Union

# Configuration values - supports nested structures
# Note: Using Any for nested values to avoid Pydantic 2.x recursion issues
# These are type hints, not runtime validation schemas
ConfigValue = Union[str, int, float, bool, List[Any], Dict[str, Any]]
ConfigDict = Dict[str, ConfigValue]

# JSON-compatible types - ensures serializability
# Note: Using Any for nested values to avoid Pydantic 2.x recursion issues
JSONValue = Union[str, int, float, bool, None, List[Any], Dict[str, Any]]
JSONDict = Dict[str, JSONValue]
JSONList = List[JSONValue]

# Event data - structured event payloads
EventValue = Union[str, int, float, bool, List[str], Dict[str, str]]
EventData = Dict[str, EventValue]

# OAuth provider data - third-party OAuth responses
OAuthValue = Union[str, int, bool, List[str], None]
OAuthData = Dict[str, OAuthValue]

# Epistemic data - conscience and faculty evaluation results
# REMOVED: Use ciris_engine.schemas.conscience.core.EpistemicData instead
# The proper Pydantic schema provides 4 structured fields:
#   - entropy_level: float
#   - coherence_level: float
#   - uncertainty_acknowledged: bool
#   - reasoning_transparency: float

# Step data - dynamic data passed between pipeline steps
# Used for step-specific parameters that get unpacked into StepResult constructors
StepData = Dict[str, Any]

# Serialized model data - Pydantic model.model_dump() output
# Represents the JSON-serializable dictionary form of a Pydantic model
SerializedModel = Dict[str, Any]

# Tool parameters - validated dict of tool execution parameters
# Flexible type that accepts any JSON-serializable parameter values
ToolParameters = Dict[str, Any]

# Action parameters - validated dict of action handler parameters
# Flexible type that accepts any JSON-serializable action values
ActionParameters = Dict[str, Any]

# Filter configuration - filter settings dictionary
# Used for adaptive filter configuration data
FilterConfig = Dict[str, Any]

# Node attributes - flexible graph node attribute dictionary
# Used for additional attributes on graph nodes beyond typed fields
NodeAttributes = Dict[str, Any]

# Identity data - complete identity snapshot data
# Used for identity variance monitoring and snapshots
IdentityData = Dict[str, Any]

# Export all type aliases
__all__ = [
    "ConfigValue",
    "ConfigDict",
    "JSONValue",
    "JSONDict",
    "JSONList",
    "EventValue",
    "EventData",
    "OAuthValue",
    "OAuthData",
    "EpistemicData",
    "StepData",
    "SerializedModel",
    "ToolParameters",
    "ActionParameters",
    "FilterConfig",
    "NodeAttributes",
    "IdentityData",
]
