"""
Common type aliases for CIRIS schemas.

These provide type safety while maintaining flexibility for dynamic data.
Replaces unconstrained Dict[str, Any] usage with well-defined types.
"""

from typing import Dict, List, Union

# Configuration values - recursive union for nested config structures
ConfigValue = Union[str, int, float, bool, List["ConfigValue"], Dict[str, "ConfigValue"]]
ConfigDict = Dict[str, ConfigValue]

# JSON-compatible types - ensures serializability
JSONValue = Union[str, int, float, bool, None, List["JSONValue"], Dict[str, "JSONValue"]]
JSONDict = Dict[str, JSONValue]
JSONList = List[JSONValue]

# Event data - structured event payloads
EventValue = Union[str, int, float, bool, List[str], Dict[str, str]]
EventData = Dict[str, EventValue]

# OAuth provider data - third-party OAuth responses
OAuthValue = Union[str, int, bool, List[str], None]
OAuthData = Dict[str, OAuthValue]

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
]
