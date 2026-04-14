"""
Helper functions for system_snapshot.py to reduce complexity.

Organized by logical function groups:
1. Thought Processing
2. Channel Resolution
3. Identity Management
4. Task Processing
5. System Context
6. Service Health
7. System Data
8. User Management
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel

from ciris_engine.logic import persistence
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.memory_service import LocalGraphMemoryService
from ciris_engine.logic.utils.jsondict_helpers import get_list
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.infrastructure.identity_variance import IdentityData, IdentitySummary
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext, TaskSummary, ThoughtSummary, UserProfile
from ciris_engine.schemas.services.graph_core import ConnectedNodeInfo, GraphNode, GraphScope, NodeType, SecretsData
from ciris_engine.schemas.services.lifecycle.time import LocalizedTimeData
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.types import JSONDict

from .secrets_snapshot import ERROR_KEY, build_secrets_snapshot

logger = logging.getLogger(__name__)


# =============================================================================
# 0. CONTEXT ENRICHMENT CACHE
# =============================================================================

# Module-level cache for context enrichment results
# This prevents re-executing tools on every thought, providing instant access
# to cached data like wallet balances, HA entities, etc.


class EnrichmentCacheEntry(BaseModel):
    """Cache entry for context enrichment results."""

    data: Any
    cached_at: datetime
    ttl_seconds: float

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        age = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return age > self.ttl_seconds


class ContextEnrichmentCache:
    """Thread-safe cache for context enrichment results.

    Features:
    - Per-tool TTL configuration
    - Startup population for instant context availability
    - Manual refresh capability
    - Cache statistics for monitoring
    """

    # TTL settings based on data type best practices:
    # - HA entity lists: Devices rarely added/removed, 5 min is fine
    # - Weather data: APIs recommend 10-20 min cache (OpenWeatherMap default: 20 min)
    # - Real-time state: Use shorter TTL or on-demand refresh
    # Reference: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/appropriate-polling/
    DEFAULT_TTL = 300.0  # 5 minutes - good for entity/device lists
    MIN_TTL = 30.0  # 30 seconds minimum to prevent excessive polling
    MAX_TTL = 900.0  # 15 minutes max - suitable for weather data

    # Category-specific TTL recommendations (tools can override via context_enrichment_params)
    TTL_ENTITY_LIST = 300.0  # 5 min - HA entities, MA players (rarely change)
    TTL_WEATHER = 600.0  # 10 min - weather data (APIs rate-limit, data changes slowly)
    TTL_DEVICE_STATE = 60.0  # 1 min - device states (more dynamic but not real-time)

    def __init__(self) -> None:
        self._cache: Dict[str, EnrichmentCacheEntry] = {}
        self._hit_count = 0
        self._miss_count = 0
        self._startup_populated = False

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        entry = self._cache.get(key)
        if entry and not entry.is_expired():
            self._hit_count += 1
            logger.debug(f"[ENRICHMENT_CACHE] HIT: {key}")
            return entry.data
        if entry:
            # Expired - clean up
            del self._cache[key]
        self._miss_count += 1
        logger.debug(f"[ENRICHMENT_CACHE] MISS: {key}")
        return None

    def set(self, key: str, data: Any, ttl_seconds: Optional[float] = None) -> None:
        """Store value in cache with TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.DEFAULT_TTL
        ttl = max(self.MIN_TTL, min(ttl, self.MAX_TTL))  # Clamp to bounds

        self._cache[key] = EnrichmentCacheEntry(
            data=data,
            cached_at=datetime.now(timezone.utc),
            ttl_seconds=ttl,
        )
        logger.debug(f"[ENRICHMENT_CACHE] SET: {key} (TTL={ttl}s)")

    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache entry."""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"[ENRICHMENT_CACHE] INVALIDATED: {key}")

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("[ENRICHMENT_CACHE] Cleared all entries")

    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0.0
        return {
            "entries": len(self._cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate_pct": round(hit_rate, 1),
            "startup_populated": self._startup_populated,
        }

    @property
    def is_populated(self) -> bool:
        """Check if cache has been populated (at startup or otherwise)."""
        return len(self._cache) > 0 or self._startup_populated

    def get_all_entries(self) -> Dict[str, Any]:
        """Get all non-expired cache entries for API exposure.

        Returns a dict of {tool_key: data} for all entries that haven't expired.
        Used by /v1/system/environment endpoint to expose context enrichment data.
        """
        result: Dict[str, Any] = {}
        expired_keys: List[str] = []

        for key, entry in self._cache.items():
            if entry.is_expired():
                expired_keys.append(key)
            else:
                result[key] = entry.data

        # Clean up expired entries
        for key in expired_keys:
            del self._cache[key]

        return result

    def mark_startup_populated(self) -> None:
        """Mark that startup population has completed."""
        self._startup_populated = True
        logger.info(f"[ENRICHMENT_CACHE] Startup population complete: {len(self._cache)} entries")


# Singleton cache instance
_enrichment_cache = ContextEnrichmentCache()


def get_enrichment_cache() -> ContextEnrichmentCache:
    """Get the global context enrichment cache."""
    return _enrichment_cache


# =============================================================================
# 1. THOUGHT PROCESSING
# =============================================================================


def _extract_thought_summary(thought: Any) -> Optional[ThoughtSummary]:
    """Extract thought summary from thought object."""
    if not thought:
        return None

    status_val = getattr(thought, "status", None)
    if status_val is not None and hasattr(status_val, "value"):
        status_val = status_val.value
    elif status_val is not None:
        status_val = str(status_val)

    thought_type_val = getattr(thought, "thought_type", None)
    thought_id_val = getattr(thought, "thought_id", None)
    if thought_id_val is None:
        thought_id_val = "unknown"  # Provide a default value for required field

    return ThoughtSummary(
        thought_id=thought_id_val,
        content=getattr(thought, "content", None),
        status=status_val,
        source_task_id=getattr(thought, "source_task_id", None),
        thought_type=thought_type_val,
        thought_depth=getattr(thought, "thought_depth", None),
    )


# =============================================================================
# 1. STANDARDIZED NODE ATTRIBUTE EXTRACTION
# =============================================================================


def extract_node_attributes(node: Any) -> JSONDict:
    """Extract attributes dictionary from any GraphNode - standardized and reusable.

    This function handles all the different ways GraphNode attributes can be stored
    and provides a consistent interface for accessing them.

    Always returns a JSON-compatible dict (never None), returning empty dict for invalid nodes.

    Returns:
        JSONDict: Graph node attributes as JSON-serializable dictionary
    """
    if not node or not hasattr(node, "attributes"):
        return {}

    if node.attributes is None:
        return {}
    elif isinstance(node.attributes, dict):
        return node.attributes
    elif hasattr(node.attributes, "model_dump"):
        # Cast to dict to satisfy type checker
        return dict(node.attributes.model_dump())
    else:
        logger.warning(f"Unexpected node attributes type: {type(node.attributes)}")
        return {}


def collect_memorized_attributes(attrs: JSONDict, known_fields: Set[str]) -> Dict[str, str]:
    """Collect arbitrary attributes as memorized_attributes - standardized and reusable.

    This function extracts all attributes that aren't in the known_fields set
    and converts them to string values for type safety.

    Args:
        attrs: Node attributes from graph (JSON-compatible dict)
        known_fields: Set of known field names to exclude

    Returns:
        Dict mapping attribute names to string values
    """
    import json

    memorized_attributes = {}
    for key, value in attrs.items():
        if key not in known_fields:
            # Convert value to string for type safety
            if value is None:
                memorized_attributes[key] = ""
            elif isinstance(value, (dict, list)):
                # Use JSON serialization with datetime handler for complex objects
                memorized_attributes[key] = json.dumps(value, default=_json_serial_for_users)
            else:
                # Use string conversion for simple types (handles datetime via str())
                memorized_attributes[key] = str(value)
    return memorized_attributes


def get_channel_id_from_node(node: Any, attrs: JSONDict) -> str:
    """Extract channel_id from node, with fallback to node.id.

    Args:
        node: GraphNode object
        attrs: Node attributes (JSON-compatible dict)

    Returns:
        Channel ID string
    """
    return str(attrs.get("channel_id", node.id.split("/")[-1] if "/" in node.id else node.id))


# =============================================================================
# 2. CHANNEL RESOLUTION
# =============================================================================


def _extract_from_system_snapshot_channel_context(
    context: Any, source_name: str
) -> Tuple[Optional[str], Optional[Any]]:
    """Extract channel info from system_snapshot.channel_context."""
    if hasattr(context, "system_snapshot") and hasattr(context.system_snapshot, "channel_context"):
        extracted_context = context.system_snapshot.channel_context
        if extracted_context and hasattr(extracted_context, "channel_id"):
            extracted_id = str(extracted_context.channel_id)
            logger.debug(f"Found channel_context in {source_name}.system_snapshot.channel_context")
            return extracted_id, extracted_context
    return None, None


def _extract_from_system_snapshot_channel_id(context: Any, source_name: str) -> Tuple[Optional[str], Optional[Any]]:
    """Extract channel info from system_snapshot.channel_id."""
    if hasattr(context, "system_snapshot") and hasattr(context.system_snapshot, "channel_id"):
        cid = context.system_snapshot.channel_id
        if cid is not None:
            logger.debug(f"Found channel_id '{cid}' in {source_name}.system_snapshot.channel_id")
            return str(cid), None
    return None, None


def _extract_from_direct_channel_id(context: Any) -> Tuple[Optional[str], Optional[Any]]:
    """Extract channel info from direct channel_id attribute."""
    if isinstance(context, dict):
        cid = context.get("channel_id")
        return str(cid) if cid is not None else None, None
    elif hasattr(context, "channel_id"):
        cid = getattr(context, "channel_id", None)
        return str(cid) if cid is not None else None, None
    return None, None


def _safe_extract_channel_info(context: Any, source_name: str) -> Tuple[Optional[str], Optional[Any]]:
    """Extract both channel_id and channel_context from context."""
    if not context:
        return None, None
    try:
        # First check if context has system_snapshot.channel_context
        channel_id, channel_context = _extract_from_system_snapshot_channel_context(context, source_name)
        if channel_id:
            return channel_id, channel_context

        # Then check if context has system_snapshot.channel_id
        channel_id, channel_context = _extract_from_system_snapshot_channel_id(context, source_name)
        if channel_id:
            return channel_id, channel_context

        # Then check direct channel_id attribute
        return _extract_from_direct_channel_id(context)

    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error extracting channel info from {source_name}: {e}")
        raise  # FAIL FAST AND LOUD - configuration/programming error


def _get_initial_channel_info(task: Optional[Task], thought: Any) -> Tuple[Optional[str], Optional[Any]]:
    """Extract initial channel ID and context from task/thought."""
    channel_id = None
    channel_context = None

    if task and task.context:
        channel_id, channel_context = _safe_extract_channel_info(task.context, "task.context")
    if not channel_id and thought and thought.context:
        channel_id, channel_context = _safe_extract_channel_info(thought.context, "thought.context")

    return channel_id, channel_context


async def _perform_direct_channel_lookup(memory_service: Any, channel_id: str) -> List[Any]:
    """Perform direct memory lookup for channel by node_id."""
    query = MemoryQuery(
        node_id=f"channel/{channel_id}",
        scope=GraphScope.LOCAL,
        type=NodeType.CHANNEL,
        include_edges=False,
        depth=1,
    )
    logger.debug(f"[DEBUG DB TIMING] About to query memory service for channel/{channel_id}")
    channel_nodes = await memory_service.recall(query)
    logger.debug(f"[DEBUG DB TIMING] Completed memory service query for channel/{channel_id}")
    return list(channel_nodes) if channel_nodes else []


async def _perform_channel_search(memory_service: Any, channel_id: str) -> List[Any]:
    """Perform search-based channel lookup."""
    from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

    search_filter = MemorySearchFilter(node_type=NodeType.CHANNEL.value, scope=GraphScope.LOCAL.value, limit=10)
    logger.debug(f"[DEBUG DB TIMING] About to search memory service for channel {channel_id}")
    search_results = await memory_service.search(query=channel_id, filters=search_filter)
    logger.debug(f"[DEBUG DB TIMING] Completed memory service search for channel {channel_id}")
    return list(search_results) if search_results else []


def _extract_channel_from_search_results(search_results: List[Any], channel_id: str) -> Optional[Any]:
    """Extract matching channel from search results."""
    for node in search_results:
        if node.attributes:
            attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
            if attrs.get("channel_id") == channel_id or node.id == f"channel/{channel_id}":
                return node
    return None


# Legacy function - now uses standardized extract_node_attributes
def _extract_channel_node_attributes(
    node: Any,
) -> Optional[JSONDict]:
    """Extract attributes dictionary from channel GraphNode."""
    return extract_node_attributes(node)


def _get_known_channel_fields() -> Set[str]:
    """Get set of known ChannelContext fields."""
    return {
        "channel_id",
        "channel_type",
        "created_at",
        "channel_name",
        "is_private",
        "participants",
        "is_active",
        "last_activity",
        "message_count",
        "allowed_actions",
        "moderation_level",
    }


def _build_required_channel_fields(attrs: JSONDict, node: Any) -> JSONDict:
    """Build required ChannelContext fields with defaults."""
    # Get created_at, or generate new timestamp if missing
    created_at_val = attrs.get("created_at")
    if created_at_val is None:
        created_at_val = datetime.now(timezone.utc).isoformat()

    return {
        "channel_id": get_channel_id_from_node(node, attrs),
        "channel_type": attrs.get("channel_type", "unknown"),
        "created_at": created_at_val,
    }


def _build_optional_channel_fields(
    attrs: JSONDict,
) -> JSONDict:
    """Build optional ChannelContext fields with defaults."""
    return {
        "channel_name": attrs.get("channel_name", None),
        "is_private": attrs.get("is_private", False),
        "participants": attrs.get("participants", []),
        "is_active": attrs.get("is_active", True),
        "last_activity": attrs.get("last_activity", None),
        "message_count": attrs.get("message_count", 0),
        "allowed_actions": attrs.get("allowed_actions", []),
        "moderation_level": attrs.get("moderation_level", "standard"),
    }


# Legacy function - now uses standardized collect_memorized_attributes
def _collect_memorized_attributes(attrs: JSONDict, known_fields: Set[str]) -> Dict[str, str]:
    """Collect arbitrary attributes the agent memorized about this channel."""
    return collect_memorized_attributes(attrs, known_fields)


def _convert_graph_node_to_channel_context(node: Any) -> Optional[ChannelContext]:
    """Convert a GraphNode containing channel data to a ChannelContext object."""
    if not node or not node.attributes:
        return None

    try:
        # Extract attributes from GraphNode
        attrs = _extract_channel_node_attributes(node)
        if attrs is None:
            return None

        # Get known field definitions
        known_fields = _get_known_channel_fields()

        # Build context data
        context_data = _build_required_channel_fields(attrs, node)
        context_data.update(_build_optional_channel_fields(attrs))
        context_data["memorized_attributes"] = _collect_memorized_attributes(attrs, known_fields)

        return ChannelContext(**context_data)

    except Exception as e:
        logger.warning(f"Failed to convert GraphNode to ChannelContext: {e}")
        return None


async def _resolve_channel_context(
    task: Optional[Task], thought: Any, memory_service: Optional[LocalGraphMemoryService]
) -> Tuple[Optional[str], Optional[ChannelContext]]:
    """Resolve channel ID and context from task/thought with memory lookup."""
    # Get initial channel info from task/thought
    channel_id, initial_context = _get_initial_channel_info(task, thought)

    # If we already have a ChannelContext, use it
    if isinstance(initial_context, ChannelContext):
        return channel_id, initial_context

    # Start with the initial context (may be None or some other object)
    channel_context = initial_context

    # Attempt memory lookup if we have both channel_id and memory_service
    if channel_id and memory_service:
        try:
            # First try direct lookup for performance
            channel_nodes = await _perform_direct_channel_lookup(memory_service, channel_id)

            if channel_nodes:
                # Convert the first found channel node to ChannelContext
                channel_context = _convert_graph_node_to_channel_context(channel_nodes[0])
            else:
                # If not found, try search
                search_results = await _perform_channel_search(memory_service, channel_id)
                found_channel = _extract_channel_from_search_results(search_results, channel_id)
                if found_channel:
                    # Convert the found channel node to ChannelContext
                    channel_context = _convert_graph_node_to_channel_context(found_channel)

        except Exception as e:
            logger.debug(f"Failed to retrieve channel context for {channel_id}: {e}")

    return channel_id, channel_context


# =============================================================================
# 3. IDENTITY MANAGEMENT
# =============================================================================


async def _extract_agent_identity(
    memory_service: Optional[LocalGraphMemoryService],
) -> Tuple[IdentityData, IdentitySummary]:
    """Extract agent identity data from graph memory."""
    # Default values for when no memory service or identity is available
    default_identity_data = IdentityData(
        agent_id="unknown",
        description="No identity data available",
        role="Unknown",
        trust_level=0.5,
    )
    default_identity_summary = IdentitySummary()

    if not memory_service:
        return default_identity_data, default_identity_summary

    try:
        # Query for the agent's identity node from the graph
        identity_query = MemoryQuery(
            node_id="agent/identity", scope=GraphScope.IDENTITY, type=NodeType.AGENT, include_edges=False, depth=1
        )
        logger.debug("[DEBUG DB TIMING] About to query memory service for agent/identity")
        identity_nodes = await memory_service.recall(identity_query)
        logger.debug("[DEBUG DB TIMING] Completed memory service query for agent/identity")
        identity_result = identity_nodes[0] if identity_nodes else None

        if not identity_result or not identity_result.attributes:
            return default_identity_data, default_identity_summary

        # Extract attributes using the standardized helper
        attrs_dict = extract_node_attributes(identity_result)
        if not attrs_dict:
            return default_identity_data, default_identity_summary

        # Create typed identity data
        identity_data = IdentityData(
            agent_id=attrs_dict.get("agent_id", "unknown"),
            description=attrs_dict.get("description", "No description available"),
            role=attrs_dict.get("role_description", "Unknown"),
            trust_level=attrs_dict.get("trust_level", 0.5),
            stewardship=attrs_dict.get("stewardship"),
        )

        # Create typed identity summary
        identity_summary = IdentitySummary(
            identity_purpose=attrs_dict.get("role_description"),
            identity_capabilities=attrs_dict.get("permitted_actions", []),
            identity_restrictions=attrs_dict.get("restricted_capabilities", []),
        )

        return identity_data, identity_summary

    except Exception as e:
        logger.warning(f"Failed to retrieve agent identity from graph: {e}")
        return default_identity_data, default_identity_summary


# =============================================================================
# 4. TASK PROCESSING
# =============================================================================


def _get_recent_tasks(limit: int = 10) -> List[TaskSummary]:
    """Get recent completed tasks as TaskSummary objects."""
    recent_tasks_list: List[TaskSummary] = []
    logger.debug("[DEBUG DB TIMING] About to get recent completed tasks")
    db_recent_tasks = persistence.get_recent_completed_tasks("default", limit)
    logger.debug(f"[DEBUG DB TIMING] Completed get recent completed tasks: {len(db_recent_tasks)} tasks")

    for t_obj in db_recent_tasks:
        # db_recent_tasks returns List[Task], convert to TaskSummary
        if isinstance(t_obj, BaseModel):
            recent_tasks_list.append(
                TaskSummary(
                    task_id=t_obj.task_id,
                    channel_id=getattr(t_obj, "channel_id", "system"),
                    created_at=t_obj.created_at,
                    status=t_obj.status.value if hasattr(t_obj.status, "value") else str(t_obj.status),
                    priority=getattr(t_obj, "priority", 0),
                    retry_count=getattr(t_obj, "retry_count", 0),
                    parent_task_id=getattr(t_obj, "parent_task_id", None),
                )
            )
    return recent_tasks_list


def _get_top_tasks(limit: int = 10) -> List[TaskSummary]:
    """Get top pending tasks as TaskSummary objects."""
    top_tasks_list: List[TaskSummary] = []
    logger.debug("[DEBUG DB TIMING] About to get top tasks")
    db_top_tasks = persistence.get_top_tasks("default", limit)
    logger.debug(f"[DEBUG DB TIMING] Completed get top tasks: {len(db_top_tasks)} tasks")

    for t_obj in db_top_tasks:
        # db_top_tasks returns List[Task], convert to TaskSummary
        if isinstance(t_obj, BaseModel):
            top_tasks_list.append(
                TaskSummary(
                    task_id=t_obj.task_id,
                    channel_id=getattr(t_obj, "channel_id", "system"),
                    created_at=t_obj.created_at,
                    status=t_obj.status.value if hasattr(t_obj.status, "value") else str(t_obj.status),
                    priority=getattr(t_obj, "priority", 0),
                    retry_count=getattr(t_obj, "retry_count", 0),
                    parent_task_id=getattr(t_obj, "parent_task_id", None),
                )
            )
    return top_tasks_list


def _build_current_task_summary(task: Optional[Task]) -> Optional[TaskSummary]:
    """Convert Task to TaskSummary."""
    if not task:
        return None

    # Convert Task to TaskSummary
    if isinstance(task, BaseModel):
        return TaskSummary(
            task_id=task.task_id,
            channel_id=getattr(task, "channel_id", "system"),
            created_at=task.created_at,
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            priority=getattr(task, "priority", 0),
            retry_count=getattr(task, "retry_count", 0),
            parent_task_id=getattr(task, "parent_task_id", None),
        )
    return None


# =============================================================================
# 5. SYSTEM CONTEXT
# =============================================================================


async def _get_secrets_data(secrets_service: Optional[SecretsService]) -> SecretsData:
    """Get secrets snapshot data."""
    if secrets_service:
        # Get the raw snapshot data
        snapshot_data = await build_secrets_snapshot(secrets_service)

        # Check if there was an error
        error_message = snapshot_data.get(ERROR_KEY)
        filter_status = "active" if not error_message else "error"

        if error_message:
            logger.warning(
                "Secrets snapshot reported an internal error in secrets service. See monitoring for details."
            )

        # Convert to typed schema
        return SecretsData(
            secrets_count=snapshot_data.get("total_secrets_stored", 0),
            filter_status=filter_status,
            last_updated=None,  # Not provided by build_secrets_snapshot
            detected_secrets=snapshot_data.get("detected_secrets", []),
            secrets_filter_version=snapshot_data.get("secrets_filter_version", 0),
            additional_data=snapshot_data,  # Store full data for backwards compatibility
        )

    return SecretsData()


def _get_shutdown_context(runtime: Optional[Any]) -> Optional[Any]:
    """Extract shutdown context from runtime."""
    if runtime and hasattr(runtime, "current_shutdown_context"):
        return runtime.current_shutdown_context
    return None


def _format_critical_alert(alert: str) -> str:
    """Format a critical resource alert."""
    return f"🚨 CRITICAL! RESOURCE LIMIT BREACHED! {alert} - REJECT OR DEFER ALL TASKS!"


def _get_system_unhealthy_alert() -> str:
    """Get system unhealthy alert message."""
    return "🚨 CRITICAL! SYSTEM UNHEALTHY! RESOURCE LIMITS EXCEEDED - IMMEDIATE ACTION REQUIRED!"


def _get_resource_check_failed_alert(error: str) -> str:
    """Get resource check failed alert message."""
    return f"🚨 CRITICAL! FAILED TO CHECK RESOURCES: {error}"


def _process_critical_alerts(snapshot: Any, resource_alerts: List[str]) -> None:
    """Process critical resource alerts from snapshot."""
    if snapshot.critical:
        for alert in snapshot.critical:
            resource_alerts.append(_format_critical_alert(alert))


def _check_system_health(snapshot: Any, resource_alerts: List[str]) -> None:
    """Check system health and add alerts if unhealthy."""
    if not snapshot.healthy:
        resource_alerts.append(_get_system_unhealthy_alert())


def _collect_resource_alerts(resource_monitor: Any) -> List[str]:
    """Collect critical resource alerts."""
    resource_alerts: List[str] = []
    try:
        if resource_monitor is not None:
            snapshot = resource_monitor.snapshot
            _process_critical_alerts(snapshot, resource_alerts)
            _check_system_health(snapshot, resource_alerts)
        else:
            logger.warning("Resource monitor not available - cannot check resource constraints")
    except Exception as e:
        logger.error(f"Failed to get resource alerts: {e}")
        resource_alerts.append(_get_resource_check_failed_alert(str(e)))
    return resource_alerts


# =============================================================================
# 6. SERVICE HEALTH
# =============================================================================


async def _safe_get_health_status(service: Any) -> tuple[bool, bool]:
    """Safely get health status from a service.

    Returns:
        (has_health_method, is_healthy): Tuple indicating if service has health methods and its health status
    """
    try:
        # Check for ServiceProtocol standard method first
        if hasattr(service, "is_healthy"):
            health_status = await service.is_healthy()
            return True, bool(health_status)
        # Fallback to legacy method
        elif hasattr(service, "get_health_status"):
            health_status = await service.get_health_status()
            return True, getattr(health_status, "is_healthy", False)
    except Exception as e:
        logger.warning(f"Failed to get health status from service: {e}")
        return True, False  # Has method but failed
    return False, False  # No health method


async def _safe_get_circuit_breaker_status(service: Any) -> tuple[bool, str]:
    """Safely get circuit breaker status from a service.

    Returns:
        (has_circuit_breaker, status): Tuple indicating if service has circuit breaker and its status
    """
    try:
        if hasattr(service, "get_circuit_breaker_status"):
            cb_status = await service.get_circuit_breaker_status()
            return True, str(cb_status) if cb_status else "UNKNOWN"
    except Exception as e:
        logger.warning(f"Failed to get circuit breaker status from service: {e}")
        return True, "UNKNOWN"  # Has method but failed
    return False, "UNKNOWN"  # No circuit breaker method


async def _process_single_service(
    service: Any, service_name: str, service_health: Dict[str, bool], circuit_breaker_status: Dict[str, str]
) -> None:
    """Process health and circuit breaker status for a single service."""
    # Get health status - only include if service has health methods
    has_health_method, health_status = await _safe_get_health_status(service)
    if has_health_method:
        service_health[service_name] = health_status

    # Get circuit breaker status - only include if service has circuit breaker methods
    has_circuit_breaker, cb_status = await _safe_get_circuit_breaker_status(service)
    if has_circuit_breaker:
        circuit_breaker_status[service_name] = cb_status


async def _process_services_group(
    services_group: JSONDict,
    prefix: str,
    service_health: Dict[str, bool],
    circuit_breaker_status: Dict[str, str],
) -> None:
    """Process a group of services (handlers or global services)."""
    for service_type, services_raw in services_group.items():
        # Type narrow services to list before iteration
        services_list = get_list(services_group, service_type, [])
        for service in services_list:
            service_name = f"{prefix}.{service_type}"
            await _process_single_service(service, service_name, service_health, circuit_breaker_status)


async def _collect_service_health(
    service_registry: Optional[Any], runtime: Optional[Any] = None
) -> Tuple[Dict[str, bool], Dict[str, str]]:
    """Collect service health and circuit breaker status."""
    service_health: Dict[str, bool] = {}
    circuit_breaker_status: Dict[str, str] = {}

    # First, collect core services from runtime (21 core services)
    if runtime:
        core_services = [
            # Graph Services (6)
            "memory_service",
            "config_service",
            "telemetry_service",
            "audit_service",
            "incident_management_service",
            "tsdb_consolidation_service",
            # Infrastructure Services (7)
            "time_service",
            "shutdown_service",
            "initialization_service",
            "authentication_service",
            "resource_monitor",
            "maintenance_service",  # database maintenance
            "secrets_service",
            # Governance Services (4)
            "wa_auth_system",  # wise authority
            "adaptive_filter_service",
            "visibility_service",
            "self_observation_service",
            # Runtime Services (3)
            "llm_service",
            "runtime_control_service",
            "task_scheduler",
            # Tool Services (1)
            "secrets_tool_service",  # secrets tool
        ]

        for service_name in core_services:
            service = getattr(runtime, service_name, None)
            if service:
                await _process_single_service(service, service_name, service_health, circuit_breaker_status)

    # Then, collect handler-specific services from service_registry
    if service_registry:
        try:
            registry_info = service_registry.get_provider_info()

            # Process handler-specific services
            for handler, service_types in registry_info.get("handlers", {}).items():
                await _process_services_group(service_types, handler, service_health, circuit_breaker_status)

            # Process global services
            global_services = registry_info.get("global_services", {})
            await _process_services_group(global_services, "global", service_health, circuit_breaker_status)

        except Exception as e:
            logger.warning(f"Failed to collect service health status: {e}")

    return service_health, circuit_breaker_status


# =============================================================================
# 7. SYSTEM DATA
# =============================================================================


async def _get_telemetry_summary(telemetry_service: Optional[Any]) -> Optional[Any]:
    """Get telemetry summary for resource usage."""
    if telemetry_service:
        try:
            telemetry_summary = await telemetry_service.get_telemetry_summary()
            logger.debug("Successfully retrieved telemetry summary")
            return telemetry_summary
        except Exception as e:
            logger.warning(f"Failed to get telemetry summary: {e}")
    return None


async def _get_continuity_summary(telemetry_service: Optional[Any]) -> Optional[Any]:
    """Get continuity awareness summary from lifecycle events."""
    if telemetry_service and hasattr(telemetry_service, "get_continuity_summary"):
        try:
            continuity_summary = await telemetry_service.get_continuity_summary()
            logger.debug("Successfully retrieved continuity summary")
            return continuity_summary
        except Exception as e:
            logger.warning(f"Failed to get continuity summary: {e}")
    return None


def _validate_channel_list(channels: List[Any], adapter_name: str) -> None:
    """Validate that channel list contains ChannelContext objects."""
    if channels and not isinstance(channels[0], ChannelContext):
        raise TypeError(
            f"Adapter {adapter_name} returned invalid channel list type: {type(channels[0])}, expected ChannelContext"
        )


def _process_adapter_channels(
    adapter_name: str, adapter: Any, adapter_channels: Dict[str, List[ChannelContext]]
) -> None:
    """Process channels from a single adapter."""
    if hasattr(adapter, "get_channel_list"):
        channels = adapter.get_channel_list()
        if channels:
            _validate_channel_list(channels, adapter_name)
            # Use channel_type from first channel
            adapter_type = channels[0].channel_type
            adapter_channels[adapter_type] = channels
            logger.debug(f"Found {len(channels)} channels for {adapter_type} adapter")


def _has_valid_adapter_manager(runtime: Optional[Any]) -> bool:
    """Check if runtime has valid adapter manager."""
    return runtime is not None and hasattr(runtime, "adapter_manager") and runtime.adapter_manager is not None


async def _collect_adapter_channels(runtime: Optional[Any]) -> Dict[str, List[ChannelContext]]:
    """Collect available channels from all adapters."""
    adapter_channels: Dict[str, List[ChannelContext]] = {}

    if _has_valid_adapter_manager(runtime):
        try:
            # Assert runtime is not None since we checked it
            assert runtime is not None
            adapter_manager = runtime.adapter_manager
            # Get all active adapters
            for adapter_name, adapter in adapter_manager._adapters.items():
                _process_adapter_channels(adapter_name, adapter, adapter_channels)
        except Exception as e:
            logger.error(f"Failed to get adapter channels: {e}")
            raise  # FAIL FAST AND LOUD

    return adapter_channels


def _validate_runtime_capabilities(runtime: Optional[Any]) -> bool:
    """Check if runtime has required attributes for tool collection."""
    if runtime is None:
        return False
    if not hasattr(runtime, "bus_manager"):
        return False
    if not hasattr(runtime, "service_registry"):
        return False
    return True


def _derive_adapter_name_from_class(class_name: str) -> str:
    """Derive adapter name from class name as fallback."""
    class_name_mappings = {
        "HA": "home_assistant",
        "HomeAssistant": "home_assistant",
        "Wallet": "wallet",
        "Weather": "weather",
    }
    for key, name in class_name_mappings.items():
        if key in class_name:
            return name
    return class_name.lower().replace("toolservice", "")


def _get_adapter_name_from_provider(provider: Any) -> str:
    """Extract adapter name from provider metadata or derive from class name."""
    # Try metadata first
    if hasattr(provider, "metadata") and isinstance(provider.metadata, dict):
        name = provider.metadata.get("adapter", "unknown")
        if name != "unknown" and isinstance(name, str):
            return name

    # Fallback to class name derivation
    class_name = type(provider.instance).__name__
    derived = _derive_adapter_name_from_class(class_name)
    logger.debug("[TOOL_PROVIDERS] Fallback adapter name for %s: %s", class_name, derived)
    return derived


def _get_tool_providers(service_registry: Any) -> List[tuple[Any, str]]:
    """Get tool service providers with their adapter names from registry.

    Returns:
        List of (instance, adapter_name) tuples
    """
    from ciris_engine.schemas.runtime.enums import ServiceType

    if not hasattr(service_registry, "_services"):
        logger.warning("[TOOL_PROVIDERS] service_registry has no _services attribute")
        return []

    providers: List[tuple[Any, str]] = []
    tool_providers = service_registry._services.get(ServiceType.TOOL, [])

    for provider in tool_providers:
        if not hasattr(provider, "instance"):
            continue
        adapter_name = _get_adapter_name_from_provider(provider)
        providers.append((provider.instance, adapter_name))
        logger.debug("[TOOL_PROVIDERS] Found provider: %s -> %s", adapter_name, type(provider.instance).__name__)

    logger.info("[TOOL_PROVIDERS] Found %d tool providers", len(providers))
    return providers


def _get_tool_services(service_registry: Any) -> List[Any]:
    """Get and validate tool services from registry (instances only, for backwards compat)."""
    return [instance for instance, _ in _get_tool_providers(service_registry)]


async def _call_async_or_sync_method(obj: Any, method_name: str, *args: Any) -> Any:
    """Call a method that might be async or sync."""
    import inspect

    if not hasattr(obj, method_name):
        return None

    method = getattr(obj, method_name)

    # Handle Mock objects that don't have real methods
    if hasattr(method, "_mock_name"):
        # This is a mock, call it and check if result is a coroutine
        result = method(*args)
        if inspect.iscoroutine(result):
            return await result
        return result

    if inspect.iscoroutinefunction(method):
        return await method(*args)
    else:
        return method(*args)


async def _get_tool_info_safely(tool_service: Any, tool_name: str, adapter_id: str) -> Optional[ToolInfo]:
    """Get tool info with error handling and type validation."""
    if not hasattr(tool_service, "get_tool_info"):
        return None

    try:
        tool_info = await _call_async_or_sync_method(tool_service, "get_tool_info", tool_name)

        if tool_info:
            if not isinstance(tool_info, ToolInfo):
                raise TypeError(
                    f"Tool service {adapter_id} returned invalid type for {tool_name}: {type(tool_info)}, expected ToolInfo"
                )
            return tool_info
    except Exception as e:
        logger.error(f"Failed to get info for tool {tool_name}: {e}")
        raise

    return None


def _extract_adapter_type(adapter_id: str) -> str:
    """Extract adapter type from adapter_id.

    Now that we get proper adapter names from metadata (e.g., 'home_assistant', 'wallet'),
    we just return the name as-is. Only strip numeric suffixes if present (e.g., 'wallet_12345' -> 'wallet').
    """
    # Known adapter names that should not be split
    known_adapters = {"home_assistant", "wallet", "navigation", "weather", "ciris_hosted_tools", "ciris_accord_metrics"}
    if adapter_id in known_adapters:
        return adapter_id

    # For unknown adapters with numeric suffixes, strip the suffix
    parts = adapter_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]

    return adapter_id


def _validate_tool_infos(tool_infos: List[ToolInfo]) -> None:
    """Validate all tools are ToolInfo instances - FAIL FAST."""
    for ti in tool_infos:
        if not isinstance(ti, ToolInfo):
            raise TypeError(f"Non-ToolInfo object in tool_infos: {type(ti)}, this violates type safety!")


async def _collect_available_tools(runtime: Optional[Any]) -> Dict[str, List[ToolInfo]]:
    """Collect available tools from all adapters via tool bus."""
    available_tools: Dict[str, List[ToolInfo]] = {}

    if not _validate_runtime_capabilities(runtime):
        return available_tools

    try:
        # Assert runtime is not None since we validated it
        assert runtime is not None
        service_registry = runtime.service_registry
        # Use _get_tool_providers to get (instance, adapter_name) tuples
        tool_providers = _get_tool_providers(service_registry)

        for tool_service, adapter_name in tool_providers:
            # Get available tools from this service
            tool_names = await _call_async_or_sync_method(tool_service, "get_available_tools")
            if not tool_names:
                continue

            # Get detailed info for each tool
            tool_infos: List[ToolInfo] = []
            for tool_name in tool_names:
                tool_info = await _get_tool_info_safely(tool_service, tool_name, adapter_name)
                if tool_info:
                    tool_infos.append(tool_info)

            if tool_infos:
                _validate_tool_infos(tool_infos)

                # Group by adapter type (use adapter_name directly since it's already clean)
                adapter_type = _extract_adapter_type(adapter_name)
                if adapter_type not in available_tools:
                    available_tools[adapter_type] = []
                available_tools[adapter_type].extend(tool_infos)
                logger.debug(f"Found {len(tool_infos)} tools for {adapter_type} adapter")

    except Exception as e:
        logger.error(f"Failed to get available tools: {e}")
        raise  # FAIL FAST AND LOUD

    return available_tools


def _collect_enrichment_tools(available_tools: Dict[str, List[ToolInfo]]) -> List[tuple[str, ToolInfo]]:
    """Collect all tools marked for context enrichment."""
    enrichment_tools: List[tuple[str, ToolInfo]] = []
    for adapter_type, tools in available_tools.items():
        logger.debug(f"[COLLECT_ENRICHMENT] {adapter_type}: {len(tools)} tools")
        for tool in tools:
            if tool.context_enrichment:
                enrichment_tools.append((adapter_type, tool))
                logger.debug(f"[COLLECT_ENRICHMENT] Found enrichment tool: {adapter_type}:{tool.name}")
                logger.info(f"[CONTEXT_ENRICHMENT] Found enrichment tool: {adapter_type}:{tool.name}")
    return enrichment_tools


def _log_no_enrichment_tools(available_tools: Dict[str, List[ToolInfo]]) -> None:
    """Log debug info when no enrichment tools are found."""
    logger.info("[CONTEXT_ENRICHMENT] No context enrichment tools found in available_tools")
    logger.info(f"[CONTEXT_ENRICHMENT] available_tools keys: {list(available_tools.keys())}")
    for adapter_type, tools in available_tools.items():
        logger.info(f"[CONTEXT_ENRICHMENT] {adapter_type} has {len(tools)} tools: {[t.name for t in tools]}")


async def _find_tool_service(
    tool_providers: List[tuple[Any, str]], adapter_type: str, tool_name: str
) -> Optional[Any]:
    """Find the tool service that provides the specified tool.

    Args:
        tool_providers: List of (instance, adapter_name) tuples from _get_tool_providers
        adapter_type: Adapter type to match (e.g., "home_assistant", "wallet")
        tool_name: Name of the tool to find

    Returns:
        Tool service instance if found, None otherwise
    """
    for ts, ts_adapter_name in tool_providers:
        ts_adapter_type = _extract_adapter_type(ts_adapter_name)
        if ts_adapter_type == adapter_type:
            available = await _call_async_or_sync_method(ts, "get_available_tools")
            if available and tool_name in available:
                logger.debug(f"[FIND_TOOL] Found {tool_name} in {ts_adapter_name}")
                return ts
    logger.warning(f"[FIND_TOOL] Could not find {tool_name} for adapter {adapter_type}")
    return None


def _process_tool_result(result: Any, tool_key: str) -> Any:
    """Process and return the appropriate result from a tool execution."""
    if hasattr(result, "data") and result.data is not None:
        logger.info(f"[CONTEXT_ENRICHMENT] {tool_key} returned data with {len(result.data)} keys")
        # Log detailed result structure for context builder tuning
        if isinstance(result.data, dict):
            for key, value in result.data.items():
                if key == "entities" and isinstance(value, list):
                    logger.info(f"[CONTEXT_ENRICHMENT] {tool_key} entities count: {len(value)}")
                    for entity in value[:10]:  # Log first 10 entities
                        logger.info(f"[CONTEXT_ENRICHMENT] Entity in context: {entity}")
                    if len(value) > 10:
                        logger.info(f"[CONTEXT_ENRICHMENT] ... and {len(value) - 10} more entities")
                else:
                    logger.info(f"[CONTEXT_ENRICHMENT] {tool_key}.{key} = {value}")
        return result.data
    elif hasattr(result, "success") and result.success:
        return {"success": True, "message": "Tool executed successfully"}
    else:
        logger.info(f"[CONTEXT_ENRICHMENT] {tool_key} returned raw result")
        return result


async def _execute_enrichment_tool(
    tool_providers: List[tuple[Any, str]], adapter_type: str, tool: ToolInfo
) -> tuple[str, Any]:
    """Execute a single enrichment tool and return (tool_key, result).

    If the tool has `_info_only=True` in context_enrichment_params, it just surfaces
    the tool info for the prompt without actually executing the tool.

    Args:
        tool_providers: List of (instance, adapter_name) tuples from _get_tool_providers
        adapter_type: Adapter type (e.g., "home_assistant")
        tool: ToolInfo for the tool to execute
    """
    tool_key = f"{adapter_type}:{tool.name}"

    params = tool.context_enrichment_params or {}

    # Handle _info_only flag - just surface the tool info without executing
    if params.get("_info_only", False):
        logger.info(f"[CONTEXT_ENRICHMENT] {tool_key} is _info_only, surfacing tool info without execution")
        # Return tool info as a highlight for the prompt
        return tool_key, {
            "_tool_highlight": True,
            "tool_name": tool.name,
            "description": tool.description,
            "when_to_use": tool.when_to_use or tool.description,
            "message": f"USE THIS TOOL for this type of request: {tool.when_to_use or tool.description}",
        }

    tool_service = await _find_tool_service(tool_providers, adapter_type, tool.name)
    if not tool_service:
        logger.warning(f"[CONTEXT_ENRICHMENT] No tool service found for {tool_key}")
        return tool_key, None

    logger.info(f"[CONTEXT_ENRICHMENT] Executing {tool_key} with params: {params}")

    result = await _call_async_or_sync_method(tool_service, "execute_tool", tool.name, params)
    if result:
        return tool_key, _process_tool_result(result, tool_key)
    return tool_key, None


async def _run_context_enrichment_tools(
    runtime: Optional[Any], available_tools: Dict[str, List[ToolInfo]]
) -> Dict[str, Any]:
    """Run context enrichment tools and return their results.

    Context enrichment tools are marked with context_enrichment=True in their ToolInfo.
    They are automatically executed during context gathering to provide additional
    information for action selection (e.g., listing available Home Assistant entities).

    This function uses caching to prevent re-executing slow tools on every thought.
    Cache TTL can be configured per-tool via context_enrichment_params._cache_ttl.

    Args:
        runtime: The runtime object with service_registry and bus_manager
        available_tools: Already collected available tools by adapter type

    Returns:
        Dict mapping "adapter_type:tool_name" to tool execution results
    """
    enrichment_results: Dict[str, Any] = {}
    cache = get_enrichment_cache()

    if not _validate_runtime_capabilities(runtime):
        return enrichment_results

    assert runtime is not None

    enrichment_tools = _collect_enrichment_tools(available_tools)
    if not enrichment_tools:
        _log_no_enrichment_tools(available_tools)
        return enrichment_results

    # Use _get_tool_providers to get (instance, adapter_name) tuples with proper adapter mapping
    tool_providers = _get_tool_providers(runtime.service_registry)
    cache_hits = 0
    cache_misses = 0

    for adapter_type, tool in enrichment_tools:
        tool_key = f"{adapter_type}:{tool.name}"
        try:
            # Check cache first (fast path)
            cached_result = cache.get(tool_key)
            if cached_result is not None:
                enrichment_results[tool_key] = cached_result
                cache_hits += 1
                continue

            # Cache miss - execute tool
            cache_misses += 1
            _, result = await _execute_enrichment_tool(tool_providers, adapter_type, tool)
            if result is not None:
                # Get TTL from tool params (default: 30s)
                params = tool.context_enrichment_params or {}
                ttl_raw = params.get("_cache_ttl")
                ttl: Optional[float] = None
                if isinstance(ttl_raw, (int, float)):
                    ttl = float(ttl_raw)
                cache.set(tool_key, result, ttl)
                enrichment_results[tool_key] = result
        except Exception as e:
            logger.error(f"[CONTEXT_ENRICHMENT] Failed to execute {tool_key}: {e}")
            enrichment_results[tool_key] = {"error": str(e)}

    logger.info(
        f"[CONTEXT_ENRICHMENT] Collected {len(enrichment_results)} enrichment results "
        f"(cache: {cache_hits} hits, {cache_misses} misses)"
    )
    return enrichment_results


async def populate_enrichment_cache_at_startup(runtime: Any, available_tools: Dict[str, List[ToolInfo]]) -> None:
    """Populate the context enrichment cache at startup.

    This should be called during runtime initialization to ensure
    cached data is immediately available for the first thought.
    """
    cache = get_enrichment_cache()
    if cache.is_populated:
        logger.info("[ENRICHMENT_CACHE] Cache already populated, skipping startup population")
        return

    logger.info("[ENRICHMENT_CACHE] Starting startup population...")

    # Run enrichment tools to populate cache
    results = await _run_context_enrichment_tools(runtime, available_tools)

    cache.mark_startup_populated()
    logger.info(f"[ENRICHMENT_CACHE] Startup population complete: {len(results)} tools cached, stats: {cache.stats}")


async def refresh_enrichment_cache(runtime: Any) -> Dict[str, Any]:
    """Force refresh all context enrichment tools and update the cache.

    This clears expired entries and re-executes all enrichment tools
    to ensure fresh data is available. Used by the API endpoint when
    ?refresh=true is requested.

    Args:
        runtime: The CIRIS runtime instance

    Returns:
        Dict of {tool_key: result} for all refreshed tools
    """
    cache = get_enrichment_cache()
    logger.info("[ENRICHMENT_CACHE] API-triggered refresh starting...")

    # Collect available tools
    available_tools = await _collect_available_tools(runtime)
    if not available_tools:
        logger.warning("[ENRICHMENT_CACHE] No tools available for refresh")
        return {}

    # Run enrichment tools (this will update the cache)
    results = await _run_context_enrichment_tools(runtime, available_tools)

    logger.info(f"[ENRICHMENT_CACHE] API refresh complete: {len(results)} tools, stats: {cache.stats}")
    return results


# =============================================================================
# 8. USER MANAGEMENT
# =============================================================================


def _extract_user_from_task_context(task: Optional[Task], user_ids: Set[str]) -> None:
    """Extract user ID from task context."""
    if task and task.context:
        logger.debug(f"[USER EXTRACTION] Task context exists, user_id value: {repr(task.context.user_id)}")
        if task.context.user_id:
            user_ids.add(str(task.context.user_id))
            logger.debug(f"[USER EXTRACTION] Found user {task.context.user_id} from task context")
        else:
            logger.debug("[USER EXTRACTION] Task context.user_id is None or empty")
    else:
        logger.debug(f"[USER EXTRACTION] Task or task.context is None (task={task is not None})")


def _extract_users_from_thought_content(thought: Any, user_ids: Set[str]) -> None:
    """Extract user IDs from thought content patterns."""
    if not thought:
        return

    thought_content = getattr(thought, "content", "") or ""

    # Discord user ID pattern
    discord_mentions = re.findall(r"<@(\d+)>", thought_content)
    if discord_mentions:
        user_ids.update(discord_mentions)
        logger.debug(f"[USER EXTRACTION] Found {len(discord_mentions)} users from Discord mentions: {discord_mentions}")

    # Also look for "ID: <number>" pattern
    id_mentions = re.findall(r"ID:\s*(\d+)", thought_content)
    if id_mentions:
        user_ids.update(id_mentions)
        logger.debug(f"[USER EXTRACTION] Found {len(id_mentions)} users from ID patterns: {id_mentions}")


def _extract_user_from_thought_context(thought: Any, user_ids: Set[str]) -> None:
    """Extract user ID from thought context."""
    if hasattr(thought, "context") and thought.context:
        if hasattr(thought.context, "user_id") and thought.context.user_id:
            user_ids.add(str(thought.context.user_id))
            logger.debug(f"[USER EXTRACTION] Found user {thought.context.user_id} from thought context")


def _extract_users_from_correlation_history(task: Optional[Task], user_ids: Set[str]) -> None:
    """Extract user IDs from correlation history database."""
    if not (task and task.context and task.context.correlation_id):
        return

    try:
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()

        with persistence.get_db_connection() as conn:
            cursor = conn.cursor()

            # Build dialect-specific SQL
            if adapter.is_postgresql():
                sql = """
                    SELECT DISTINCT tags->>'user_id' as user_id
                    FROM service_correlations
                    WHERE correlation_id = %s
                    AND tags->>'user_id' IS NOT NULL
                """
            else:
                sql = """
                    SELECT DISTINCT json_extract(tags, '$.user_id') as user_id
                    FROM service_correlations
                    WHERE correlation_id = ?
                    AND json_extract(tags, '$.user_id') IS NOT NULL
                """

            cursor.execute(sql, (task.context.correlation_id,))
            correlation_users = cursor.fetchall()
            for row in correlation_users:
                if row["user_id"]:
                    user_ids.add(str(row["user_id"]))
                    logger.debug(f"[USER EXTRACTION] Found user {row['user_id']} from correlation history")
    except Exception as e:
        logger.warning(f"[USER EXTRACTION] Failed to extract users from correlation history: {e}")


def _extract_user_ids_from_context(task: Optional[Task], thought: Any) -> Set[str]:
    """Extract user IDs from task, thought, and correlation history."""
    user_ids_to_enrich: Set[str] = set()

    # Extract from all sources using helper functions
    _extract_user_from_task_context(task, user_ids_to_enrich)
    _extract_users_from_thought_content(thought, user_ids_to_enrich)
    _extract_user_from_thought_context(thought, user_ids_to_enrich)
    _extract_users_from_correlation_history(task, user_ids_to_enrich)

    logger.info(f"[USER EXTRACTION] Total users to enrich: {len(user_ids_to_enrich)} users: {user_ids_to_enrich}")
    return user_ids_to_enrich


def _json_serial_for_users(obj: Any) -> Any:
    """JSON serializer for user profile data."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


def _should_skip_user_enrichment(user_id: str, existing_user_ids: Set[str]) -> bool:
    """Check if user should be skipped during enrichment."""
    if user_id in existing_user_ids:
        logger.debug(f"[USER EXTRACTION] User {user_id} already exists, skipping")
        return True
    return False


def _create_user_memory_query(user_id: str) -> MemoryQuery:
    """Create memory query for user enrichment."""
    return MemoryQuery(
        node_id=f"user/{user_id}",
        scope=GraphScope.LOCAL,
        type=NodeType.USER,
        include_edges=True,
        depth=2,
    )


def _create_preferences_memory_query(user_id: str) -> MemoryQuery:
    """Create memory query for user preferences node.

    The setup wizard stores user preferences (language, location, timezone)
    in a separate 'preferences/{user_id}' node. This query retrieves those
    preferences for merging into the user profile.
    """
    return MemoryQuery(
        node_id=f"preferences/{user_id}",
        scope=GraphScope.LOCAL,
        type=NodeType.CONCEPT,  # Preferences are stored as CONCEPT nodes
        include_edges=False,
        depth=1,
    )


async def _query_user_preferences(
    user_id: str, memory_service: LocalGraphMemoryService
) -> JSONDict:
    """Query the preferences/{user_id} node for user settings.

    The setup wizard and settings page store user preferences in a separate
    node. This function retrieves those preferences for merging into the
    user profile.

    Args:
        user_id: The user ID to query preferences for
        memory_service: The memory service to query

    Returns:
        Dict of preference attributes (may be empty)
    """
    try:
        prefs_query = _create_preferences_memory_query(user_id)
        prefs_results = await memory_service.recall(prefs_query)

        if prefs_results:
            prefs_node = prefs_results[0]
            attrs = _extract_node_attributes(prefs_node)
            logger.debug(
                f"[USER PREFS] Found preferences for {user_id}: {list(attrs.keys())}"
            )
            return attrs

        logger.debug(f"[USER PREFS] No preferences node found for {user_id}")
        return {}

    except Exception as e:
        logger.warning(f"[USER PREFS] Failed to query preferences for {user_id}: {e}")
        return {}


def _determine_if_admin_user(user_id: str) -> bool:
    """Determine if a user_id represents an admin or system user."""
    # Check for admin patterns
    user_id_lower = user_id.lower()
    return user_id_lower.startswith("wa-") or user_id_lower == "admin" or user_id_lower.startswith("admin_")


async def _create_default_user_node(
    user_id: str, memory_service: LocalGraphMemoryService, channel_id: Optional[str]
) -> Optional[GraphNode]:
    """Create a new user node with appropriate defaults.

    Creates minimal user profile for new users:
    - Admin/WA users: minimal profile with system defaults
    - Regular users: basic profile ready for user settings
    """
    try:
        # Determine user type
        is_admin = _determine_if_admin_user(user_id)

        # Create timestamp for first_seen
        current_time = datetime.now(timezone.utc)

        # Build base attributes as JSON-compatible dict
        base_attributes: JSONDict = {
            "user_id": user_id,
            "display_name": "Admin" if is_admin else f"User_{user_id}",
            "first_seen": current_time.isoformat(),
            "created_by": "UserEnrichment",
        }

        # Add channel if provided
        if channel_id:
            base_attributes["channels"] = [channel_id]

        # Add role-specific defaults
        if is_admin:
            # Admin users get minimal profile
            base_attributes["trust_level"] = 1.0
            base_attributes["is_wa"] = user_id.lower().startswith("wa-")
        else:
            # Regular users get basic profile
            base_attributes["trust_level"] = 0.5
            base_attributes["communication_style"] = "formal"
            base_attributes["preferred_language"] = "en"
            base_attributes["timezone"] = "UTC"

        # Create GraphNode
        new_node = GraphNode(
            id=f"user/{user_id}",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes=base_attributes,
        )

        # Save to memory graph
        logger.info(
            f"[USER EXTRACTION] Creating new user node for {user_id} (admin={is_admin}) with attributes: {list(base_attributes.keys())}"
        )
        await memory_service.memorize(new_node)

        return new_node

    except Exception as e:
        logger.error(f"Failed to create default user node for {user_id}: {e}")
        return None


async def _process_user_node_for_profile(
    user_node: Any, user_id: str, memory_service: LocalGraphMemoryService, channel_id: Optional[str]
) -> UserProfile:
    """Process user node to create enriched user profile."""
    # Extract node attributes using helper
    attrs = _extract_node_attributes(user_node)

    # Collect connected nodes using helper
    connected_nodes_info = await _collect_connected_nodes(memory_service, user_id)

    # Parse datetime fields safely
    last_interaction = _parse_datetime_safely(attrs.get("last_seen"), "last_seen", user_id)
    created_at = _parse_datetime_safely(attrs.get("first_seen") or attrs.get("created_at"), "created_at", user_id)

    # Create user profile using helper
    user_profile = _create_user_profile_from_node(user_id, attrs, connected_nodes_info, last_interaction, created_at)

    # Collect cross-channel messages and add to profile notes
    if channel_id:
        recent_messages = await _collect_cross_channel_messages(user_id, channel_id)
        if recent_messages:
            # Ensure notes is not None before concatenating
            current_notes = user_profile.notes or ""
            user_profile.notes = current_notes + (
                f"\nRecent messages from other channels: {json.dumps(recent_messages, default=_json_serial_for_users)}"
            )

    logger.info(
        f"Added user profile for {user_id} with attributes: {list(attrs.keys())} and {len(connected_nodes_info)} connected nodes"
    )
    return user_profile


async def _enrich_single_user_profile(
    user_id: str, memory_service: LocalGraphMemoryService, channel_id: Optional[str]
) -> Optional[UserProfile]:
    """Enrich a single user profile from memory graph.

    If no user node exists, creates one automatically with appropriate defaults.
    This ensures user_profiles is never empty in system snapshots.

    IMPORTANT: This function queries BOTH the user/{user_id} node AND the
    preferences/{user_id} node. The setup wizard stores language/location
    preferences in the preferences node, so we must query both and merge.
    """
    try:
        # Query user node with ALL attributes
        user_query = _create_user_memory_query(user_id)
        logger.debug(f"[DEBUG] Querying memory for user/{user_id}")
        user_results = await memory_service.recall(user_query)
        logger.debug(
            f"[USER EXTRACTION] Query returned {len(user_results) if user_results else 0} results for user {user_id}"
        )

        # Also query preferences node - setup wizard stores language/location here
        prefs_attrs = await _query_user_preferences(user_id, memory_service)

        if user_results:
            user_node = user_results[0]
            profile = await _process_user_node_for_profile(user_node, user_id, memory_service, channel_id)

            # Merge preferences into profile (preferences take priority)
            if prefs_attrs:
                profile = _merge_preferences_into_profile(profile, prefs_attrs)

            return profile

        # No user node exists - create one automatically
        logger.info(f"[USER EXTRACTION] No node found for user/{user_id}, creating new user node with defaults")
        new_user_node = await _create_default_user_node(user_id, memory_service, channel_id)

        if new_user_node:
            profile = await _process_user_node_for_profile(new_user_node, user_id, memory_service, channel_id)

            # Merge preferences into profile (preferences take priority)
            if prefs_attrs:
                profile = _merge_preferences_into_profile(profile, prefs_attrs)

            return profile

    except Exception as e:
        logger.warning(f"Failed to enrich user {user_id}: {e}")

    return None


def _merge_preferences_into_profile(profile: UserProfile, prefs_attrs: JSONDict) -> UserProfile:
    """Merge preferences node attributes into a user profile.

    The setup wizard stores user preferences (language, location, timezone)
    in a separate preferences/{user_id} node. This function merges those
    preferences into the user profile, with preferences taking priority.

    Args:
        profile: The user profile to update
        prefs_attrs: Attributes from the preferences node

    Returns:
        Updated user profile with merged preferences
    """
    # Language - critical for localization
    if prefs_attrs.get("preferred_language") and prefs_attrs.get("preferred_language") != "en":
        profile.preferred_language = str(prefs_attrs["preferred_language"])
        logger.debug(f"[PREFS MERGE] Set language to '{profile.preferred_language}' from preferences node")

    # Timezone
    if prefs_attrs.get("timezone") and prefs_attrs.get("timezone") != "UTC":
        profile.timezone = str(prefs_attrs["timezone"])

    # Location
    if prefs_attrs.get("location"):
        profile.location = str(prefs_attrs["location"])
    if prefs_attrs.get("location_country"):
        # Build location string if not already set
        if not profile.location:
            parts = []
            if prefs_attrs.get("location_city"):
                parts.append(str(prefs_attrs["location_city"]))
            if prefs_attrs.get("location_region"):
                parts.append(str(prefs_attrs["location_region"]))
            if prefs_attrs.get("location_country"):
                parts.append(str(prefs_attrs["location_country"]))
            if parts:
                profile.location = ", ".join(parts)

    return profile


async def _enrich_user_profiles(
    memory_service: LocalGraphMemoryService,
    user_ids: Set[str],
    channel_id: Optional[str],
    existing_profiles: List[UserProfile],
) -> List[UserProfile]:
    """Enrich user profiles from memory graph with comprehensive data.

    IMPORTANT: For users that already exist in existing_profiles (e.g., from GraphQL),
    we MERGE memory graph data into them rather than skipping. This ensures that
    user preferences like preferred_language stored in the memory graph are always
    reflected in the final profile.
    """
    # Build lookup for existing profiles by user_id
    existing_by_id = {p.user_id: p for p in existing_profiles}

    for user_id in user_ids:
        logger.debug(f"[USER EXTRACTION] Processing user {user_id}")

        # Get enriched profile from memory graph
        memory_profile = await _enrich_single_user_profile(user_id, memory_service, channel_id)

        if not memory_profile:
            continue

        if user_id in existing_by_id:
            # User already exists - MERGE memory graph data into existing profile
            # This is critical for localization: memory graph has the real preferred_language
            existing = existing_by_id[user_id]
            logger.debug(f"[USER EXTRACTION] Merging memory graph data into existing profile for {user_id}")

            # Update fields from memory graph that may have been hardcoded or missing
            # Only update if memory graph has non-default values
            if memory_profile.preferred_language and memory_profile.preferred_language != "en":
                existing.preferred_language = memory_profile.preferred_language
            if memory_profile.timezone and memory_profile.timezone != "UTC":
                existing.timezone = memory_profile.timezone
            if memory_profile.communication_style and memory_profile.communication_style != "formal":
                existing.communication_style = memory_profile.communication_style
            if memory_profile.user_preferred_name:
                existing.user_preferred_name = memory_profile.user_preferred_name
            if memory_profile.location:
                existing.location = memory_profile.location
            if memory_profile.interaction_preferences:
                existing.interaction_preferences = memory_profile.interaction_preferences
            if memory_profile.oauth_name:
                existing.oauth_name = memory_profile.oauth_name
            # Merge memorized_attributes
            if memory_profile.memorized_attributes:
                if not existing.memorized_attributes:
                    existing.memorized_attributes = {}
                existing.memorized_attributes.update(memory_profile.memorized_attributes)
            # Append notes
            if memory_profile.notes:
                existing.notes = (existing.notes or "") + "\n" + memory_profile.notes
        else:
            # New user - add to profiles
            existing_profiles.append(memory_profile)
            existing_by_id[user_id] = memory_profile

    return existing_profiles


# =============================================================================
# TIME LOCALIZATION HELPERS
# =============================================================================


def _get_localized_times(time_service: TimeServiceProtocol) -> LocalizedTimeData:
    """Get current time localized to LONDON, CHICAGO, and TOKYO timezones.

    FAILS FAST AND LOUD if time_service is None.

    Cross-platform compatible: Falls back to UTC offsets on Windows where
    IANA timezone database may not be available.
    """
    if time_service is None:
        raise RuntimeError(
            "CRITICAL: time_service is None! Cannot get localized times. "
            "The system must be properly initialized with a time service."
        )

    from datetime import datetime, timedelta
    from datetime import timezone as dt_timezone
    from datetime import tzinfo
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    # Get current UTC time from time service
    utc_time = time_service.now()
    if not isinstance(utc_time, datetime):
        raise RuntimeError(
            f"CRITICAL: time_service.now() returned {type(utc_time)}, expected datetime. "
            f"Time service is not properly configured."
        )

    # Define timezone objects using zoneinfo with Windows fallback
    # Windows may not have IANA timezone database, use fixed UTC offsets as fallback
    london_tz: tzinfo
    try:
        london_tz = ZoneInfo("Europe/London")
    except ZoneInfoNotFoundError:
        # GMT/BST: UTC+0/+1 - use UTC+0 as conservative fallback
        london_tz = dt_timezone(timedelta(hours=0))
        logger.warning("Europe/London timezone not found, using UTC+0 fallback")

    chicago_tz: tzinfo
    try:
        chicago_tz = ZoneInfo("America/Chicago")
    except ZoneInfoNotFoundError:
        # CST/CDT: UTC-6/-5 - use UTC-6 as conservative fallback
        chicago_tz = dt_timezone(timedelta(hours=-6))
        logger.warning("America/Chicago timezone not found, using UTC-6 fallback")

    tokyo_tz: tzinfo
    try:
        tokyo_tz = ZoneInfo("Asia/Tokyo")
    except ZoneInfoNotFoundError:
        # JST: UTC+9 (no DST)
        tokyo_tz = dt_timezone(timedelta(hours=9))
        logger.warning("Asia/Tokyo timezone not found, using UTC+9 fallback")

    # Convert to localized times
    utc_iso = utc_time.isoformat()
    london_time = utc_time.astimezone(london_tz).isoformat()
    chicago_time = utc_time.astimezone(chicago_tz).isoformat()
    tokyo_time = utc_time.astimezone(tokyo_tz).isoformat()

    return LocalizedTimeData(
        utc=utc_iso,
        london=london_time,
        chicago=chicago_time,
        tokyo=tokyo_time,
    )


# =============================================================================
# USER PROFILE ENRICHMENT HELPERS (Reusable for other adapters)
# =============================================================================


def get_known_user_fields() -> Set[str]:
    """Get set of known UserProfile fields."""
    return {
        "user_id",
        "display_name",
        "username",  # Alternative for display_name
        "created_at",
        "first_seen",  # Alternative for created_at
        "preferred_language",
        "language",  # Alternative for preferred_language
        "timezone",
        "communication_style",
        # User-configurable preferences (protected from agent, visible in snapshot)
        "user_preferred_name",
        "location",
        "interaction_preferences",
        "oauth_name",
        # User interaction tracking
        "total_interactions",
        "last_interaction",
        "last_seen",  # Alternative for last_interaction
        "trust_level",
        "is_wa",
        "permissions",
        "restrictions",
        "consent_stream",
        "consent_expires_at",
        "partnership_requested_at",
        "partnership_approved",
    }


def build_user_profile_from_node(
    user_id: str,
    attrs: JSONDict,
    connected_nodes_info: List[ConnectedNodeInfo],
    last_interaction: Optional[datetime],
    created_at: Optional[datetime],
) -> UserProfile:
    """Create a UserProfile from node attributes using standardized approach."""
    # Get known field definitions
    known_fields = get_known_user_fields()

    # Collect arbitrary attributes in memorized_attributes
    memorized_attributes = collect_memorized_attributes(attrs, known_fields)

    # Create connected nodes summary for notes
    notes_content = ""
    if connected_nodes_info:
        # Convert typed objects to dict for JSON serialization
        connected_data = [node.model_dump() for node in connected_nodes_info]
        notes_content = f"Connected nodes: {json.dumps(connected_data, default=_json_serial_for_users)}"

    # Parse consent information from node attributes
    consent_expires_at = _parse_datetime_safely(attrs.get("consent_expires_at"), "consent_expires_at", user_id)
    partnership_requested_at = _parse_datetime_safely(
        attrs.get("partnership_requested_at"), "partnership_requested_at", user_id
    )

    return UserProfile(
        user_id=user_id,
        display_name=attrs.get("username", attrs.get("display_name", f"User_{user_id}")),
        created_at=created_at or datetime.now(),
        preferred_language=attrs.get("language", attrs.get("preferred_language", "en")),
        timezone=attrs.get("timezone", "UTC"),
        communication_style=attrs.get("communication_style", "formal"),
        # User-configurable preferences (protected from agent modification in MANAGED_USER_ATTRIBUTES)
        user_preferred_name=attrs.get("user_preferred_name"),
        location=attrs.get("location"),
        interaction_preferences=attrs.get("interaction_preferences"),
        oauth_name=attrs.get("oauth_name"),
        total_interactions=attrs.get("total_interactions", 0),
        last_interaction=last_interaction,
        trust_level=attrs.get("trust_level", 0.5),
        is_wa=attrs.get("is_wa", False),
        permissions=attrs.get("permissions", []),
        restrictions=attrs.get("restrictions", []),
        # Consent relationship state
        consent_stream=attrs.get("consent_stream", "TEMPORARY"),
        consent_expires_at=consent_expires_at,
        partnership_requested_at=partnership_requested_at,
        partnership_approved=attrs.get("partnership_approved", False),
        # Store arbitrary attributes the agent memorized
        memorized_attributes=memorized_attributes,
        # Store connected nodes info in notes
        notes=notes_content,
    )


# Legacy function - now uses standardized extract_node_attributes
def _extract_node_attributes(
    node: GraphNode,
) -> JSONDict:
    """Extract attributes from a graph node, handling both dict and Pydantic models."""
    return extract_node_attributes(node)


def _parse_datetime_safely(raw_value: Any, field_name: str, user_id: str) -> Optional[datetime]:
    """Parse datetime value safely, returning None for any invalid data."""
    if raw_value is None:
        return None

    if isinstance(raw_value, datetime):
        return raw_value
    elif isinstance(raw_value, str):
        try:
            # Try to parse as ISO datetime
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            logger.warning(
                f"FIELD_FAILED_VALIDATION: User {user_id} has invalid {field_name}: '{raw_value}', using None"
            )
            return None
    else:
        logger.warning(
            f"FIELD_FAILED_VALIDATION: User {user_id} has non-datetime {field_name}: {type(raw_value)}, using None"
        )
        return None


async def _collect_connected_nodes(memory_service: LocalGraphMemoryService, user_id: str) -> List[ConnectedNodeInfo]:
    """Collect connected nodes for a user node from the memory graph."""
    connected_nodes_info = []
    try:
        # Get edges for this user node
        from ciris_engine.logic.persistence.models.graph import get_edges_for_node

        edges = get_edges_for_node(f"user/{user_id}", GraphScope.LOCAL)

        for edge in edges:
            # Get the connected node
            connected_node_id = edge.target if edge.source == f"user/{user_id}" else edge.source
            connected_query = MemoryQuery(
                node_id=connected_node_id, scope=GraphScope.LOCAL, include_edges=False, depth=1
            )
            connected_results = await memory_service.recall(connected_query)
            if connected_results:
                connected_node = connected_results[0]
                # Extract attributes using our standardized helper
                connected_attrs = extract_node_attributes(connected_node)

                # Create typed connected node info
                connected_info = ConnectedNodeInfo(
                    node_id=connected_node.id,
                    node_type=connected_node.type,
                    relationship=edge.relationship,
                    attributes=connected_attrs or {},
                )
                connected_nodes_info.append(connected_info)
    except Exception as e:
        logger.warning(f"Failed to get connected nodes for user {user_id}: {e}")

    return connected_nodes_info


# Legacy function - now uses standardized build_user_profile_from_node
def _create_user_profile_from_node(
    user_id: str,
    attrs: JSONDict,
    connected_nodes_info: List[ConnectedNodeInfo],
    last_interaction: Optional[datetime],
    created_at: Optional[datetime],
) -> UserProfile:
    """Create a UserProfile from node attributes and connected nodes."""
    return build_user_profile_from_node(user_id, attrs, connected_nodes_info, last_interaction, created_at)


async def _collect_cross_channel_messages(user_id: str, channel_id: str) -> List[JSONDict]:
    """Collect recent messages from this user in other channels."""
    recent_messages = []
    try:
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()

        # Query service correlations for user's recent messages
        with persistence.get_db_connection() as conn:
            cursor = conn.cursor()

            # Build dialect-specific SQL
            if adapter.is_postgresql():
                # PostgreSQL: Cast JSONB to text for LIKE operator
                sql = """
                    SELECT
                        c.correlation_id,
                        c.handler_name,
                        c.request_data,
                        c.created_at,
                        c.tags
                    FROM service_correlations c
                    WHERE
                        c.tags::text LIKE %s
                        AND c.tags::text NOT LIKE %s
                        AND c.handler_name IN ('ObserveHandler', 'SpeakHandler')
                    ORDER BY c.created_at DESC
                    LIMIT 3
                """
            else:
                # SQLite: tags is TEXT, LIKE works directly
                sql = """
                    SELECT
                        c.correlation_id,
                        c.handler_name,
                        c.request_data,
                        c.created_at,
                        c.tags
                    FROM service_correlations c
                    WHERE
                        c.tags LIKE ?
                        AND c.tags NOT LIKE ?
                        AND c.handler_name IN ('ObserveHandler', 'SpeakHandler')
                    ORDER BY c.created_at DESC
                    LIMIT 3
                """

            cursor.execute(sql, (f'%"user_id":"{user_id}"%', f'%"channel_id":"{channel_id}"%'))

            for row in cursor.fetchall():
                try:
                    tags = json.loads(row["tags"]) if row["tags"] else {}
                    msg_channel = tags.get("channel_id", "unknown")
                    msg_content = "Message in " + msg_channel

                    # Try to extract content from request_data
                    if row["request_data"]:
                        req_data = json.loads(row["request_data"])
                        if isinstance(req_data, dict):
                            msg_content = req_data.get("content", req_data.get("message", msg_content))

                    recent_messages.append(
                        {
                            "channel": msg_channel,
                            "content": msg_content,
                            "timestamp": (
                                row["created_at"].isoformat()
                                if hasattr(row["created_at"], "isoformat")
                                else str(row["created_at"])
                            ),
                        }
                    )
                except (json.JSONDecodeError, TypeError, AttributeError, KeyError):
                    # Skip malformed entries
                    pass
    except Exception as e:
        logger.warning(f"Failed to collect cross-channel messages for user {user_id}: {e}")

    return recent_messages
