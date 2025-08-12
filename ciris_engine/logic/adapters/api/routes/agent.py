"""
Agent interaction endpoints for CIRIS API v3.0 (Simplified).

Core endpoints for natural agent interaction.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.agent import AgentLineage, MessageContext, ServiceAvailability
from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.messages import IncomingMessage

from ..constants import DESC_CURRENT_COGNITIVE_STATE, ERROR_MEMORY_SERVICE_NOT_AVAILABLE
from ..dependencies.auth import AuthContext, require_observer

logger = logging.getLogger(__name__)

# Minimum uptime in seconds before defaulting task count
MIN_UPTIME_FOR_DEFAULT_TASKS = 60

router = APIRouter(prefix="/agent", tags=["agent"])

# Request/Response schemas


class InteractRequest(BaseModel):
    """Request to interact with the agent."""

    message: str = Field(..., description="Message to send to the agent")
    context: Optional[MessageContext] = Field(None, description="Optional context")


class InteractResponse(BaseModel):
    """Response from agent interaction."""

    message_id: str = Field(..., description="Unique message ID")
    response: str = Field(..., description="Agent's response")
    state: str = Field(..., description="Agent's cognitive state after processing")
    processing_time_ms: int = Field(..., description="Time taken to process")


class ConversationMessage(BaseModel):
    """Message in conversation history."""

    id: str = Field(..., description="Message ID")
    author: str = Field(..., description="Message author")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="When sent")
    is_agent: bool = Field(..., description="Whether this was from the agent")


class ConversationHistory(BaseModel):
    """Conversation history."""

    messages: List[ConversationMessage] = Field(..., description="Message history")
    total_count: int = Field(..., description="Total messages")
    has_more: bool = Field(..., description="Whether more messages exist")


class AgentStatus(BaseModel):
    """Agent status and cognitive state."""

    # Core identity
    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")

    # Version information
    version: str = Field(..., description="CIRIS version (e.g., 1.0.4-beta)")
    codename: str = Field(..., description="Release codename")
    code_hash: Optional[str] = Field(None, description="Code hash for exact version")

    # State information
    cognitive_state: str = Field(..., description=DESC_CURRENT_COGNITIVE_STATE)
    uptime_seconds: float = Field(..., description="Time since startup")

    # Activity metrics
    messages_processed: int = Field(..., description="Total messages processed")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    current_task: Optional[str] = Field(None, description="Current task description")

    # System state
    services_active: int = Field(..., description="Number of active services")
    memory_usage_mb: float = Field(..., description="Current memory usage in MB")
    multi_provider_services: Optional[dict] = Field(None, description="Services with provider counts")


class AgentIdentity(BaseModel):
    """Agent identity and capabilities."""

    # Identity
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    purpose: str = Field(..., description="Agent's purpose")
    created_at: datetime = Field(..., description="When agent was created")
    lineage: AgentLineage = Field(..., description="Agent lineage information")
    variance_threshold: float = Field(..., description="Identity variance threshold")

    # Capabilities
    tools: List[str] = Field(..., description="Available tools")
    handlers: List[str] = Field(..., description="Active handlers")
    services: ServiceAvailability = Field(..., description="Service availability")
    permissions: List[str] = Field(..., description="Agent permissions")


class ChannelInfo(BaseModel):
    """Information about a communication channel."""

    channel_id: str = Field(..., description="Unique channel identifier")
    channel_type: str = Field(..., description="Type of channel (discord, api, cli)")
    display_name: str = Field(..., description="Human-readable channel name")
    is_active: bool = Field(..., description="Whether channel is currently active")
    created_at: Optional[datetime] = Field(None, description="When channel was created")
    last_activity: Optional[datetime] = Field(None, description="Last message in channel")
    message_count: int = Field(0, description="Total messages in channel")


class ChannelList(BaseModel):
    """List of active channels."""

    channels: List[ChannelInfo] = Field(..., description="List of channels")
    total_count: int = Field(..., description="Total number of channels")


# Message tracking for interact functionality
_message_responses: dict[str, str] = {}
_response_events: dict[str, asyncio.Event] = {}


async def store_message_response(message_id: str, response: str) -> None:
    """Store a response and notify waiting request."""
    _message_responses[message_id] = response
    event = _response_events.get(message_id)
    if event:
        event.set()


# Endpoints


@router.post("/interact", response_model=SuccessResponse[InteractResponse])
async def interact(
    request: Request, body: InteractRequest, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[InteractResponse]:
    """
    Send message and get response.

    This endpoint combines the old send/ask functionality into a single interaction.
    It sends the message and waits for the agent's response (with a reasonable timeout).

    Requires: SEND_MESSAGES permission (ADMIN+ by default, or OBSERVER with explicit grant)
    """
    # Check if user has permission to send messages
    if not auth.has_permission(Permission.SEND_MESSAGES):
        # Get auth service to check permission request status
        # Note: We can't use dependency injection here, so we'll access it directly
        auth_service = request.app.state.auth_service if hasattr(request.app.state, "auth_service") else None
        user = auth_service.get_user(auth.user_id) if auth_service else None

        # If user is an OAuth user without a permission request, automatically create one
        if user and user.auth_type == "oauth" and user.permission_requested_at is None:
            # Set permission request timestamp
            user.permission_requested_at = datetime.now(timezone.utc)
            # Store the updated user
            auth_service._users[user.wa_id] = user

            # Don't log potentially sensitive email addresses
            logger.info(f"Auto-created permission request for OAuth user ID: {user.wa_id}")

        # Build detailed error response
        error_detail = {
            "error": "insufficient_permissions",
            "message": "You do not have permission to send messages to this agent.",
            "discord_invite": "https://discord.gg/A3HVPMWd",
            "can_request_permissions": user.permission_requested_at is None if user else True,
            "permission_requested": user.permission_requested_at is not None if user else False,
            "requested_at": user.permission_requested_at.isoformat() if user and user.permission_requested_at else None,
        }

        raise HTTPException(status_code=403, detail=error_detail)
    # Create unique IDs
    message_id = str(uuid.uuid4())
    channel_id = f"api_{auth.user_id}"  # User-specific channel
    event = asyncio.Event()
    _response_events[message_id] = event

    # Create message
    msg = IncomingMessage(
        message_id=message_id,
        author_id=auth.user_id,
        author_name=auth.user_id,
        content=body.message,
        channel_id=channel_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Track timing
    start_time = datetime.now(timezone.utc)

    # Route message through adapter's handler
    if hasattr(request.app.state, "on_message"):
        await request.app.state.on_message(msg)
    else:
        raise HTTPException(status_code=503, detail="Message handler not configured")

    # Get timeout from config or use default
    timeout = 55.0  # default timeout for longer processing
    if hasattr(request.app.state, "api_config"):
        timeout = request.app.state.api_config.interaction_timeout

    # Wait for response with timeout
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)

        # Get response
        response_content = _message_responses.get(message_id, "I'm processing your request. Please check back shortly.")

        # Clean up
        _response_events.pop(message_id, None)
        _message_responses.pop(message_id, None)

        # Calculate processing time
        end_time = datetime.now(timezone.utc)
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Get current cognitive state
        cognitive_state = "WORK"
        runtime = getattr(request.app.state, "runtime", None)
        if runtime and hasattr(runtime, "state_manager"):
            cognitive_state = runtime.state_manager.current_state

        response = InteractResponse(
            message_id=message_id,
            response=response_content,
            state=cognitive_state,
            processing_time_ms=processing_time_ms,
        )

        return SuccessResponse(data=response)

    except asyncio.TimeoutError:
        # Clean up
        _response_events.pop(message_id, None)
        _message_responses.pop(message_id, None)

        # Return a timeout response rather than error
        response = InteractResponse(
            message_id=message_id,
            response="Still processing. Check back later. Agent response is not guaranteed.",
            state="WORK",
            processing_time_ms=int(timeout * 1000),  # Use actual timeout value
        )

        return SuccessResponse(data=response)


@router.get("/history", response_model=SuccessResponse[ConversationHistory])
async def get_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
    before: Optional[datetime] = Query(None, description="Get messages before this time"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[ConversationHistory]:
    """
    Conversation history.

    Get the conversation history for the current user.
    """
    # Use user-specific channel
    channel_id = f"api_{auth.user_id}"

    # For admin users and above, also include the default API channel (home)
    channels_to_query = [channel_id]
    if auth.role in ["ADMIN", "AUTHORITY", "SYSTEM_ADMIN"]:
        # Get default API channel from config
        api_host = getattr(request.app.state, "api_host", "127.0.0.1")
        api_port = getattr(request.app.state, "api_port", "8080")
        default_channel = f"api_{api_host}_{api_port}"
        channels_to_query.append(default_channel)

        # Also add common variations of the API channel
        # This ensures we catch messages regardless of how the channel was recorded
        channels_to_query.extend(
            [
                f"api_0.0.0.0_{api_port}",  # Bind address
                f"api_127.0.0.1_{api_port}",  # Localhost
                f"api_localhost_{api_port}",  # Hostname variant
            ]
        )

    logger.info(f"History query for user {auth.user_id} with role {auth.role}, channels: {channels_to_query}")

    # Check for mock message history first
    message_history = getattr(request.app.state, "message_history", None)
    if message_history is not None:
        # Filter messages for this user (including default channel for admins)
        user_messages = [m for m in message_history if m.get("channel_id") in channels_to_query]

        # Convert to response format
        messages = []

        # First, expand all messages (user + response pairs)
        all_messages = []
        for msg in user_messages:
            # Add user message
            all_messages.append(
                ConversationMessage(
                    id=msg["message_id"],
                    author=msg["author_id"],
                    content=msg["content"],
                    timestamp=(
                        datetime.fromisoformat(msg["timestamp"])
                        if isinstance(msg["timestamp"], str)
                        else msg["timestamp"]
                    ),
                    is_agent=False,
                )
            )
            # Add agent response if exists
            if msg.get("response"):
                all_messages.append(
                    ConversationMessage(
                        id=f"{msg['message_id']}_response",
                        author="Scout",
                        content=msg["response"],
                        timestamp=(
                            datetime.fromisoformat(msg["timestamp"])
                            if isinstance(msg["timestamp"], str)
                            else msg["timestamp"]
                        ),
                        is_agent=True,
                    )
                )

        # Now take only the last 'limit' messages
        if len(all_messages) > limit:
            messages = all_messages[-limit:]
        else:
            messages = all_messages

        history = ConversationHistory(
            messages=messages,
            total_count=len(user_messages),
            has_more=len(user_messages) > len(messages),  # Fixed: has_more should be based on actual truncation
        )

        return SuccessResponse(data=history)

    # Get communication service
    comm_service = getattr(request.app.state, "communication_service", None)
    if not comm_service:
        # Fallback: query from memory
        memory_service = getattr(request.app.state, "memory_service", None)
        if memory_service:
            # Query conversation nodes from memory
            from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
            from ciris_engine.schemas.services.operations import MemoryQuery

            # MemoryQuery expects node_id, not filters
            # For conversation history, we'll need to use a different approach
            # For now, create a placeholder query
            query = MemoryQuery(
                node_id=f"conversation_{channel_id}",
                scope=GraphScope.LOCAL,
                type=NodeType.CONVERSATION_SUMMARY,
                include_edges=True,
                depth=1,
            )

            nodes = await memory_service.recall(query)

            # Convert to conversation messages
            messages = []
            for node in nodes:
                attrs = node.attributes
                messages.append(
                    ConversationMessage(
                        id=attrs.get("message_id", node.id),
                        author=attrs.get("author", "unknown"),
                        content=attrs.get("content", ""),
                        timestamp=datetime.fromisoformat(attrs.get("timestamp", node.created_at)),
                        is_agent=attrs.get("is_agent", False),
                    )
                )

            history = ConversationHistory(messages=messages, total_count=len(messages), has_more=len(messages) == limit)

            return SuccessResponse(data=history)

    try:
        # Fetch messages from communication service (fetch more to allow filtering)
        fetch_limit = limit * 2 if before else limit

        # Fetch messages from all relevant channels
        fetched_messages: List[Dict[str, Any]] = []
        for channel in channels_to_query:
            try:
                logger.info(f"Fetching messages from channel: {channel}")
                if comm_service is None:
                    logger.warning("Communication service is not available")
                    continue
                channel_messages = await comm_service.fetch_messages(channel, limit=fetch_limit)
                logger.info(f"Retrieved {len(channel_messages)} messages from {channel}")
                fetched_messages.extend(channel_messages)
            except Exception as e:
                # If a channel doesn't exist or has no messages, continue
                logger.warning(f"Failed to fetch from channel {channel}: {e}")
                continue

        # Sort messages by timestamp (newest first)
        sorted_messages = sorted(
            fetched_messages,
            key=lambda m: (
                m.timestamp
                if isinstance(m.timestamp, datetime)
                else datetime.fromisoformat(str(m.timestamp)) if m.timestamp else datetime.now(timezone.utc)
            ),
            reverse=True,
        )

        # Filter by time if specified
        if before:
            filtered_messages = [
                m
                for m in sorted_messages
                if m.timestamp
                and (m.timestamp if isinstance(m.timestamp, datetime) else datetime.fromisoformat(str(m.timestamp)))
                < before
            ]
        else:
            filtered_messages = sorted_messages

        # Convert to conversation messages
        conv_messages = []
        for msg in filtered_messages[:limit]:  # Apply limit after filtering
            # Safely access model attributes
            timestamp_val = msg.timestamp
            msg_timestamp = (
                timestamp_val
                if isinstance(timestamp_val, datetime)
                else datetime.fromisoformat(str(timestamp_val)) if timestamp_val else datetime.now(timezone.utc)
            )

            conv_messages.append(
                ConversationMessage(
                    id=str(msg.message_id or ""),
                    author=str(msg.author_name or msg.author_id or ""),
                    content=str(msg.content or ""),
                    timestamp=msg_timestamp,
                    is_agent=bool(getattr(msg, "is_agent_message", False) or getattr(msg, "is_bot", False)),
                )
            )

        # Build response
        history = ConversationHistory(
            messages=conv_messages,
            total_count=len(filtered_messages),  # Total before limiting
            has_more=len(filtered_messages) > limit,
        )

        return SuccessResponse(data=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_cognitive_state(runtime) -> str:
    """Get the agent's cognitive state."""
    if hasattr(runtime, "state_manager"):
        return runtime.state_manager.current_state
    return "WORK"


def _calculate_uptime(time_service) -> float:
    """Calculate the agent's uptime in seconds."""
    if not time_service:
        return 0.0

    # Try to get uptime from time service status
    if hasattr(time_service, "get_status"):
        time_status = time_service.get_status()
        if hasattr(time_status, "uptime_seconds"):
            return time_status.uptime_seconds

    # Calculate uptime manually
    if hasattr(time_service, "_start_time") and hasattr(time_service, "now"):
        return (time_service.now() - time_service._start_time).total_seconds()

    return 0.0


def _count_wakeup_tasks(uptime: float) -> int:
    """Count completed WAKEUP tasks."""
    try:
        from ciris_engine.logic import persistence
        from ciris_engine.schemas.runtime.enums import TaskStatus

        completed_tasks = persistence.get_tasks_by_status(TaskStatus.COMPLETED)

        wakeup_prefixes = [
            "VERIFY_IDENTITY",
            "VALIDATE_INTEGRITY",
            "EVALUATE_RESILIENCE",
            "ACCEPT_INCOMPLETENESS",
            "EXPRESS_GRATITUDE",
        ]

        count = sum(1 for task in completed_tasks if any(task.task_id.startswith(prefix) for prefix in wakeup_prefixes))

        # If no wakeup tasks found but system has been running, assume standard cycle
        if count == 0 and uptime > MIN_UPTIME_FOR_DEFAULT_TASKS:
            return 5  # Standard wakeup cycle completes 5 tasks

        return count
    except Exception as e:
        logger.warning(f"Failed to count completed tasks: {e}")
        return 0


def _count_active_services(service_registry) -> tuple[int, dict]:
    """Count active services and get multi-provider service details."""
    multi_provider_count = 0
    multi_provider_services = {}

    if service_registry:
        from ciris_engine.schemas.runtime.enums import ServiceType

        for service_type in ServiceType:
            providers = service_registry.get_services_by_type(service_type)
            count = len(providers)
            if count > 0:
                multi_provider_count += count
                multi_provider_services[service_type.value] = {"providers": count, "type": "multi-provider"}

    # CIRIS has AT LEAST 19 service types:
    # Multi-provider services can have multiple instances + 12 singleton services
    services_active = multi_provider_count + 12

    return services_active, multi_provider_services


def _get_agent_identity_info(runtime) -> tuple[str, str]:
    """Get agent ID and name."""
    agent_id = "ciris_agent"
    agent_name = "CIRIS"

    if hasattr(runtime, "agent_identity") and runtime.agent_identity:
        agent_id = runtime.agent_identity.agent_id
        # Try to get name from various sources
        if hasattr(runtime.agent_identity, "name"):
            agent_name = runtime.agent_identity.name
        elif hasattr(runtime.agent_identity, "core_profile"):
            # Use first part of description or role as name
            agent_name = runtime.agent_identity.core_profile.description.split(".")[0]

    return agent_id, agent_name


@router.get("/status", response_model=SuccessResponse[AgentStatus])
async def get_status(request: Request, auth: AuthContext = Depends(require_observer)) -> SuccessResponse[AgentStatus]:
    """
    Agent status and cognitive state.

    Get comprehensive agent status including state, metrics, and current activity.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    try:
        # Get basic state information
        cognitive_state = _get_cognitive_state(runtime)
        time_service = getattr(request.app.state, "time_service", None)
        uptime = _calculate_uptime(time_service)
        messages_processed = _count_wakeup_tasks(uptime)

        # Get current task
        current_task = None
        task_scheduler = getattr(request.app.state, "task_scheduler", None)
        if task_scheduler and hasattr(task_scheduler, "get_current_task"):
            current_task = await task_scheduler.get_current_task()

        # Get resource usage
        memory_usage_mb = 0.0
        resource_monitor = getattr(request.app.state, "resource_monitor", None)
        if resource_monitor and hasattr(resource_monitor, "snapshot"):
            memory_usage_mb = float(resource_monitor.snapshot.memory_mb)

        # Count services
        service_registry = getattr(request.app.state, "service_registry", None)
        services_active, multi_provider_services = _count_active_services(service_registry)

        # Get identity
        agent_id, agent_name = _get_agent_identity_info(runtime)

        # Get version information
        from ciris_engine.constants import CIRIS_CODENAME, CIRIS_VERSION

        try:
            from version import __version__ as code_hash
        except ImportError:
            code_hash = None

        status = AgentStatus(
            agent_id=agent_id,
            name=agent_name,
            version=CIRIS_VERSION,
            codename=CIRIS_CODENAME,
            code_hash=code_hash,
            cognitive_state=cognitive_state,
            uptime_seconds=uptime,
            messages_processed=messages_processed,
            last_activity=datetime.now(timezone.utc),
            current_task=current_task,
            services_active=services_active,
            memory_usage_mb=memory_usage_mb,
            multi_provider_services=multi_provider_services,
        )

        return SuccessResponse(data=status)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identity", response_model=SuccessResponse[AgentIdentity])
async def get_identity(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AgentIdentity]:
    """
    Agent identity and capabilities.

    Get comprehensive agent identity including capabilities, tools, and permissions.
    """
    # Get memory service to query identity
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=ERROR_MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Query identity from graph
        from ciris_engine.schemas.services.graph_core import GraphScope
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(node_id="agent/identity", scope=GraphScope.IDENTITY, include_edges=False)

        nodes = await memory_service.recall(query)

        # Get identity data
        identity_data = {}
        if nodes:
            identity_node = nodes[0]
            identity_data = identity_node.attributes
        else:
            # Fallback to runtime identity
            runtime = getattr(request.app.state, "runtime", None)
            if runtime and hasattr(runtime, "agent_identity"):
                identity = runtime.agent_identity
                identity_data = {
                    "agent_id": identity.agent_id,
                    "name": getattr(identity, "name", identity.core_profile.description.split(".")[0]),
                    "purpose": getattr(identity, "purpose", identity.core_profile.description),
                    "created_at": identity.identity_metadata.created_at.isoformat(),
                    "lineage": {
                        "model": identity.identity_metadata.model,
                        "version": identity.identity_metadata.version,
                        "parent_id": getattr(identity.identity_metadata, "parent_id", None),
                        "creation_context": getattr(identity.identity_metadata, "creation_context", "default"),
                        "adaptations": getattr(identity.identity_metadata, "adaptations", []),
                    },
                    "variance_threshold": 0.2,
                }

        # Get capabilities

        # Get tool service for available tools
        tool_service = getattr(request.app.state, "tool_service", None)
        tools = []
        if tool_service:
            tools = await tool_service.list_tools()

        # Get handlers (these are the core action handlers)
        handlers = [
            "observe",
            "speak",
            "tool",
            "reject",
            "ponder",
            "defer",
            "memorize",
            "recall",
            "forget",
            "task_complete",
        ]

        # Get service availability
        services = ServiceAvailability()
        service_registry = getattr(request.app.state, "service_registry", None)
        if service_registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            for service_type in ServiceType:
                providers = service_registry.get_services_by_type(service_type)
                count = len(providers)
                # Map to service categories
                if "graph" in service_type.value.lower() or service_type.value == "MEMORY":
                    services.graph += count
                elif service_type.value in ["LLM", "SECRETS"]:
                    services.core += count
                elif service_type.value in [
                    "TIME",
                    "SHUTDOWN",
                    "INITIALIZATION",
                    "VISIBILITY",
                    "AUTHENTICATION",
                    "RESOURCE_MONITOR",
                    "RUNTIME_CONTROL",
                ]:
                    services.infrastructure += count
                elif service_type.value == "WISE_AUTHORITY":
                    services.governance += count
                else:
                    services.special += count

        # Get permissions (agent's core capabilities)
        permissions = ["communicate", "use_tools", "access_memory", "observe_environment", "learn", "adapt"]

        # Build response
        lineage_data = identity_data.get("lineage", {})
        lineage = AgentLineage(
            model=lineage_data.get("model", "unknown"),
            version=lineage_data.get("version", "1.0"),
            parent_id=lineage_data.get("parent_id"),
            creation_context=lineage_data.get("creation_context", "default"),
            adaptations=lineage_data.get("adaptations", []),
        )

        response = AgentIdentity(
            agent_id=identity_data.get("agent_id", "ciris_agent"),
            name=identity_data.get("name", "CIRIS"),
            purpose=identity_data.get("purpose", "Autonomous AI agent"),
            created_at=datetime.fromisoformat(identity_data.get("created_at", datetime.now(timezone.utc).isoformat())),
            lineage=lineage,
            variance_threshold=identity_data.get("variance_threshold", 0.2),
            tools=tools,
            handlers=handlers,
            services=services,
            permissions=permissions,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _convert_to_channel_info(ch, adapter_type: str) -> ChannelInfo:
    """Convert adapter channel data to ChannelInfo format."""
    if hasattr(ch, "channel_id"):
        # Pydantic model format
        return ChannelInfo(
            channel_id=ch.channel_id,
            channel_type=getattr(ch, "channel_type", adapter_type),
            display_name=getattr(ch, "display_name", ch.channel_id),
            is_active=getattr(ch, "is_active", True),
            created_at=getattr(ch, "created_at", None),
            last_activity=getattr(ch, "last_activity", None),
            message_count=getattr(ch, "message_count", 0),
        )
    else:
        # Dict format (legacy)
        return ChannelInfo(
            channel_id=ch.get("channel_id", ""),
            channel_type=ch.get("channel_type", adapter_type),
            display_name=ch.get("display_name", ch.get("channel_id", "")),
            is_active=ch.get("is_active", True),
            created_at=ch.get("created_at"),
            last_activity=ch.get("last_activity"),
            message_count=ch.get("message_count", 0),
        )


async def _get_channels_from_adapter(adapter, adapter_type: str) -> List[ChannelInfo]:
    """Get channels from a single adapter."""
    channels = []
    if hasattr(adapter, "get_active_channels"):
        try:
            adapter_channels = await adapter.get_active_channels()
            for ch in adapter_channels:
                channels.append(_convert_to_channel_info(ch, adapter_type))
        except Exception as e:
            logger.error(f"Error getting channels from adapter {adapter_type}: {e}")
    return channels


async def _get_channels_from_bootstrap_adapters(runtime) -> List[ChannelInfo]:
    """Get channels from bootstrap adapters."""
    channels = []
    if runtime and hasattr(runtime, "adapters"):
        logger.info(f"Checking {len(runtime.adapters)} bootstrap adapters for channels")
        for adapter in runtime.adapters:
            adapter_type = adapter.__class__.__name__.lower().replace("platform", "")
            channels.extend(await _get_channels_from_adapter(adapter, adapter_type))
    return channels


async def _get_channels_from_dynamic_adapters(runtime, request) -> List[ChannelInfo]:
    """Get channels from dynamically loaded adapters."""
    channels = []

    # Get main runtime control service
    control_service = getattr(request.app.state, "main_runtime_control_service", None)

    # Fallback to service registry
    if not control_service and runtime and hasattr(runtime, "service_registry") and runtime.service_registry:
        from ciris_engine.schemas.runtime.enums import ServiceType

        providers = runtime.service_registry.get_services_by_type(ServiceType.RUNTIME_CONTROL)
        if providers:
            control_service = providers[0]

    if control_service and hasattr(control_service, "adapter_manager") and control_service.adapter_manager:
        adapter_manager = control_service.adapter_manager
        if hasattr(adapter_manager, "loaded_adapters"):
            for adapter_id, instance in adapter_manager.loaded_adapters.items():
                adapter_channels = await _get_channels_from_adapter(instance.adapter, instance.adapter_type)
                # Filter out duplicates
                for ch in adapter_channels:
                    if not any(existing.channel_id == ch.channel_id for existing in channels):
                        channels.append(ch)

    return channels


def _add_default_api_channels(channels: List[ChannelInfo], request: Request, auth: AuthContext) -> None:
    """Add default API channels if not already present."""
    # Default API channel
    api_host = getattr(request.app.state, "api_host", "127.0.0.1")
    api_port = getattr(request.app.state, "api_port", "8080")
    api_channel_id = f"api_{api_host}_{api_port}"

    if not any(ch.channel_id == api_channel_id for ch in channels):
        channels.append(
            ChannelInfo(
                channel_id=api_channel_id,
                channel_type="api",
                display_name=f"API Channel ({api_host}:{api_port})",
                is_active=True,
                created_at=None,
                last_activity=datetime.now(timezone.utc),
                message_count=0,
            )
        )

    # User-specific API channel
    user_channel_id = f"api_{auth.user_id}"
    if not any(ch.channel_id == user_channel_id for ch in channels):
        channels.append(
            ChannelInfo(
                channel_id=user_channel_id,
                channel_type="api",
                display_name=f"API Channel ({auth.user_id})",
                is_active=True,
                created_at=None,
                last_activity=None,
                message_count=0,
            )
        )


@router.get("/channels", response_model=SuccessResponse[ChannelList])
async def get_channels(request: Request, auth: AuthContext = Depends(require_observer)) -> SuccessResponse[ChannelList]:
    """
    List active communication channels.

    Get all channels where the agent is currently active or has been active.
    """
    try:
        channels = []
        runtime = getattr(request.app.state, "runtime", None)

        # Get channels from bootstrap adapters
        channels.extend(await _get_channels_from_bootstrap_adapters(runtime))

        # Get channels from dynamically loaded adapters
        dynamic_channels = await _get_channels_from_dynamic_adapters(runtime, request)
        channels.extend(dynamic_channels)

        # Add default API channels
        _add_default_api_channels(channels, request, auth)

        # Sort channels by type and then by id
        channels.sort(key=lambda x: (x.channel_type, x.channel_id))

        channel_list = ChannelList(channels=channels, total_count=len(channels))
        return SuccessResponse(data=channel_list)

    except Exception as e:
        logger.error(f"Failed to get channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Helper function to notify interact responses
async def notify_interact_response(message_id: str, content: str) -> None:
    """Notify waiting interact requests of responses."""
    if message_id in _response_events:
        _message_responses[message_id] = content
        _response_events[message_id].set()


# WebSocket endpoint for streaming
from fastapi import WebSocket, WebSocketDisconnect


@router.websocket("/stream")
async def websocket_stream(
    websocket: WebSocket,
) -> None:
    """
    WebSocket endpoint for real-time updates.

    Clients can subscribe to different channels:
    - messages: Agent messages and responses
    - telemetry: Real-time metrics
    - reasoning: Reasoning traces
    - logs: System logs
    """
    # Extract authorization header from WebSocket request
    authorization = websocket.headers.get("authorization")

    if not authorization:
        await websocket.close(code=1008, reason="Missing authorization header")
        return

    # Get auth service from app state
    auth_service = getattr(websocket.app.state, "auth_service", None)
    if not auth_service:
        await websocket.close(code=1011, reason="Auth service not initialized")
        return

    # Validate bearer token
    if not authorization.startswith("Bearer "):
        await websocket.close(code=1008, reason="Invalid authorization format")
        return

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # Validate API key
    key_info = auth_service.validate_api_key(api_key)
    if not key_info:
        await websocket.close(code=1008, reason="Invalid API key")
        return

    # Create auth context
    auth_context = AuthContext(
        user_id=key_info.user_id,
        role=key_info.role,
        permissions=ROLE_PERMISSIONS.get(key_info.role, set()),
        api_key_id=auth_service._get_key_id(api_key),
        authenticated_at=datetime.now(timezone.utc),
    )

    # Check minimum role requirement (OBSERVER)
    if not auth_context.role.has_permission(UserRole.OBSERVER):
        await websocket.close(code=1008, reason="Insufficient permissions")
        return

    await websocket.accept()
    client_id = f"ws_{id(websocket)}"

    # Get communication service to register WebSocket
    comm_service = getattr(websocket.app.state, "communication_service", None)
    if comm_service and hasattr(comm_service, "register_websocket"):
        comm_service.register_websocket(client_id, websocket)

    subscribed_channels = set(["messages"])  # Default subscription

    try:
        while True:
            # Receive and process client messages
            data = await websocket.receive_json()

            if data.get("action") == "subscribe":
                channels = data.get("channels", [])
                subscribed_channels.update(channels)
                await websocket.send_json(
                    {
                        "type": "subscription_update",
                        "channels": list(subscribed_channels),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

            elif data.get("action") == "unsubscribe":
                channels = data.get("channels", [])
                subscribed_channels.difference_update(channels)
                await websocket.send_json(
                    {
                        "type": "subscription_update",
                        "channels": list(subscribed_channels),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

            elif data.get("action") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})

    except WebSocketDisconnect:
        # Clean up on disconnect
        if comm_service and hasattr(comm_service, "unregister_websocket"):
            comm_service.unregister_websocket(client_id)
        logger.info(f"WebSocket client {client_id} disconnected")
