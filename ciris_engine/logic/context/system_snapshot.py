import json
import logging
from datetime import datetime, timezone
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
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.services.runtime_control import CircuitBreakerStatus

from .secrets_snapshot import build_secrets_snapshot
from .system_snapshot_helpers import (
    _build_current_task_summary,
    _collect_adapter_channels,
    _collect_available_tools,
    _collect_resource_alerts,
    _collect_service_health,
    _enrich_user_profiles,
    _extract_agent_identity,
    _extract_thought_summary,
    _extract_user_ids_from_context,
    _get_localized_times,
    _get_recent_tasks,
    _get_secrets_data,
    _get_shutdown_context,
    _get_telemetry_summary,
    _get_top_tasks,
    _resolve_channel_context,
)

logger = logging.getLogger(__name__)


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return str(obj)


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
    time_service: Any = None,  # REQUIRED - will fail fast and loud if None
) -> SystemSnapshot:
    """Build system snapshot for the thought.

    CRITICAL: This function FAILS FAST AND LOUD on any type safety violation.
    No fallbacks, no graceful degradation - if the data is wrong, we crash.

    This ensures we catch type safety issues immediately in development/testing
    rather than silently corrupting the agent's context in production.

    Philosophy: Better to crash visibly than operate with invalid data.
    """
    from ciris_engine.schemas.runtime.system_context import TaskSummary, ThoughtSummary

    # Extract thought summary using helper function
    thought_summary = _extract_thought_summary(thought)

    # Mission-critical channel_id and channel_context resolution using helper function
    channel_id, channel_context = await _resolve_channel_context(task, thought, memory_service)

    # Retrieve agent identity from graph using helper function
    identity_data, identity_purpose, identity_capabilities, identity_restrictions = await _extract_agent_identity(
        memory_service
    )

    # Get task data using helper functions
    recent_tasks_list = _get_recent_tasks(10)
    top_tasks_list = _get_top_tasks(10)
    current_task_summary = _build_current_task_summary(task)

    # Get system context data using helper functions
    secrets_data = await _get_secrets_data(secrets_service)
    shutdown_context = _get_shutdown_context(runtime)
    resource_alerts = _collect_resource_alerts(resource_monitor)
    service_health, circuit_breaker_status = await _collect_service_health(service_registry)
    telemetry_summary = await _get_telemetry_summary(telemetry_service)

    # Get system data using helper functions
    adapter_channels = await _collect_adapter_channels(runtime)
    available_tools = await _collect_available_tools(runtime)

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
        # Get localized times - FAILS FAST AND LOUD if time_service is None
        **{f"current_time_{key}": value for key, value in _get_localized_times(time_service).items()},
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
                # Extract consent attributes from GraphQL profile (v1.4.6)
                consent_attrs = {attr.key: attr.value for attr in graphql_profile.attributes}
                consent_stream = consent_attrs.get("consent_stream", "TEMPORARY")
                consent_expires_at = None
                if "consent_expires_at" in consent_attrs:
                    try:
                        consent_expires_at = datetime.fromisoformat(consent_attrs["consent_expires_at"])
                    except (ValueError, TypeError):
                        pass
                partnership_requested_at = None
                if "partnership_requested_at" in consent_attrs:
                    try:
                        partnership_requested_at = datetime.fromisoformat(consent_attrs["partnership_requested_at"])
                    except (ValueError, TypeError):
                        pass

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
                        # Consent relationship state (v1.4.6)
                        consent_stream=consent_stream,
                        consent_expires_at=consent_expires_at,
                        partnership_requested_at=partnership_requested_at,
                        partnership_approved=consent_attrs.get("partnership_approved", "false").lower() == "true",
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

    # Enrich user profiles from memory graph using helper functions
    if memory_service:
        # Extract user IDs from ALL available sources and enrich profiles
        user_ids_to_enrich = _extract_user_ids_from_context(task, thought)
        existing_profiles = context_data.get("user_profiles", [])
        enriched_profiles = await _enrich_user_profiles(
            memory_service, user_ids_to_enrich, channel_id, existing_profiles
        )

        # Update context data with enriched profiles
        if enriched_profiles:
            context_data["user_profiles"] = enriched_profiles
            # Log user profile context size
            profiles_bytes = len(json.dumps([p.model_dump() for p in enriched_profiles], default=json_serial))
            logger.info(
                f"[CONTEXT BUILD] {len(enriched_profiles)} User Profiles queried - {profiles_bytes:,} bytes added to context"
            )

    # Log channel context size
    if "channel_context" in context_data and context_data["channel_context"]:
        channel_bytes = len(
            json.dumps(
                (
                    context_data["channel_context"].model_dump()
                    if hasattr(context_data["channel_context"], "model_dump")
                    else context_data["channel_context"]
                ),
                default=json_serial,
            )
        )
        logger.info(f"[CONTEXT BUILD] 1 Channel queried - {channel_bytes:,} bytes added to context")

    # Create the snapshot - FAIL FAST AND LOUD if there's any problem
    snapshot = SystemSnapshot(**context_data)

    # Calculate and log total snapshot size
    snapshot_json = snapshot.model_dump_json()
    snapshot_bytes = len(snapshot_json)

    # Check for any validation errors or missing critical data
    errors = []
    if not context_data.get("user_profiles"):
        errors.append("No user profiles")
    if not context_data.get("channel_context"):
        errors.append("No channel context")

    if errors:
        logger.warning(
            f"[CONTEXT BUILD] System Snapshot built with {snapshot_bytes:,} bytes total, WARNINGS: {', '.join(errors)}"
        )
    else:
        logger.info(f"[CONTEXT BUILD] System Snapshot built with {snapshot_bytes:,} bytes total, no errors")

    # Note: GraphTelemetryService doesn't need update_system_snapshot
    # as it stores telemetry data directly in the graph

    return snapshot
