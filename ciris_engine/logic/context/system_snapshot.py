import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from ciris_engine.logic import persistence
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.memory_service import LocalGraphMemoryService
from ciris_engine.logic.utils import GraphQLContextProvider
from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot, UserProfile
from ciris_engine.schemas.services.core.runtime import ServiceHealthStatus
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.services.runtime_control import CircuitBreakerStatus

from .secrets_snapshot import build_secrets_snapshot

logger = logging.getLogger(__name__)


async def build_system_snapshot(
    task: Optional[Task],
    thought: Any,
    resource_monitor: Any,  # REQUIRED - mission critical system
    memory_service: Optional[LocalGraphMemoryService] = None,
    graphql_provider: Optional[GraphQLContextProvider] = None,
    telemetry_service: Optional[Any] = None,
    secrets_service: Optional[SecretsService] = None,
    runtime: Optional[Any] = None,
    service_registry: Optional[Any] = None,
) -> SystemSnapshot:
    """Build system snapshot for the thought.

    CRITICAL: This function FAILS FAST AND LOUD on any type safety violation.
    No fallbacks, no graceful degradation - if the data is wrong, we crash.

    This ensures we catch type safety issues immediately in development/testing
    rather than silently corrupting the agent's context in production.

    Philosophy: Better to crash visibly than operate with invalid data.
    """
    from ciris_engine.schemas.runtime.system_context import TaskSummary, ThoughtSummary

    thought_summary = None
    if thought:
        status_val = getattr(thought, "status", None)
        if status_val is not None and hasattr(status_val, "value"):
            status_val = status_val.value
        elif status_val is not None:
            status_val = str(status_val)
        thought_type_val = getattr(thought, "thought_type", None)
        thought_id_val = getattr(thought, "thought_id", None)
        if thought_id_val is None:
            thought_id_val = "unknown"  # Provide a default value for required field
        thought_summary = ThoughtSummary(
            thought_id=thought_id_val,
            content=getattr(thought, "content", None),
            status=status_val,
            source_task_id=getattr(thought, "source_task_id", None),
            thought_type=thought_type_val,
            thought_depth=getattr(thought, "thought_depth", None),
        )

    # Mission-critical channel_id and channel_context resolution with type safety
    channel_id = None
    channel_context = None

    def safe_extract_channel_info(context: Any, source_name: str) -> Tuple[Optional[str], Optional[Any]]:
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
        return None, None

    if task and task.context:
        channel_id, channel_context = safe_extract_channel_info(task.context, "task.context")
    if not channel_id and thought and thought.context:
        channel_id, channel_context = safe_extract_channel_info(thought.context, "thought.context")

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

    # Retrieve agent identity from graph - SINGLE CALL at snapshot generation
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

    recent_tasks_list: List[Any] = []
    logger.info("[DEBUG DB TIMING] About to get recent completed tasks")
    db_recent_tasks = persistence.get_recent_completed_tasks(10)
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

    top_tasks_list: List[Any] = []
    logger.info("[DEBUG DB TIMING] About to get top tasks")
    db_top_tasks = persistence.get_top_tasks(10)
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

    current_task_summary = None
    if task:
        # Convert Task to TaskSummary
        if isinstance(task, BaseModel):
            current_task_summary = TaskSummary(
                task_id=task.task_id,
                channel_id=getattr(task, "channel_id", "system"),
                created_at=task.created_at,
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                priority=getattr(task, "priority", 0),
                retry_count=getattr(task, "retry_count", 0),
                parent_task_id=getattr(task, "parent_task_id", None),
            )

    secrets_data: dict = {}
    if secrets_service:
        secrets_data = await build_secrets_snapshot(secrets_service)

    # Get shutdown context from runtime
    shutdown_context = None
    if runtime and hasattr(runtime, "current_shutdown_context"):
        shutdown_context = runtime.current_shutdown_context

    # Get resource alerts - CRITICAL for mission-critical systems
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

    # Get service health status
    service_health: Dict[str, ServiceHealthStatus] = {}
    circuit_breaker_status: Dict[str, CircuitBreakerStatus] = {}

    if service_registry:
        try:
            # Get health status from all registered services
            registry_info = service_registry.get_provider_info()

            # Check handler-specific services
            for handler, service_types in registry_info.get("handlers", {}).items():
                for service_type, services in service_types.items():
                    for service in services:
                        if hasattr(service, "get_health_status"):
                            service_name = f"{handler}.{service_type}"
                            health_status = await service.get_health_status()
                            # Extract is_healthy boolean from the health status object
                            service_health[service_name] = getattr(health_status, "is_healthy", False)
                        if hasattr(service, "get_circuit_breaker_status"):
                            service_name = f"{handler}.{service_type}"
                            # Get circuit breaker status as string
                            cb_status = service.get_circuit_breaker_status()
                            circuit_breaker_status[service_name] = str(cb_status) if cb_status else "UNKNOWN"

            # Check global services
            for service_type, services in registry_info.get("global_services", {}).items():
                for service in services:
                    if hasattr(service, "get_health_status"):
                        service_name = f"global.{service_type}"
                        health_status = await service.get_health_status()
                        # Extract is_healthy boolean from the health status object
                        service_health[service_name] = getattr(health_status, "is_healthy", False)
                    if hasattr(service, "get_circuit_breaker_status"):
                        service_name = f"global.{service_type}"
                        # Get circuit breaker status as string
                        cb_status = service.get_circuit_breaker_status()
                        circuit_breaker_status[service_name] = str(cb_status) if cb_status else "UNKNOWN"

        except Exception as e:
            logger.warning(f"Failed to collect service health status: {e}")

    # Get telemetry summary for resource usage
    telemetry_summary = None
    if telemetry_service:
        try:
            telemetry_summary = await telemetry_service.get_telemetry_summary()
            logger.debug("Successfully retrieved telemetry summary")
        except Exception as e:
            logger.warning(f"Failed to get telemetry summary: {e}")

    # Get adapter channels for agent visibility
    adapter_channels: Dict[str, List[ChannelContext]] = {}
    if runtime and hasattr(runtime, "adapter_manager"):
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

    # Get available tools from all adapters via tool bus
    available_tools: Dict[str, List[ToolInfo]] = {}
    if runtime and hasattr(runtime, "bus_manager") and hasattr(runtime, "service_registry"):
        try:
            service_registry = runtime.service_registry

            # Get all tool services from registry
            tool_services = service_registry.get_services_by_type("tool")

            # Validate tool_services is iterable
            if not hasattr(tool_services, "__iter__"):
                logger.error(f"get_services_by_type('tool') returned non-iterable: {type(tool_services)}")
                tool_services = []

            for tool_service in tool_services:
                # Get adapter context from the tool service
                adapter_id = getattr(tool_service, "adapter_id", "unknown")

                # Get available tools from this service
                if hasattr(tool_service, "get_available_tools"):
                    # Check if it's a coroutine function
                    import inspect

                    if inspect.iscoroutinefunction(tool_service.get_available_tools):
                        tool_names = await tool_service.get_available_tools()
                    else:
                        tool_names = tool_service.get_available_tools()

                    # Get detailed info for each tool
                    tool_infos: List[ToolInfo] = []
                    for tool_name in tool_names:
                        # Get tool info - must return ToolInfo or None
                        if hasattr(tool_service, "get_tool_info"):
                            try:
                                if inspect.iscoroutinefunction(tool_service.get_tool_info):
                                    tool_info = await tool_service.get_tool_info(tool_name)
                                else:
                                    tool_info = tool_service.get_tool_info(tool_name)

                                if tool_info:
                                    if not isinstance(tool_info, ToolInfo):
                                        raise TypeError(
                                            f"Tool service {adapter_id} returned invalid type for {tool_name}: {type(tool_info)}, expected ToolInfo"
                                        )
                                    tool_infos.append(tool_info)
                            except Exception as e:
                                logger.error(f"Failed to get info for tool {tool_name}: {e}")
                                raise

                    if tool_infos:
                        # Verify ALL tools are ToolInfo instances - FAIL FAST
                        for ti in tool_infos:
                            if not isinstance(ti, ToolInfo):
                                raise TypeError(
                                    f"Non-ToolInfo object in tool_infos: {type(ti)}, this violates type safety!"
                                )

                        # Group by adapter type (extract from adapter_id)
                        adapter_type = adapter_id.split("_")[0] if "_" in adapter_id else adapter_id
                        if adapter_type not in available_tools:
                            available_tools[adapter_type] = []
                        available_tools[adapter_type].extend(tool_infos)
                        logger.debug(f"Found {len(tool_infos)} tools for {adapter_type} adapter")

        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            raise  # FAIL FAST AND LOUD

    # Get queue status using centralized function
    queue_status = persistence.get_queue_status()

    # Get version information
    from ciris_engine.constants import CIRIS_CODENAME, CIRIS_VERSION

    try:
        from version import __version__ as code_hash
    except ImportError:
        code_hash = None

    context_data = {
        "current_task_details": current_task_summary,
        "current_thought_summary": thought_summary,
        "system_counts": {
            "total_tasks": queue_status.total_tasks,
            "total_thoughts": queue_status.total_thoughts,
            "pending_tasks": queue_status.pending_tasks,
            "pending_thoughts": queue_status.pending_thoughts + queue_status.processing_thoughts,
        },
        "top_pending_tasks_summary": top_tasks_list,
        "recently_completed_tasks_summary": recent_tasks_list,
        "channel_id": channel_id,
        "channel_context": channel_context,  # Preserve the full ChannelContext object
        # Identity graph data - loaded once per snapshot
        "agent_identity": identity_data,
        "identity_purpose": identity_purpose,
        "identity_capabilities": identity_capabilities,
        "identity_restrictions": identity_restrictions,
        # Version information
        "agent_version": CIRIS_VERSION,
        "agent_codename": CIRIS_CODENAME,
        "agent_code_hash": code_hash,
        "shutdown_context": shutdown_context,
        "service_health": service_health,
        "circuit_breaker_status": circuit_breaker_status,
        "resource_alerts": resource_alerts,  # CRITICAL mission-critical alerts
        "telemetry_summary": telemetry_summary,  # Resource usage data
        "adapter_channels": adapter_channels,  # Available channels by adapter
        "available_tools": available_tools,  # Available tools by adapter
        **secrets_data,
    }

    if graphql_provider:
        enriched_context = await graphql_provider.enrich_context(task, thought)
        # Convert EnrichedContext to dict for merging
        if enriched_context:
            # Convert GraphQLUserProfile to UserProfile
            user_profiles_list = []
            for name, graphql_profile in enriched_context.user_profiles:
                # Create UserProfile from GraphQLUserProfile data
                user_profiles_list.append(
                    UserProfile(
                        user_id=name,  # Use name as user_id
                        display_name=graphql_profile.nick or name,
                        created_at=datetime.now(),  # Default to now since not provided
                        preferred_language="en",  # Default values
                        timezone="UTC",
                        communication_style="formal",
                        trust_level=graphql_profile.trust_score or 0.5,
                        last_interaction=(
                            datetime.fromisoformat(graphql_profile.last_seen) if graphql_profile.last_seen else None
                        ),
                        is_wa=any(attr.key == "is_wa" and attr.value == "true" for attr in graphql_profile.attributes),
                        permissions=[attr.value for attr in graphql_profile.attributes if attr.key == "permission"],
                        restrictions=[attr.value for attr in graphql_profile.attributes if attr.key == "restriction"],
                    )
                )

            context_data["user_profiles"] = user_profiles_list

            # Add other enriched context data
            # Note: identity_context and community_context are not SystemSnapshot fields
            # They would need to be added to the schema if needed
            # if enriched_context.identity_context:
            #     context_data["identity_context"] = enriched_context.identity_context
            # if enriched_context.community_context:
            #     context_data["community_context"] = enriched_context.community_context

    # Enrich user profiles from memory graph (supplement or replace GraphQL data)
    if memory_service and thought:
        # Extract user IDs from the thought content and context
        user_ids_to_enrich = set()

        # Look for user mentions in thought content (Discord format: <@USER_ID> or @username)
        import re

        thought_content = getattr(thought, "content", "")
        # Discord user ID pattern
        discord_mentions = re.findall(r"<@(\d+)>", thought_content)
        user_ids_to_enrich.update(discord_mentions)
        # Also look for "ID: <number>" pattern
        id_mentions = re.findall(r"ID:\s*(\d+)", thought_content)
        user_ids_to_enrich.update(id_mentions)

        # Also check the current channel context for the message author
        if hasattr(thought, "context") and thought.context:
            if hasattr(thought.context, "user_id") and thought.context.user_id:
                user_ids_to_enrich.add(str(thought.context.user_id))

        logger.info(f"Enriching user profiles for users: {user_ids_to_enrich}")

        # Get existing user profiles or create new list
        existing_profiles = context_data.get("user_profiles", [])
        existing_user_ids = {p.user_id for p in existing_profiles}

        for user_id in user_ids_to_enrich:
            if user_id in existing_user_ids:
                continue  # Already have profile from GraphQL

            try:
                # Query user node with ALL attributes
                user_query = MemoryQuery(
                    node_id=f"user/{user_id}",
                    scope=GraphScope.LOCAL,
                    type=NodeType.USER,
                    include_edges=True,  # Get edges too
                    depth=2,  # Get connected nodes
                )
                logger.info(f"[DEBUG] Querying memory for user/{user_id}")
                user_results = await memory_service.recall(user_query)

                if user_results:
                    user_node = user_results[0]
                    # Extract ALL attributes from the user node - handle both dict and Pydantic model
                    if not user_node.attributes:
                        attrs = {}
                    elif isinstance(user_node.attributes, dict):
                        attrs = user_node.attributes
                    elif hasattr(user_node.attributes, "model_dump"):
                        attrs = user_node.attributes.model_dump()
                    else:
                        # Log warning but continue with empty dict instead of raising
                        logger.warning(
                            f"Unexpected user node attributes type for user {user_id}: {type(user_node.attributes)}, using empty dict"
                        )
                        attrs = {}

                    # Get edges and connected nodes
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
                                # Handle different attribute types
                                if not connected_node.attributes:
                                    connected_attrs = {}
                                elif hasattr(connected_node.attributes, "model_dump"):
                                    # Pydantic model
                                    connected_attrs = connected_node.attributes.model_dump()
                                elif isinstance(connected_node.attributes, dict):
                                    # Already a dict (e.g., from tsdb_summary nodes)
                                    connected_attrs = connected_node.attributes
                                else:
                                    # Unknown type - log and skip this node
                                    logger.debug(
                                        f"Unexpected attributes type for {connected_node_id}: {type(connected_node.attributes)}"
                                    )
                                    continue
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

                    # Create UserProfile with all available data
                    # Use json.dumps with default handler for datetime objects
                    def json_serial(obj):
                        """JSON serializer for objects not serializable by default json code"""
                        if hasattr(obj, "isoformat"):
                            return obj.isoformat()
                        if hasattr(obj, "model_dump"):
                            return obj.model_dump()
                        return str(obj)

                    notes_content = f"All attributes: {json.dumps(attrs, default=json_serial)}"
                    if connected_nodes_info:
                        notes_content += f"\nConnected nodes: {json.dumps(connected_nodes_info, default=json_serial)}"

                    user_profile = UserProfile(
                        user_id=user_id,
                        display_name=attrs.get("username", attrs.get("display_name", f"User_{user_id}")),
                        created_at=datetime.now(),  # Could parse from node if available
                        preferred_language=attrs.get("language", "en"),
                        timezone=attrs.get("timezone", "UTC"),
                        communication_style=attrs.get("communication_style", "formal"),
                        trust_level=attrs.get("trust_level", 0.5),
                        last_interaction=attrs.get("last_seen"),
                        is_wa=attrs.get("is_wa", False),
                        permissions=attrs.get("permissions", []),
                        restrictions=attrs.get("restrictions", []),
                        # Store ALL other attributes and connected nodes in notes for access
                        notes=notes_content,
                    )
                    existing_profiles.append(user_profile)
                    logger.info(
                        f"Added user profile for {user_id} with attributes: {list(attrs.keys())} and {len(connected_nodes_info)} connected nodes"
                    )

                # Get messages from other channels
                if channel_id:
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

                        recent_messages = []
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
                                # JSONDecodeError: malformed JSON in tags or request_data
                                # TypeError: row['tags'] or row['request_data'] is not a string
                                # AttributeError: row object missing expected attributes
                                # KeyError: row dictionary missing expected keys
                                pass

                        if recent_messages and existing_profiles:
                            # Find the user profile we just added
                            for profile in existing_profiles:
                                if profile.user_id == user_id:
                                    profile.notes += f"\nRecent messages from other channels: {json.dumps(recent_messages, default=json_serial)}"
                                    break

            except Exception as e:
                logger.warning(f"Failed to enrich user {user_id}: {e}")

        # Update context data with enriched profiles
        if existing_profiles:
            context_data["user_profiles"] = existing_profiles

    # Create the snapshot - FAIL FAST AND LOUD if there's any problem
    snapshot = SystemSnapshot(**context_data)

    # Note: GraphTelemetryService doesn't need update_system_snapshot
    # as it stores telemetry data directly in the graph

    return snapshot
