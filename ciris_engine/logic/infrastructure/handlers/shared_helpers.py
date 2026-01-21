"""
Shared helper functions for action handlers.

These helpers reduce cognitive complexity by extracting common patterns
used across multiple handlers into reusable, testable functions.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional, Set, Tuple

from pydantic import BaseModel

from ciris_engine.schemas.handlers.memory_schemas import ConnectedNodeInfo, RecalledNodeInfo
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict, JSONValue

if TYPE_CHECKING:
    from ciris_engine.logic.buses import BusManager
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

# Known adapter prefixes for channel routing
KNOWN_ADAPTER_PREFIXES: FrozenSet[str] = frozenset({"api_", "discord_", "cli_", "ws:", "reddit_"})

# Managed user attributes that should not be modified by memorize operations
MANAGED_USER_ATTRIBUTES: Dict[str, str] = {
    # System-managed timestamps
    "last_seen": "System-managed timestamp updated automatically when user activity is detected. Use OBSERVE action instead.",
    "last_interaction": "System-managed timestamp updated automatically when user interacts. Use OBSERVE action instead.",
    "created_at": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
    "first_seen": "System-managed timestamp set once when user is first encountered. Cannot be modified.",
    # System-managed access control
    "trust_level": "Managed by the Adaptive Filter service based on user behavior patterns. Cannot be directly modified.",
    "is_wa": "Managed by the Authentication service. Wise Authority status requires proper authorization flow.",
    "permissions": "Managed by the Authorization service. Permission changes require administrative access.",
    "restrictions": "Managed by the Authorization service. Restriction changes require administrative access.",
    # User privacy & preference settings (user-only modification via API)
    "marketing_opt_in": "User consent for marketing communications. Only modifiable by user via settings API. Use DEFER to request user permission changes.",
    "marketing_opt_in_source": "Source of marketing consent (e.g., 'oauth_login', 'settings_page'). System-managed tracking field. Cannot be modified directly.",
    "location": "User's location preference. Only modifiable by user via settings API. Use OBSERVE to see current value.",
    "interaction_preferences": "User's custom interaction preferences and prompt. Only modifiable by user via settings API. Use OBSERVE to see current value.",
    "user_preferred_name": "User's preferred display name. Only modifiable by user via settings API. Use OBSERVE to see current value.",
    # OAuth identity fields (authentication system managed)
    "oauth_provider": "OAuth provider identity (e.g., 'google', 'github'). Managed by authentication system during OAuth flow. Use OBSERVE to see details.",
    "oauth_email": "Email address from OAuth provider. Managed by authentication system. Use OBSERVE to see email.",
    "oauth_external_id": "External user ID from OAuth provider. Managed by authentication system during OAuth flow. Cannot be modified.",
    "oauth_name": "Full name from OAuth provider. Managed by authentication system during OAuth flow. Use OBSERVE to see name.",
    "oauth_picture": "Profile picture URL from OAuth provider. Managed by authentication system during OAuth flow. Use OBSERVE to see picture URL.",
    "oauth_links": "Linked OAuth identities for this user. Managed by authentication system. Use OBSERVE to see linked accounts.",
}


# =============================================================================
# Datetime Helpers
# =============================================================================


def parse_iso_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp handling both 'Z' and '+00:00' formats.

    Args:
        timestamp_str: ISO format timestamp string or None

    Returns:
        Parsed datetime or None if input is None or invalid
    """
    if not timestamp_str:
        return None
    try:
        # Handle 'Z' suffix by converting to '+00:00'
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        return None


def parse_timestamp_to_datetime(timestamp_str: str) -> datetime:
    """Parse ISO timestamp, raising ValueError on failure.

    Args:
        timestamp_str: ISO format timestamp string

    Returns:
        Parsed datetime

    Raises:
        ValueError: If timestamp cannot be parsed
    """
    result = parse_iso_timestamp(timestamp_str)
    if result is None:
        raise ValueError(f"Invalid ISO timestamp: {timestamp_str}")
    return result


# =============================================================================
# Channel Helpers
# =============================================================================


def is_api_channel(channel_id: Optional[str]) -> bool:
    """Check if channel is an API channel (api_, ws:).

    Args:
        channel_id: Channel identifier or None

    Returns:
        True if channel is API-based, False otherwise
    """
    if not channel_id:
        return False
    return channel_id.startswith("api_") or channel_id.startswith("ws:")


def has_valid_adapter_prefix(channel_id: str) -> bool:
    """Check if channel_id has a known adapter prefix.

    Args:
        channel_id: Channel identifier

    Returns:
        True if channel has a known adapter prefix
    """
    return any(channel_id.startswith(prefix) for prefix in KNOWN_ADAPTER_PREFIXES)


# =============================================================================
# Attribute Serialization Helpers
# =============================================================================


def serialize_datetime_value(value: Any) -> JSONValue:
    """Convert datetime values to ISO strings, pass through others.

    Args:
        value: Any value that might be a datetime

    Returns:
        ISO string if datetime, original value otherwise
    """
    if isinstance(value, datetime):
        return value.isoformat()
    # Cast to JSONValue - caller is responsible for ensuring value is JSON-serializable
    result: JSONValue = value
    return result


def serialize_attributes_to_json(attributes: Any) -> JSONDict:
    """Serialize Pydantic model or dict attributes to JSON-compatible dict.

    Handles both dict and Pydantic BaseModel attributes, converting
    datetime values to ISO strings.

    Args:
        attributes: Dict or Pydantic model with attributes

    Returns:
        JSON-compatible dictionary
    """
    result: JSONDict = {}

    if isinstance(attributes, BaseModel):
        attr_dict = attributes.model_dump()
        for key, value in attr_dict.items():
            result[key] = serialize_datetime_value(value)
    elif isinstance(attributes, dict):
        for key, value in attributes.items():
            result[key] = serialize_datetime_value(value)

    return result


# =============================================================================
# Node Type Helpers
# =============================================================================


def is_user_node(node: GraphNode) -> bool:
    """Check if node is a user node.

    Args:
        node: Graph node to check

    Returns:
        True if node represents a user
    """
    return node.type == NodeType.USER or node.id.startswith("user/") or node.id.startswith("user_")


def is_identity_node(node: GraphNode) -> bool:
    """Check if node is an identity node requiring WA authorization.

    Args:
        node: Graph node to check

    Returns:
        True if node is an identity node
    """
    return node.scope == GraphScope.IDENTITY or node.id.startswith("agent/identity") or node.type == NodeType.AGENT


def is_config_node(node: GraphNode) -> bool:
    """Check if node is a CONFIG node.

    Args:
        node: Graph node to check

    Returns:
        True if node is a CONFIG node in LOCAL scope
    """
    return node.type == NodeType.CONFIG and node.scope == GraphScope.LOCAL


def extract_user_id_from_node(node: GraphNode) -> Optional[str]:
    """Extract user_id from a user node ID.

    Args:
        node: Graph node with user ID format

    Returns:
        User ID string or None if not a user node
    """
    if node.id.startswith("user/"):
        return node.id[5:]
    if node.id.startswith("user_"):
        return node.id[5:]
    return None


# =============================================================================
# Managed Attribute Helpers
# =============================================================================


def get_node_attributes_dict(node: GraphNode) -> Dict[str, Any]:
    """Get node attributes as a dictionary.

    Args:
        node: Graph node

    Returns:
        Dictionary of attributes
    """
    if not hasattr(node, "attributes") or not node.attributes:
        return {}

    if isinstance(node.attributes, dict):
        return node.attributes
    if hasattr(node.attributes, "__dict__"):
        return node.attributes.__dict__
    return {}


def check_managed_attributes(node: GraphNode) -> Optional[str]:
    """Check if node tries to modify managed attributes.

    Args:
        node: Graph node to check

    Returns:
        Error message if managed attribute found, None otherwise
    """
    if not is_user_node(node):
        return None

    attrs_to_check = get_node_attributes_dict(node)

    for attr_name, rationale in MANAGED_USER_ATTRIBUTES.items():
        if attr_name in attrs_to_check:
            return (
                f"MEMORIZE BLOCKED: Attempt to modify managed user attribute '{attr_name}'. "
                f"\n\nRationale: {rationale}"
                f"\n\nAttempted operation: Set '{attr_name}' to '{attrs_to_check[attr_name]}' for user node '{node.id}'."
                f"\n\nGuidance: If this information needs correction, please use DEFER action to request "
                f"Wise Authority assistance. They can help determine the proper way to update this information "
                f"through the appropriate system channels."
            )

    return None


# =============================================================================
# Consent Helpers
# =============================================================================


async def handle_user_consent(
    user_id: str,
    node: GraphNode,
    consent_service: "ConsentService",
    time_service: "TimeServiceProtocol",
) -> Tuple[Optional[str], bool]:
    """Handle consent checking/creation for user nodes.

    Args:
        user_id: User identifier
        node: Graph node being memorized
        consent_service: Consent service instance
        time_service: Time service for timestamps

    Returns:
        Tuple of (error_message or None, consent_metadata_added)
    """
    from ciris_engine.logic.services.governance.consent import ConsentNotFoundError
    from ciris_engine.schemas.consent.core import ConsentRequest, ConsentStream

    try:
        consent_status = await consent_service.get_consent(user_id)

        # Check if TEMPORARY consent has expired
        if consent_status.stream == ConsentStream.TEMPORARY:
            if consent_status.expires_at and datetime.now(timezone.utc) > consent_status.expires_at:
                await consent_service.revoke_consent(user_id, "TEMPORARY consent expired (14 days)")
                return (
                    f"MEMORIZE BLOCKED: User consent expired. "
                    f"User {user_id}'s TEMPORARY consent expired on {consent_status.expires_at}. "
                    f"Decay protocol initiated. User data will be anonymized over 90 days.",
                    False,
                )

        # Add consent metadata to node attributes
        _add_consent_metadata_to_node(node, consent_status)
        return None, True

    except ConsentNotFoundError:
        # No consent exists - try to create default TEMPORARY consent
        try:
            now = datetime.now(timezone.utc)
            consent_request = ConsentRequest(
                user_id=user_id,
                stream=ConsentStream.TEMPORARY,
                categories=[],
                reason="Default TEMPORARY consent on first interaction",
            )
            await consent_service.grant_consent(consent_request, channel_id=None)

            # Add default consent metadata
            _add_default_consent_metadata(node, now)
            logger.info(f"Created default TEMPORARY consent for new user {user_id}")
            return None, True

        except Exception as grant_error:
            logger.debug(f"Cannot grant consent: {grant_error}. Continuing without consent.")
            return None, False

    except Exception as e:
        logger.debug(f"Consent service not available: {e}. Continuing without consent check.")
        return None, False


def _add_consent_metadata_to_node(node: GraphNode, consent_status: Any) -> None:
    """Add consent metadata to node attributes."""
    if hasattr(node, "attributes") and isinstance(node.attributes, dict):
        node.attributes["consent_stream"] = consent_status.stream
        node.attributes["consent_expires_at"] = (
            consent_status.expires_at.isoformat() if consent_status.expires_at else None
        )
        node.attributes["consent_granted_at"] = consent_status.granted_at.isoformat()


def _add_default_consent_metadata(node: GraphNode, now: datetime) -> None:
    """Add default TEMPORARY consent metadata to node."""
    from ciris_engine.schemas.consent.core import ConsentStream

    if hasattr(node, "attributes") and isinstance(node.attributes, dict):
        node.attributes["consent_stream"] = ConsentStream.TEMPORARY
        node.attributes["consent_expires_at"] = (now + timedelta(days=14)).isoformat()
        node.attributes["consent_granted_at"] = now.isoformat()
        node.attributes["consent_notice"] = "We forget about you in 14 days unless you say otherwise"


# =============================================================================
# Config Node Helpers
# =============================================================================


def validate_config_node(node: GraphNode) -> Tuple[str, Optional[Any], Optional[str]]:
    """Validate CONFIG node has required value.

    Args:
        node: CONFIG node to validate

    Returns:
        Tuple of (config_key, config_value, error_message)
        error_message is None if valid
    """
    config_key = node.id.replace("/", ".")

    node_attrs = node.attributes if hasattr(node, "attributes") else {}
    if isinstance(node_attrs, dict):
        config_value = node_attrs.get("value")
    else:
        config_value = getattr(node_attrs, "value", None) if node_attrs else None

    if config_value is None:
        error_msg = (
            f"MEMORIZE CONFIG FAILED: Missing required 'value' field for configuration '{config_key}'\n\n"
            "CONFIG nodes require both a key and a value. The key was extracted from the node ID, "
            "but no value was provided in the attributes.\n\n"
            "To set a configuration value, include it in the node attributes. Examples:\n\n"
            "For numeric values:\n"
            "  $memorize filter/spam_threshold CONFIG LOCAL value=0.8\n\n"
            "For boolean values:\n"
            "  $memorize filter/enabled CONFIG LOCAL value=true\n\n"
            "For string values:\n"
            "  $memorize filter/mode CONFIG LOCAL value=strict"
        )
        return config_key, None, error_msg

    return config_key, config_value, None


def create_config_node(node: GraphNode, config_key: str, config_value: Any) -> GraphNode:
    """Create a proper ConfigNode from attributes.

    Args:
        node: Original node with config data
        config_key: Configuration key
        config_value: Configuration value

    Returns:
        Properly structured GraphNode for config storage

    Raises:
        ValueError: If ConfigNode creation fails
    """
    from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue

    config_val = ConfigValue()
    if isinstance(config_value, bool):
        config_val.bool_value = config_value
    elif isinstance(config_value, int):
        config_val.int_value = config_value
    elif isinstance(config_value, float):
        config_val.float_value = config_value
    elif isinstance(config_value, list):
        config_val.list_value = config_value
    elif isinstance(config_value, dict):
        config_val.dict_value = config_value
    else:
        config_val.string_value = str(config_value)

    config_node = ConfigNode(
        id=node.id,
        type=NodeType.CONFIG,
        scope=node.scope,
        attributes={},
        key=config_key,
        value=config_val,
        version=1,
        updated_by="agent",
    )

    return config_node.to_graph_node()


# =============================================================================
# Recall Result Helpers
# =============================================================================


def build_recalled_node_info(node: GraphNode) -> RecalledNodeInfo:
    """Build RecalledNodeInfo from a graph node.

    Args:
        node: Graph node to convert

    Returns:
        RecalledNodeInfo with serialized attributes
    """
    attributes = serialize_attributes_to_json(node.attributes)
    return RecalledNodeInfo(type=node.type, scope=node.scope, attributes=attributes)


async def fetch_connected_nodes(
    node: GraphNode,
    bus_manager: "BusManager",
    handler_name: str,
) -> List[ConnectedNodeInfo]:
    """Fetch connected nodes for a recalled node via edges.

    Args:
        node: Node to get connections for
        bus_manager: Bus manager for memory operations
        handler_name: Name of calling handler

    Returns:
        List of connected node info
    """
    from ciris_engine.logic.persistence.models.graph import get_edges_for_node
    from ciris_engine.schemas.services.operations import MemoryQuery

    try:
        edges = get_edges_for_node(node.id, node.scope)
        if not edges:
            return []

        connected_nodes: List[ConnectedNodeInfo] = []

        for edge in edges:
            connected_node_id = edge.target if edge.source == node.id else edge.source
            connected_query = MemoryQuery(node_id=connected_node_id, scope=edge.scope, include_edges=False, depth=1)

            try:
                connected_results = await bus_manager.memory.recall(
                    recall_query=connected_query, handler_name=handler_name
                )
                if connected_results:
                    connected_node = connected_results[0]
                    connected_attrs = serialize_attributes_to_json(connected_node.attributes)

                    connected_node_info = ConnectedNodeInfo(
                        node_id=connected_node.id,
                        node_type=connected_node.type,
                        relationship=edge.relationship,
                        direction="outgoing" if edge.source == node.id else "incoming",
                        attributes=connected_attrs,
                    )
                    connected_nodes.append(connected_node_info)
            except Exception as e:
                logger.debug(f"Failed to get connected node {connected_node_id}: {e}")

        return connected_nodes

    except Exception as e:
        logger.warning(f"Failed to get edges for node {node.id}: {e}")
        return []


# =============================================================================
# Audit Parameter Helpers
# =============================================================================


def extract_audit_parameters(
    action_type: HandlerActionType,
    action_params: Any,
    follow_up_id: Optional[str] = None,
    error: Optional[Exception] = None,
) -> Dict[str, str]:
    """Extract audit-worthy parameters based on action type.

    Args:
        action_type: Type of action being audited
        action_params: Action parameters
        follow_up_id: Optional follow-up thought ID
        error: Optional error that occurred

    Returns:
        Dictionary of string parameters for audit context
    """
    params: Dict[str, str] = {}

    if follow_up_id:
        params["follow_up_thought_id"] = follow_up_id

    if error:
        params["error"] = str(error)
        params["error_type"] = type(error).__name__

    # Extract tool-specific info for TOOL actions
    if action_type == HandlerActionType.TOOL:
        _extract_tool_audit_params(action_params, params)

    return params


def _extract_tool_audit_params(action_params: Any, params: Dict[str, str]) -> None:
    """Extract tool-specific parameters for audit."""
    from ciris_engine.schemas.actions.parameters import ToolParams

    if hasattr(action_params, "name"):
        if isinstance(action_params, ToolParams):
            params["tool_name"] = action_params.name
            params["tool_parameters"] = json.dumps(action_params.parameters)
        else:
            # Fallback for dict-like params
            params["tool_name"] = str(getattr(action_params, "name", "unknown"))
