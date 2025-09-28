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
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext, TaskSummary, ThoughtSummary, UserProfile
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

from .secrets_snapshot import build_secrets_snapshot

logger = logging.getLogger(__name__)


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
# 2. CHANNEL RESOLUTION
# =============================================================================


def _safe_extract_channel_info(context: Any, source_name: str) -> Tuple[Optional[str], Optional[Any]]:
    """Extract both channel_id and channel_context from context."""
    if not context:
        return None, None
    try:
        extracted_id = None
        extracted_context = None

        # First check if context has system_snapshot.channel_context
        if hasattr(context, "system_snapshot") and hasattr(context.system_snapshot, "channel_context"):
            extracted_context = context.system_snapshot.channel_context
            if extracted_context and hasattr(extracted_context, "channel_id"):
                extracted_id = str(extracted_context.channel_id)
                logger.debug(f"Found channel_context in {source_name}.system_snapshot.channel_context")
                return extracted_id, extracted_context

        # Then check if context has system_snapshot.channel_id
        if hasattr(context, "system_snapshot") and hasattr(context.system_snapshot, "channel_id"):
            cid = context.system_snapshot.channel_id
            if cid is not None:
                logger.debug(f"Found channel_id '{cid}' in {source_name}.system_snapshot.channel_id")
                return str(cid), None

        # Then check direct channel_id attribute
        if isinstance(context, dict):
            cid = context.get("channel_id")
            return str(cid) if cid is not None else None, None
        elif hasattr(context, "channel_id"):
            cid = getattr(context, "channel_id", None)
            return str(cid) if cid is not None else None, None
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error extracting channel info from {source_name}: {e}")
        raise  # FAIL FAST AND LOUD - configuration/programming error


async def _resolve_channel_context(
    task: Optional[Task], thought: Any, memory_service: Optional[LocalGraphMemoryService]
) -> Tuple[Optional[str], Optional[Any]]:
    """Resolve channel ID and context from task/thought with memory lookup."""
    channel_id = None
    channel_context = None

    if task and task.context:
        channel_id, channel_context = _safe_extract_channel_info(task.context, "task.context")
    if not channel_id and thought and thought.context:
        channel_id, channel_context = _safe_extract_channel_info(thought.context, "thought.context")

    if channel_id and memory_service:
        try:
            # First try direct lookup for performance
            query = MemoryQuery(
                node_id=f"channel/{channel_id}",
                scope=GraphScope.LOCAL,
                type=NodeType.CHANNEL,
                include_edges=False,
                depth=1,
            )
            logger.info(f"[DEBUG DB TIMING] About to query memory service for channel/{channel_id}")
            channel_nodes = await memory_service.recall(query)
            logger.info(f"[DEBUG DB TIMING] Completed memory service query for channel/{channel_id}")

            # If not found, try search
            if not channel_nodes:
                from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

                search_filter = MemorySearchFilter(
                    node_type=NodeType.CHANNEL.value, scope=GraphScope.LOCAL.value, limit=10
                )
                # Search by channel ID in attributes
                logger.info(f"[DEBUG DB TIMING] About to search memory service for channel {channel_id}")
                search_results = await memory_service.search(query=channel_id, filters=search_filter)
                logger.info(f"[DEBUG DB TIMING] Completed memory service search for channel {channel_id}")
                # Update channel_context if we found channel info
                for node in search_results:
                    if node.attributes:
                        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
                        if attrs.get("channel_id") == channel_id or node.id == f"channel/{channel_id}":
                            # Found the channel, could extract more context here if needed
                            break
        except Exception as e:
            logger.debug(f"Failed to retrieve channel context for {channel_id}: {e}")

    return channel_id, channel_context


# =============================================================================
# 3. IDENTITY MANAGEMENT
# =============================================================================


async def _extract_agent_identity(
    memory_service: Optional[LocalGraphMemoryService],
) -> Tuple[Dict, Optional[str], List[str], List[str]]:
    """Extract agent identity data from graph memory."""
    identity_data: dict = {}
    identity_purpose: Optional[str] = None
    identity_capabilities: List[str] = []
    identity_restrictions: List[str] = []

    if memory_service:
        try:
            # Query for the agent's identity node from the graph
            identity_query = MemoryQuery(
                node_id="agent/identity", scope=GraphScope.IDENTITY, type=NodeType.AGENT, include_edges=False, depth=1
            )
            logger.info("[DEBUG DB TIMING] About to query memory service for agent/identity")
            identity_nodes = await memory_service.recall(identity_query)
            logger.info("[DEBUG DB TIMING] Completed memory service query for agent/identity")
            identity_result = identity_nodes[0] if identity_nodes else None

            if identity_result and identity_result.attributes:
                # The identity is stored as a TypedGraphNode (IdentityNode)
                # Handle both dict and Pydantic model attributes
                if isinstance(identity_result.attributes, dict):
                    attrs_dict = identity_result.attributes
                elif hasattr(identity_result.attributes, "model_dump"):
                    attrs_dict = identity_result.attributes.model_dump()
                else:
                    # Log warning but continue with empty dict instead of raising
                    logger.warning(
                        f"Unexpected graph node attributes type: {type(identity_result.attributes)}, using empty dict"
                    )
                    attrs_dict = {}

                identity_data = {
                    "agent_id": attrs_dict.get("agent_id", ""),
                    "description": attrs_dict.get("description", ""),
                    "role": attrs_dict.get("role_description", ""),
                    "trust_level": attrs_dict.get("trust_level", 0.5),
                }
                # Include stewardship if present (Book VI compliance)
                if "stewardship" in attrs_dict:
                    identity_data["stewardship"] = attrs_dict["stewardship"]

                identity_purpose = attrs_dict.get("role_description", "")
                identity_capabilities = attrs_dict.get("permitted_actions", [])
                identity_restrictions = attrs_dict.get("restricted_capabilities", [])
        except Exception as e:
            logger.warning(f"Failed to retrieve agent identity from graph: {e}")

    return identity_data, identity_purpose, identity_capabilities, identity_restrictions


# =============================================================================
# 4. TASK PROCESSING
# =============================================================================


def _get_recent_tasks(limit: int = 10) -> List[TaskSummary]:
    """Get recent completed tasks as TaskSummary objects."""
    recent_tasks_list: List[TaskSummary] = []
    logger.info("[DEBUG DB TIMING] About to get recent completed tasks")
    db_recent_tasks = persistence.get_recent_completed_tasks(limit)
    logger.info(f"[DEBUG DB TIMING] Completed get recent completed tasks: {len(db_recent_tasks)} tasks")

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
    logger.info("[DEBUG DB TIMING] About to get top tasks")
    db_top_tasks = persistence.get_top_tasks(limit)
    logger.info(f"[DEBUG DB TIMING] Completed get top tasks: {len(db_top_tasks)} tasks")

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


async def _get_secrets_data(secrets_service: Optional[SecretsService]) -> Dict:
    """Get secrets snapshot data."""
    if secrets_service:
        return await build_secrets_snapshot(secrets_service)
    return {}


def _get_shutdown_context(runtime: Optional[Any]) -> Optional[Any]:
    """Extract shutdown context from runtime."""
    if runtime and hasattr(runtime, "current_shutdown_context"):
        return runtime.current_shutdown_context
    return None


def _collect_resource_alerts(resource_monitor: Any) -> List[str]:
    """Collect critical resource alerts."""
    resource_alerts: List[str] = []
    try:
        if resource_monitor is not None:
            snapshot = resource_monitor.snapshot
            # Check for critical resource conditions
            if snapshot.critical:
                for alert in snapshot.critical:
                    resource_alerts.append(
                        f"🚨 CRITICAL! RESOURCE LIMIT BREACHED! {alert} - REJECT OR DEFER ALL TASKS!"
                    )
            # Also check if healthy flag is False
            if not snapshot.healthy:
                resource_alerts.append(
                    "🚨 CRITICAL! SYSTEM UNHEALTHY! RESOURCE LIMITS EXCEEDED - IMMEDIATE ACTION REQUIRED!"
                )
        else:
            logger.warning("Resource monitor not available - cannot check resource constraints")
    except Exception as e:
        logger.error(f"Failed to get resource alerts: {e}")
        resource_alerts.append(f"🚨 CRITICAL! FAILED TO CHECK RESOURCES: {str(e)}")
    return resource_alerts


# =============================================================================
# 6. SERVICE HEALTH
# =============================================================================


async def _safe_get_health_status(service: Any) -> bool:
    """Safely get health status from a service."""
    try:
        if hasattr(service, "get_health_status"):
            health_status = await service.get_health_status()
            return getattr(health_status, "is_healthy", False)
    except Exception as e:
        logger.warning(f"Failed to get health status from service: {e}")
    return False


def _safe_get_circuit_breaker_status(service: Any) -> str:
    """Safely get circuit breaker status from a service."""
    try:
        if hasattr(service, "get_circuit_breaker_status"):
            cb_status = service.get_circuit_breaker_status()
            return str(cb_status) if cb_status else "UNKNOWN"
    except Exception as e:
        logger.warning(f"Failed to get circuit breaker status from service: {e}")
    return "UNKNOWN"


async def _process_single_service(
    service: Any,
    service_name: str,
    service_health: Dict[str, bool],
    circuit_breaker_status: Dict[str, str]
) -> None:
    """Process health and circuit breaker status for a single service."""
    # Get health status
    health_status = await _safe_get_health_status(service)
    service_health[service_name] = health_status

    # Get circuit breaker status
    cb_status = _safe_get_circuit_breaker_status(service)
    circuit_breaker_status[service_name] = cb_status


async def _process_services_group(
    services_group: Dict[str, Any],
    prefix: str,
    service_health: Dict[str, bool],
    circuit_breaker_status: Dict[str, str]
) -> None:
    """Process a group of services (handlers or global services)."""
    for service_type, services in services_group.items():
        for service in services:
            service_name = f"{prefix}.{service_type}"
            await _process_single_service(service, service_name, service_health, circuit_breaker_status)


async def _collect_service_health(service_registry: Optional[Any]) -> Tuple[Dict[str, bool], Dict[str, str]]:
    """Collect service health and circuit breaker status."""
    service_health: Dict[str, bool] = {}
    circuit_breaker_status: Dict[str, str] = {}

    if not service_registry:
        return service_health, circuit_breaker_status

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


async def _collect_adapter_channels(runtime: Optional[Any]) -> Dict[str, List[ChannelContext]]:
    """Collect available channels from all adapters."""
    adapter_channels: Dict[str, List[ChannelContext]] = {}
    if runtime and hasattr(runtime, "adapter_manager") and runtime.adapter_manager is not None:
        try:
            adapter_manager = runtime.adapter_manager
            # Get all active adapters
            for adapter_name, adapter in adapter_manager._adapters.items():
                if hasattr(adapter, "get_channel_list"):
                    channels = adapter.get_channel_list()
                    if channels:
                        # Ensure we have ChannelContext objects
                        if not isinstance(channels[0], ChannelContext):
                            raise TypeError(
                                f"Adapter {adapter_name} returned invalid channel list type: {type(channels[0])}, expected ChannelContext"
                            )
                        # Use channel_type from first channel
                        adapter_type = channels[0].channel_type
                        adapter_channels[adapter_type] = channels
                        logger.debug(f"Found {len(channels)} channels for {adapter_type} adapter")
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


def _get_tool_services(service_registry: Any) -> List[Any]:
    """Get and validate tool services from registry."""
    tool_services = service_registry.get_services_by_type("tool")

    # Validate tool_services is iterable but not a string
    try:
        # Check if it's truly iterable and not a mock
        if not hasattr(tool_services, "__iter__") or isinstance(tool_services, str):
            logger.error(f"get_services_by_type('tool') returned non-iterable: {type(tool_services)}")
            return []

        # Try to convert to list to ensure it's really iterable
        return list(tool_services)
    except (TypeError, AttributeError):
        logger.error(f"get_services_by_type('tool') returned non-iterable: {type(tool_services)}")
        return []


async def _call_async_or_sync_method(obj: Any, method_name: str, *args) -> Any:
    """Call a method that might be async or sync."""
    import inspect

    if not hasattr(obj, method_name):
        return None

    method = getattr(obj, method_name)

    # Handle Mock objects that don't have real methods
    if hasattr(method, '_mock_name'):
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
    """Extract adapter type from adapter_id."""
    return adapter_id.split("_")[0] if "_" in adapter_id else adapter_id


def _validate_tool_infos(tool_infos: List[ToolInfo]) -> None:
    """Validate all tools are ToolInfo instances - FAIL FAST."""
    for ti in tool_infos:
        if not isinstance(ti, ToolInfo):
            raise TypeError(
                f"Non-ToolInfo object in tool_infos: {type(ti)}, this violates type safety!"
            )


async def _collect_available_tools(runtime: Optional[Any]) -> Dict[str, List[ToolInfo]]:
    """Collect available tools from all adapters via tool bus."""
    available_tools: Dict[str, List[ToolInfo]] = {}

    if not _validate_runtime_capabilities(runtime):
        return available_tools

    try:
        service_registry = runtime.service_registry
        tool_services = _get_tool_services(service_registry)

        for tool_service in tool_services:
            adapter_id = getattr(tool_service, "adapter_id", "unknown")

            # Get available tools from this service
            tool_names = await _call_async_or_sync_method(tool_service, "get_available_tools")
            if not tool_names:
                continue

            # Get detailed info for each tool
            tool_infos: List[ToolInfo] = []
            for tool_name in tool_names:
                tool_info = await _get_tool_info_safely(tool_service, tool_name, adapter_id)
                if tool_info:
                    tool_infos.append(tool_info)

            if tool_infos:
                _validate_tool_infos(tool_infos)

                # Group by adapter type
                adapter_type = _extract_adapter_type(adapter_id)
                if adapter_type not in available_tools:
                    available_tools[adapter_type] = []
                available_tools[adapter_type].extend(tool_infos)
                logger.debug(f"Found {len(tool_infos)} tools for {adapter_type} adapter")

    except Exception as e:
        logger.error(f"Failed to get available tools: {e}")
        raise  # FAIL FAST AND LOUD

    return available_tools


# =============================================================================
# 8. USER MANAGEMENT
# =============================================================================


def _extract_user_ids_from_context(task: Optional[Task], thought: Any) -> Set[str]:
    """Extract user IDs from task, thought, and correlation history."""
    user_ids_to_enrich = set()

    # 1. From task context (PRIMARY SOURCE - the user who initiated the task)
    if task and task.context and task.context.user_id:
        user_ids_to_enrich.add(str(task.context.user_id))
        logger.debug(f"[USER EXTRACTION] Found user {task.context.user_id} from task context")

    # 2. From thought content (mentions in the message)
    if thought:
        thought_content = getattr(thought, "content", "")
        # Discord user ID pattern
        discord_mentions = re.findall(r"<@(\d+)>", thought_content)
        if discord_mentions:
            user_ids_to_enrich.update(discord_mentions)
            logger.debug(
                f"[USER EXTRACTION] Found {len(discord_mentions)} users from Discord mentions: {discord_mentions}"
            )
        # Also look for "ID: <number>" pattern
        id_mentions = re.findall(r"ID:\s*(\d+)", thought_content)
        if id_mentions:
            user_ids_to_enrich.update(id_mentions)
            logger.debug(f"[USER EXTRACTION] Found {len(id_mentions)} users from ID patterns: {id_mentions}")

        # 3. From thought context (may have user_id)
        if hasattr(thought, "context") and thought.context:
            if hasattr(thought.context, "user_id") and thought.context.user_id:
                user_ids_to_enrich.add(str(thought.context.user_id))
                logger.debug(f"[USER EXTRACTION] Found user {thought.context.user_id} from thought context")

    # 4. From correlation history (get ALL users who participated in the conversation)
    if task and task.context and task.context.correlation_id:
        try:
            with persistence.get_db_connection() as conn:
                cursor = conn.cursor()
                # Query for all messages in this correlation
                cursor.execute(
                    """
                    SELECT DISTINCT json_extract(tags, '$.user_id') as user_id
                    FROM service_correlations
                    WHERE correlation_id = ?
                    AND json_extract(tags, '$.user_id') IS NOT NULL
                    """,
                    (task.context.correlation_id,),
                )
                correlation_users = cursor.fetchall()
                for row in correlation_users:
                    if row["user_id"]:
                        user_ids_to_enrich.add(str(row["user_id"]))
                        logger.debug(f"[USER EXTRACTION] Found user {row['user_id']} from correlation history")
        except Exception as e:
            logger.warning(f"[USER EXTRACTION] Failed to extract users from correlation history: {e}")

    logger.info(f"[USER EXTRACTION] Total users to enrich: {len(user_ids_to_enrich)} users: {user_ids_to_enrich}")
    return user_ids_to_enrich


def _json_serial_for_users(obj):
    """JSON serializer for user profile data."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


async def _enrich_user_profiles(
    memory_service: LocalGraphMemoryService,
    user_ids: Set[str],
    channel_id: Optional[str],
    existing_profiles: List[UserProfile],
) -> List[UserProfile]:
    """Enrich user profiles from memory graph with comprehensive data."""
    existing_user_ids = {p.user_id for p in existing_profiles}

    for user_id in user_ids:
        logger.debug(f"[USER EXTRACTION] Processing user {user_id}")
        if user_id in existing_user_ids:
            logger.debug(f"[USER EXTRACTION] User {user_id} already exists, skipping")
            continue  # Already have profile

        try:
            # Query user node with ALL attributes
            user_query = MemoryQuery(
                node_id=f"user/{user_id}",
                scope=GraphScope.LOCAL,
                type=NodeType.USER,
                include_edges=True,
                depth=2,
            )
            logger.info(f"[DEBUG] Querying memory for user/{user_id}")
            user_results = await memory_service.recall(user_query)
            logger.debug(
                f"[USER EXTRACTION] Query returned {len(user_results) if user_results else 0} results for user {user_id}"
            )

            if user_results:
                user_node = user_results[0]

                # Extract node attributes using helper
                attrs = _extract_node_attributes(user_node, user_id)

                # Collect connected nodes using helper
                connected_nodes_info = await _collect_connected_nodes(memory_service, user_id)

                # Parse datetime fields safely (no more LLM corruption hack!)
                last_interaction = _parse_datetime_safely(attrs.get("last_seen"), "last_seen", user_id)
                created_at = _parse_datetime_safely(
                    attrs.get("first_seen") or attrs.get("created_at"), "created_at", user_id
                )

                # Create user profile using helper
                user_profile = _create_user_profile_from_node(
                    user_id, attrs, connected_nodes_info, last_interaction, created_at
                )
                existing_profiles.append(user_profile)
                logger.info(
                    f"Added user profile for {user_id} with attributes: {list(attrs.keys())} and {len(connected_nodes_info)} connected nodes"
                )

                # Collect cross-channel messages and add to profile notes
                if channel_id:
                    recent_messages = await _collect_cross_channel_messages(user_id, channel_id)
                    if recent_messages:
                        user_profile.notes += f"\nRecent messages from other channels: {json.dumps(recent_messages, default=_json_serial_for_users)}"

        except Exception as e:
            logger.warning(f"Failed to enrich user {user_id}: {e}")

    return existing_profiles


# =============================================================================
# TIME LOCALIZATION HELPERS
# =============================================================================


def _get_localized_times(time_service) -> Dict[str, str]:
    """Get current time localized to LONDON, CHICAGO, and TOKYO timezones.

    FAILS FAST AND LOUD if time_service is None.
    """
    if time_service is None:
        raise RuntimeError(
            "CRITICAL: time_service is None! Cannot get localized times. "
            "The system must be properly initialized with a time service."
        )

    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Get current UTC time from time service
    utc_time = time_service.now()
    if not isinstance(utc_time, datetime):
        raise RuntimeError(
            f"CRITICAL: time_service.now() returned {type(utc_time)}, expected datetime. "
            f"Time service is not properly configured."
        )

    # Define timezone objects using zoneinfo (Python 3.9+ standard library)
    london_tz = ZoneInfo("Europe/London")
    chicago_tz = ZoneInfo("America/Chicago")
    tokyo_tz = ZoneInfo("Asia/Tokyo")

    # Convert to localized times
    utc_iso = utc_time.isoformat()
    london_time = utc_time.astimezone(london_tz).isoformat()
    chicago_time = utc_time.astimezone(chicago_tz).isoformat()
    tokyo_time = utc_time.astimezone(tokyo_tz).isoformat()

    return {"utc": utc_iso, "london": london_time, "chicago": chicago_time, "tokyo": tokyo_time}


# =============================================================================
# USER PROFILE ENRICHMENT HELPERS (Reusable for other adapters)
# =============================================================================


def _extract_node_attributes(node: GraphNode, user_id: str) -> Dict[str, Any]:
    """Extract attributes from a graph node, handling both dict and Pydantic models."""
    if not node.attributes:
        return {}
    elif isinstance(node.attributes, dict):
        return node.attributes
    elif hasattr(node.attributes, "model_dump"):
        return node.attributes.model_dump()
    else:
        logger.warning(f"Unexpected node attributes type for {user_id}: {type(node.attributes)}, using empty dict")
        return {}


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


async def _collect_connected_nodes(memory_service: LocalGraphMemoryService, user_id: str) -> List[Dict[str, Any]]:
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
                # Extract attributes using our helper
                connected_attrs = _extract_node_attributes(connected_node, connected_node_id)
                connected_nodes_info.append(
                    {
                        "node_id": connected_node.id,
                        "node_type": connected_node.type,
                        "relationship": edge.relationship,
                        "attributes": connected_attrs,
                    }
                )
    except Exception as e:
        logger.warning(f"Failed to get connected nodes for user {user_id}: {e}")

    return connected_nodes_info


def _create_user_profile_from_node(
    user_id: str,
    attrs: Dict[str, Any],
    connected_nodes_info: List[Dict[str, Any]],
    last_interaction: Optional[datetime],
    created_at: Optional[datetime],
) -> UserProfile:
    """Create a UserProfile from node attributes and connected nodes."""
    # Use json.dumps with default handler for datetime objects
    notes_content = f"All attributes: {json.dumps(attrs, default=_json_serial_for_users)}"
    if connected_nodes_info:
        notes_content += f"\nConnected nodes: {json.dumps(connected_nodes_info, default=_json_serial_for_users)}"

    # Extract consent information from node attributes
    consent_expires_at = _parse_datetime_safely(attrs.get("consent_expires_at"), "consent_expires_at", user_id)
    partnership_requested_at = _parse_datetime_safely(
        attrs.get("partnership_requested_at"), "partnership_requested_at", user_id
    )

    return UserProfile(
        user_id=user_id,
        display_name=attrs.get("username", attrs.get("display_name", f"User_{user_id}")),
        created_at=created_at or datetime.now(),  # Use current time if no valid created_at
        preferred_language=attrs.get("language", "en"),
        timezone=attrs.get("timezone", "UTC"),
        communication_style=attrs.get("communication_style", "formal"),
        trust_level=attrs.get("trust_level", 0.5),
        last_interaction=last_interaction,
        is_wa=attrs.get("is_wa", False),
        permissions=attrs.get("permissions", []),
        restrictions=attrs.get("restrictions", []),
        # Consent relationship state
        consent_stream=attrs.get("consent_stream", "TEMPORARY"),
        consent_expires_at=consent_expires_at,
        partnership_requested_at=partnership_requested_at,
        partnership_approved=attrs.get("partnership_approved", False),
        # Store ALL other attributes and connected nodes in notes for access
        notes=notes_content,
    )


async def _collect_cross_channel_messages(user_id: str, channel_id: str) -> List[Dict[str, Any]]:
    """Collect recent messages from this user in other channels."""
    recent_messages = []
    try:
        # Query service correlations for user's recent messages
        with persistence.get_db_connection() as conn:
            cursor = conn.cursor()
            # Look for handler actions from this user in other channels
            cursor.execute(
                """
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
            """,
                (f'%"user_id":"{user_id}"%', f'%"channel_id":"{channel_id}"%'),
            )

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
