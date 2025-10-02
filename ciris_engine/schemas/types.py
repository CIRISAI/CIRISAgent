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
# Structured data from epistemic faculties (ethical, common sense, domain-specific)
EpistemicData = Dict[str, Union[str, int, float, bool, List[str], None]]

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
]
