"""
Batch context builder for optimizing system snapshot generation.
Separates per-batch vs per-thought operations for performance.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from ciris_engine.logic import persistence
from ciris_engine.schemas.infrastructure.identity_variance import IdentityData
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import ContinuitySummary, SystemSnapshot, TaskSummary, TelemetrySummary
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

logger = logging.getLogger(__name__)


async def create_minimal_batch_context(
    memory_service: Optional[Any] = None,
    secrets_service: Optional[Any] = None,
    service_registry: Optional[Any] = None,
    resource_monitor: Optional[Any] = None,
    telemetry_service: Optional[Any] = None,
    runtime: Optional[Any] = None,
) -> "BatchContextData":
    """
    Create minimal batch context for single-thought processing.

    This is a lightweight version of prefetch_batch_context() that creates
    batch data on-demand for individual thoughts when batch processing is
    not being used (e.g., API interactions, single thoughts).

    Uses the same data fetching logic as prefetch_batch_context() but is
    called inline for single thoughts instead of being pre-fetched.
    """
    logger.debug("[MINIMAL BATCH] Creating minimal batch context for single thought")
    # Reuse the full prefetch logic - it's already optimized
    return await prefetch_batch_context(
        memory_service=memory_service,
        secrets_service=secrets_service,
        service_registry=service_registry,
        resource_monitor=resource_monitor,
        telemetry_service=telemetry_service,
        runtime=runtime,
    )


class BatchContextData:
    """Pre-fetched data that's the same for all thoughts in a batch."""

    def __init__(self) -> None:
        # Agent identity - using IdentityData model per SystemSnapshot definition
        self.agent_identity: Optional[IdentityData] = None
        self.identity_purpose: Optional[str] = None
        self.identity_capabilities: List[str] = []
        self.identity_restrictions: List[str] = []
        # Task tracking
        self.recent_tasks: List[TaskSummary] = []
        self.top_tasks: List[TaskSummary] = []
        # Service health - bool for is_healthy per SystemSnapshot
        self.service_health: Dict[str, bool] = {}
        # Circuit breaker - string state per SystemSnapshot
        self.circuit_breaker_status: Dict[str, str] = {}
        # Resource alerts are strings
        self.resource_alerts: List[str] = []
        # Telemetry uses the schema
        self.telemetry_summary: Optional[TelemetrySummary] = None
        # Continuity uses the schema
        self.continuity_summary: Optional[ContinuitySummary] = None
        # Secrets snapshot with typed fields
        self.secrets_snapshot: Dict[str, Union[List[str], int]] = {}
        # Shutdown context from runtime.extended
        from ciris_engine.schemas.runtime.extended import ShutdownContext

        self.shutdown_context: Optional[ShutdownContext] = None


async def prefetch_batch_context(
    memory_service: Optional[Any] = None,
    secrets_service: Optional[Any] = None,
    service_registry: Optional[Any] = None,
    resource_monitor: Optional[Any] = None,
    telemetry_service: Optional[Any] = None,
    runtime: Optional[Any] = None,
) -> BatchContextData:
    """Pre-fetch all data that's common across a batch of thoughts."""

    logger.debug("[DEBUG DB TIMING] Starting batch context prefetch")
    batch_data = BatchContextData()

    # 1. Agent Identity (single query)
    if memory_service:
        try:
            logger.debug("[DEBUG DB TIMING] Batch: fetching agent identity")
            identity_query = MemoryQuery(
                node_id="agent/identity", scope=GraphScope.IDENTITY, type=NodeType.AGENT, include_edges=False, depth=1
            )
            identity_nodes = await memory_service.recall(identity_query)
            identity_result = identity_nodes[0] if identity_nodes else None

            if identity_result and identity_result.attributes:
                attrs = identity_result.attributes
                # Convert Pydantic model to dict if needed
                if hasattr(attrs, "model_dump"):
                    attrs = attrs.model_dump()
                if isinstance(attrs, dict):
                    # Create IdentityData instance from attributes
                    try:
                        # Map role_description → role for IdentityData model
                        identity_dict = {
                            "agent_id": attrs.get("agent_id", "unknown"),
                            "description": attrs.get("description", ""),
                            "role": attrs.get("role") or attrs.get("role_description", ""),
                            "trust_level": attrs.get("trust_level", 0.5),
                            "stewardship": attrs.get("stewardship"),
                        }
                        batch_data.agent_identity = IdentityData(**identity_dict)
                    except Exception as e:
                        logger.warning(f"Failed to create IdentityData from attributes: {e}")
                        # Keep as None - will be handled when building SystemSnapshot
                        batch_data.agent_identity = None

                    # Extract specific fields for structured access
                    batch_data.identity_purpose = attrs.get("role_description", "")
                    batch_data.identity_capabilities = attrs.get("permitted_actions", [])
                    batch_data.identity_restrictions = attrs.get("restricted_capabilities", [])
        except Exception as e:
            logger.warning(f"Failed to retrieve agent identity: {e}")

    # 2. Recent and Top Tasks (single query each)
    logger.debug("[DEBUG DB TIMING] Batch: fetching recent completed tasks")
    db_recent_tasks = persistence.get_recent_completed_tasks("default", 10)

    logger.debug("[DEBUG DB TIMING] Batch: fetching top tasks")
    db_top_tasks = persistence.get_top_tasks("default", 10)

    # Convert to TaskSummary
    from pydantic import BaseModel

    for t_obj in db_recent_tasks:
        if isinstance(t_obj, BaseModel):
            batch_data.recent_tasks.append(
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

    for t_obj in db_top_tasks:
        if isinstance(t_obj, BaseModel):
            batch_data.top_tasks.append(
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

    # 3. Service Health (if needed)
    if service_registry:
        logger.debug("[DEBUG DB TIMING] Batch: collecting service health")
        try:
            registry_info = service_registry.get_provider_info()

            # Check handler-specific services
            for handler, service_types in registry_info.get("handlers", {}).items():
                for service_type, services in service_types.items():
                    for service in services:
                        service_name = f"{handler}.{service_type}"
                        # Use is_healthy() method (async)
                        if hasattr(service, "is_healthy"):
                            batch_data.service_health[service_name] = await service.is_healthy()
                        # Get circuit breaker status if available
                        if hasattr(service, "get_circuit_breaker_status"):
                            batch_data.circuit_breaker_status[service_name] = service.get_circuit_breaker_status()

            # Check global services
            global_services = registry_info.get("global_services", {})
            for service_type, services in global_services.items():
                for service in services:
                    service_name = f"global.{service_type}"
                    # Use is_healthy() method (async)
                    if hasattr(service, "is_healthy"):
                        batch_data.service_health[service_name] = await service.is_healthy()
                    # Get circuit breaker status if available
                    if hasattr(service, "get_circuit_breaker_status"):
                        batch_data.circuit_breaker_status[service_name] = service.get_circuit_breaker_status()
        except Exception as e:
            logger.warning(f"Failed to collect service health: {e}")

    # 4. Resource Alerts
    if resource_monitor:
        logger.debug("[DEBUG DB TIMING] Batch: checking resource monitor")
        try:
            snapshot = resource_monitor.snapshot
            if snapshot.critical:
                for alert in snapshot.critical:
                    batch_data.resource_alerts.append(
                        f"🚨 CRITICAL! RESOURCE LIMIT BREACHED! {alert} - REJECT OR DEFER ALL TASKS!"
                    )
            if not snapshot.healthy:
                batch_data.resource_alerts.append(
                    "🚨 CRITICAL! SYSTEM UNHEALTHY! RESOURCE LIMITS EXCEEDED - IMMEDIATE ACTION REQUIRED!"
                )
        except Exception as e:
            logger.error(f"Failed to get resource alerts: {e}")
            batch_data.resource_alerts.append(f"🚨 CRITICAL! FAILED TO CHECK RESOURCES: {str(e)}")

    # 5. Telemetry Summary
    if telemetry_service:
        logger.debug("[DEBUG DB TIMING] Batch: getting telemetry summary")
        try:
            batch_data.telemetry_summary = await telemetry_service.get_telemetry_summary()
        except Exception as e:
            logger.warning(f"Failed to get telemetry summary: {e}")

        # 5b. Continuity Summary
        if hasattr(telemetry_service, "get_continuity_summary"):
            logger.debug("[DEBUG DB TIMING] Batch: getting continuity summary")
            try:
                batch_data.continuity_summary = await telemetry_service.get_continuity_summary()
            except Exception as e:
                logger.warning(f"Failed to get continuity summary: {e}")

    # 6. Secrets Snapshot
    if secrets_service:
        logger.debug("[DEBUG DB TIMING] Batch: building secrets snapshot")
        from typing import cast

        from .secrets_snapshot import build_secrets_snapshot

        batch_data.secrets_snapshot = cast(
            Dict[str, Union[List[str], int]], await build_secrets_snapshot(secrets_service)
        )

    # 7. Shutdown Context
    if runtime and hasattr(runtime, "current_shutdown_context"):
        batch_data.shutdown_context = runtime.current_shutdown_context

    logger.debug("[DEBUG DB TIMING] Batch context prefetch complete")
    return batch_data


async def build_system_snapshot_with_batch(
    task: Optional[Task],
    thought: Any,
    batch_data: Optional[BatchContextData] = None,
    memory_service: Optional[Any] = None,
    graphql_provider: Optional[Any] = None,
    time_service: Any = None,  # REQUIRED - will fail fast and loud if None
    resource_monitor: Any = None,  # REQUIRED - mission critical system
    # Additional services for creating batch context on-demand
    secrets_service: Optional[Any] = None,
    service_registry: Optional[Any] = None,
    telemetry_service: Optional[Any] = None,
    runtime: Optional[Any] = None,
) -> SystemSnapshot:
    """
    Build system snapshot using batch data (pre-fetched or created on-demand).

    If batch_data is provided, uses the pre-fetched data (batch processing).
    If batch_data is None, creates minimal batch context on-demand (single thought).

    This unified approach ensures consistent snapshot building regardless of
    whether processing a batch of thoughts or a single thought.
    """

    from ciris_engine.schemas.runtime.system_context import ThoughtSummary

    from .system_snapshot_helpers import _get_localized_times

    # Create batch context on-demand if not provided
    if batch_data is None:
        logger.info(
            f"[UNIFIED BATCH] No batch context provided for thought {getattr(thought, 'thought_id', 'unknown')}, creating on-demand"
        )
        batch_data = await create_minimal_batch_context(
            memory_service=memory_service,
            secrets_service=secrets_service,
            service_registry=service_registry,
            resource_monitor=resource_monitor,
            telemetry_service=telemetry_service,
            runtime=runtime,
        )
        logger.info(
            f"[UNIFIED BATCH] Created minimal batch context for thought {getattr(thought, 'thought_id', 'unknown')}"
        )
    else:
        logger.info(
            f"[UNIFIED BATCH] Using pre-fetched batch data for thought {getattr(thought, 'thought_id', 'unknown')}"
        )

    # Per-thought data
    thought_summary = None
    if thought:
        status_val = getattr(thought, "status", None)
        if status_val is not None and hasattr(status_val, "value"):
            status_val = status_val.value
        elif status_val is not None:
            status_val = str(status_val)

        # ThoughtSummary requires thought_id to be a string (not None)
        thought_id = getattr(thought, "thought_id", None)
        if thought_id is None:
            thought_id = "unknown"

        thought_summary = ThoughtSummary(
            thought_id=thought_id,
            content=getattr(thought, "content", None),
            status=status_val,
            source_task_id=getattr(thought, "source_task_id", None),
            thought_type=getattr(thought, "thought_type", None),
            thought_depth=getattr(thought, "thought_depth", None),
        )

    # Channel context (per-thought if different channels)
    channel_id = None
    channel_context = None

    # First, check for existing channel_context object in task.context.system_snapshot
    if task and hasattr(task, "context") and task.context:
        if (
            hasattr(task.context, "system_snapshot")
            and task.context.system_snapshot
            and hasattr(task.context.system_snapshot, "channel_context")
            and task.context.system_snapshot.channel_context
        ):
            from ciris_engine.schemas.runtime.system_context import ChannelContext

            # Validate it's a ChannelContext object (fail fast on wrong type)
            if isinstance(task.context.system_snapshot.channel_context, ChannelContext):
                channel_context = task.context.system_snapshot.channel_context
                logger.info(
                    f"[UNIFIED BATCH] Extracted existing channel_context: {channel_context.channel_id} ({channel_context.channel_type})"
                )

    # Extract channel_id - try multiple sources in priority order
    if task:
        # First try: task.channel_id (most common)
        if hasattr(task, "channel_id") and task.channel_id:
            channel_id = str(task.channel_id)
        # Second try: task.context.channel_id
        elif (
            hasattr(task, "context")
            and task.context
            and hasattr(task.context, "channel_id")
            and task.context.channel_id
        ):
            channel_id = str(task.context.channel_id)
        # Third try: task.context.system_snapshot.channel_id (legacy)
        elif (
            hasattr(task, "context")
            and task.context
            and hasattr(task.context, "system_snapshot")
            and task.context.system_snapshot
            and hasattr(task.context.system_snapshot, "channel_id")
            and task.context.system_snapshot.channel_id
        ):
            channel_id = str(task.context.system_snapshot.channel_id)

    # If no channel_id from task, try thought.context.channel_id
    if (
        not channel_id
        and thought
        and hasattr(thought, "context")
        and thought.context
        and hasattr(thought.context, "channel_id")
        and thought.context.channel_id
    ):
        channel_id = str(thought.context.channel_id)

    # Only query channel context if we have a channel_id
    if channel_id and memory_service:
        logger.debug(f"[DEBUG DB TIMING] Per-thought: querying channel context for {channel_id}")
        try:
            query = MemoryQuery(
                node_id=f"channel/{channel_id}",
                scope=GraphScope.LOCAL,
                type=NodeType.CHANNEL,
                include_edges=False,
                depth=1,
            )
            await memory_service.recall(query)
        except Exception as e:
            logger.debug(f"Failed to retrieve channel context: {e}")

    # Current task summary
    current_task_summary = None
    if task:
        from pydantic import BaseModel

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

    # GraphQL user enrichment (if available)
    user_profiles = []
    if graphql_provider:
        from ciris_engine.schemas.runtime.system_context import UserProfile

        enriched_context = await graphql_provider.enrich_context(task, thought)
        if enriched_context and enriched_context.user_profiles:
            # Convert GraphQLUserProfile to UserProfile
            for name, graphql_profile in enriched_context.user_profiles:
                # Extract consent attributes from GraphQL profile
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

                user_profiles.append(
                    UserProfile(
                        user_id=name,
                        display_name=graphql_profile.nick or name,
                        created_at=datetime.now(timezone.utc),
                        preferred_language="en",
                        timezone="UTC",
                        communication_style="formal",
                        trust_level=graphql_profile.trust_score or 0.5,
                        last_interaction=(
                            datetime.fromisoformat(graphql_profile.last_seen) if graphql_profile.last_seen else None
                        ),
                        is_wa=any(attr.key == "is_wa" and attr.value == "true" for attr in graphql_profile.attributes),
                        permissions=[attr.value for attr in graphql_profile.attributes if attr.key == "permission"],
                        restrictions=[attr.value for attr in graphql_profile.attributes if attr.key == "restriction"],
                        consent_stream=consent_stream,
                        consent_expires_at=consent_expires_at,
                        partnership_requested_at=partnership_requested_at,
                        partnership_approved=consent_attrs.get("partnership_approved", "false").lower() == "true",
                    )
                )

    # Memory graph user enrichment (if available)
    if memory_service:
        from .system_snapshot_helpers import _enrich_user_profiles, _extract_user_ids_from_context

        user_ids_to_enrich = _extract_user_ids_from_context(task, thought)
        if user_ids_to_enrich:
            logger.debug(f"[DEBUG BATCH] Enriching {len(user_ids_to_enrich)} user profiles: {user_ids_to_enrich}")
            user_profiles = await _enrich_user_profiles(memory_service, user_ids_to_enrich, channel_id, user_profiles)

    # Collect adapter channels and tools (if runtime available)
    adapter_channels = {}
    available_tools = {}
    context_enrichment_results = {}
    if runtime:
        from .system_snapshot_helpers import (
            _collect_adapter_channels,
            _collect_available_tools,
            _run_context_enrichment_tools,
        )

        adapter_channels = await _collect_adapter_channels(runtime)
        available_tools = await _collect_available_tools(runtime)
        # Run context enrichment tools (e.g., ha_list_entities)
        context_enrichment_results = await _run_context_enrichment_tools(runtime, available_tools)

    # Get queue status for system_counts
    queue_status = persistence.get_queue_status()
    system_counts = {
        "total_tasks": queue_status.total_tasks,
        "total_thoughts": queue_status.total_thoughts,
        "pending_tasks": queue_status.pending_tasks,
        "pending_thoughts": queue_status.pending_thoughts + queue_status.processing_thoughts,
    }

    # Get version information
    from ciris_engine.constants import CIRIS_CODENAME, CIRIS_VERSION

    try:
        from version import __version__ as code_hash
    except ImportError:
        code_hash = ""

    # Build snapshot with batch data
    return SystemSnapshot(
        # Channel context fields
        channel_context=channel_context,
        channel_id=channel_id,
        # Current processing state
        current_task_details=current_task_summary,
        current_thought_summary=thought_summary,
        # System overview
        system_counts=system_counts,
        top_pending_tasks_summary=batch_data.top_tasks,
        recently_completed_tasks_summary=batch_data.recent_tasks,
        # Agent identity fields - convert None to empty dict per schema requirement
        agent_identity=batch_data.agent_identity if batch_data.agent_identity is not None else {},
        identity_purpose=batch_data.identity_purpose or "",
        identity_capabilities=batch_data.identity_capabilities,
        identity_restrictions=batch_data.identity_restrictions,
        # Version information
        agent_version=CIRIS_VERSION,
        agent_codename=CIRIS_CODENAME,
        agent_code_hash=code_hash,
        # Security fields
        detected_secrets=batch_data.secrets_snapshot.get("detected_secrets", []) if batch_data.secrets_snapshot else [],
        secrets_filter_version=(
            batch_data.secrets_snapshot.get("secrets_filter_version", 0) if batch_data.secrets_snapshot else 0
        ),
        total_secrets_stored=(
            batch_data.secrets_snapshot.get("total_secrets_stored", 0) if batch_data.secrets_snapshot else 0
        ),
        # Service health fields
        service_health=batch_data.service_health,
        circuit_breaker_status=batch_data.circuit_breaker_status,
        resource_alerts=batch_data.resource_alerts,
        # Other fields
        shutdown_context=batch_data.shutdown_context,
        telemetry_summary=batch_data.telemetry_summary,
        continuity_summary=batch_data.continuity_summary,
        user_profiles=user_profiles,  # Enriched user profiles from GraphQL and memory graph
        adapter_channels=adapter_channels,  # Available channels by adapter
        available_tools=available_tools,  # Available tools by adapter
        context_enrichment_results=context_enrichment_results,  # Pre-run tool results for context
        # Get localized times - FAILS FAST AND LOUD if time_service is None
        **{
            f"current_time_{key}": value
            for key, value in _get_localized_times(time_service).model_dump().items()
            if key in ["utc", "london", "chicago", "tokyo"]
        },
    )
