"""
Common type aliases for CIRIS schemas.

MIGRATION NOTE: This file is being phased out in favor of concrete Pydantic models.
Only JSON serialization and configuration types remain as type aliases.
For all other use cases, import the concrete model from its specific schema module.

Type Alias Replacements:
- EventData → Use ciris_engine.schemas.audit.core.AuditEventData
- OAuthData → Use ciris_engine.schemas.infrastructure.oauth.OAuthTokenResponse or related models
- ToolParameters → Use ciris_engine.schemas.tools.Tool.parameters (dict[str, ToolParameter])
- ActionParameters → Use specific action param models from ciris_engine.schemas.actions.parameters
- FilterConfig → Use ciris_engine.schemas.services.filters_core.FilterConfig
- JSONDict → Use ciris_engine.schemas.services.graph/attributes.JSONDict
- IdentityData → Use ciris_engine.schemas.infrastructure.identity_variance.IdentitySnapshot
- StepData → Use ciris_engine.schemas.processors.state.StepContext or ProcessingContext
"""

from typing import Any, Dict, List, Union

# JSON-compatible types - for serialization/deserialization ONLY
# These are intentionally flexible for JSON I/O boundaries
JSONValue = Union[str, int, float, bool, None, List[Any], Dict[str, Any]]
JSONDict = Dict[str, JSONValue]
JSONList = List[JSONValue]

# Configuration values - for flexible configuration loading ONLY
# These are intentionally flexible for config file parsing
ConfigValue = Union[str, int, float, bool, List[Any], Dict[str, Any]]
ConfigDict = Dict[str, ConfigValue]

# DEPRECATED ALIASES - Do not use in new code, use concrete models instead
# These exist temporarily for backwards compatibility during migration

# SerializedModel represents Pydantic model.model_dump() output
# Prefer: Use the actual Pydantic model type instead of dict
SerializedModel = Dict[str, Any]

# Export only the core type aliases still in use
__all__ = [
    "ConfigValue",
    "ConfigDict",
    "JSONValue",
    "JSONDict",
    "JSONList",
    "SerializedModel",  # Deprecated, for backwards compat only
]
