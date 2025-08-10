"""
Batch context builder for optimizing system snapshot generation.
Separates per-batch vs per-thought operations for performance.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from ciris_engine.logic import persistence
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, TaskSummary, TelemetrySummary
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

logger = logging.getLogger(__name__)


class BatchContextData:
    """Pre-fetched data that's the same for all thoughts in a batch."""

    def __init__(self) -> None:
        # Agent identity - using typed values per SystemSnapshot definition
        self.agent_identity: Dict[str, Union[str, int, float, bool, list, dict]] = {}
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

    logger.info("[DEBUG DB TIMING] Starting batch context prefetch")
    batch_data = BatchContextData()

    # 1. Agent Identity (single query)
    if memory_service:
        try:
            logger.info("[DEBUG DB TIMING] Batch: fetching agent identity")
            identity_query = MemoryQuery(
                node_id="agent/identity", scope=GraphScope.IDENTITY, type=NodeType.AGENT, include_edges=False, depth=1
            )
            identity_nodes = await memory_service.recall(identity_query)
            identity_result = identity_nodes[0] if identity_nodes else None

            if identity_result and identity_result.attributes:
                attrs = identity_result.attributes
                if isinstance(attrs, dict):
                    batch_data.agent_identity = {
                        "agent_id": attrs.get("agent_id", ""),
                        "description": attrs.get("description", ""),
                        "role": attrs.get("role_description", ""),
                        "trust_level": attrs.get("trust_level", 0.5),
                    }
                    batch_data.identity_purpose = attrs.get("role_description", "")
                    batch_data.identity_capabilities = attrs.get("permitted_actions", [])
                    batch_data.identity_restrictions = attrs.get("restricted_capabilities", [])
        except Exception as e:
            logger.warning(f"Failed to retrieve agent identity: {e}")

    # 2. Recent and Top Tasks (single query each)
    logger.info("[DEBUG DB TIMING] Batch: fetching recent completed tasks")
    db_recent_tasks = persistence.get_recent_completed_tasks(10)

    logger.info("[DEBUG DB TIMING] Batch: fetching top tasks")
    db_top_tasks = persistence.get_top_tasks(10)

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
        logger.info("[DEBUG DB TIMING] Batch: collecting service health")
        try:
            registry_info = service_registry.get_provider_info()

            # Check handler-specific services
            for handler, service_types in registry_info.get("handlers", {}).items():
                for service_type, services in service_types.items():
                    for service in services:
                        if hasattr(service, "get_health_status"):
                            service_name = f"{handler}.{service_type}"
                            batch_data.service_health[service_name] = await service.get_health_status()
                        if hasattr(service, "get_circuit_breaker_status"):
                            service_name = f"{handler}.{service_type}"
                            batch_data.circuit_breaker_status[service_name] = service.get_circuit_breaker_status()
        except Exception as e:
            logger.warning(f"Failed to collect service health: {e}")

    # 4. Resource Alerts
    if resource_monitor:
        logger.info("[DEBUG DB TIMING] Batch: checking resource monitor")
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
        logger.info("[DEBUG DB TIMING] Batch: getting telemetry summary")
        try:
            batch_data.telemetry_summary = await telemetry_service.get_telemetry_summary()
        except Exception as e:
            logger.warning(f"Failed to get telemetry summary: {e}")

    # 6. Secrets Snapshot
    if secrets_service:
        logger.info("[DEBUG DB TIMING] Batch: building secrets snapshot")
        from .secrets_snapshot import build_secrets_snapshot

        batch_data.secrets_snapshot = await build_secrets_snapshot(secrets_service)

    # 7. Shutdown Context
    if runtime and hasattr(runtime, "current_shutdown_context"):
        batch_data.shutdown_context = runtime.current_shutdown_context

    logger.info("[DEBUG DB TIMING] Batch context prefetch complete")
    return batch_data


async def build_system_snapshot_with_batch(
    task: Optional[Task],
    thought: Any,
    batch_data: BatchContextData,
    memory_service: Optional[Any] = None,
    graphql_provider: Optional[Any] = None,
) -> SystemSnapshot:
    """Build system snapshot using pre-fetched batch data."""

    from ciris_engine.schemas.runtime.system_context import ThoughtSummary

    logger.info(
        f"[DEBUG DB TIMING] Building snapshot for thought {getattr(thought, 'thought_id', 'unknown')} with batch data"
    )

    # Per-thought data
    thought_summary = None
    if thought:
        status_val = getattr(thought, "status", None)
        if status_val is not None and hasattr(status_val, "value"):
            status_val = status_val.value
        elif status_val is not None:
            status_val = str(status_val)

        thought_summary = ThoughtSummary(
            thought_id=getattr(thought, "thought_id", "unknown"),
            content=getattr(thought, "content", None),
            status=status_val,
            source_task_id=getattr(thought, "source_task_id", None),
            thought_type=getattr(thought, "thought_type", None),
            thought_depth=getattr(thought, "thought_depth", None),
        )

    # Channel context (per-thought if different channels)
    channel_id = None
    channel_context = None

    # Extract channel_id logic (simplified)
    if task and hasattr(task, "context") and task.context:
        if (
            hasattr(task.context, "system_snapshot")
            and task.context.system_snapshot
            and hasattr(task.context.system_snapshot, "channel_id")
        ):
            channel_id = str(task.context.system_snapshot.channel_id)

    # Only query channel context if we have a channel_id
    if channel_id and memory_service:
        logger.info(f"[DEBUG DB TIMING] Per-thought: querying channel context for {channel_id}")
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

    # Build snapshot with batch data
    return SystemSnapshot(
        # Channel context fields
        channel_context=channel_context,
        channel_id=channel_id,
        # Current processing state
        current_task_details=current_task_summary,
        current_thought_summary=thought_summary,
        # System overview
        system_counts={},  # Could be populated from batch data if needed
        top_pending_tasks_summary=batch_data.top_tasks,
        recently_completed_tasks_summary=batch_data.recent_tasks,
        # Agent identity fields
        agent_identity=batch_data.agent_identity or {},
        identity_purpose=batch_data.identity_purpose or "",
        identity_capabilities=batch_data.identity_capabilities,
        identity_restrictions=batch_data.identity_restrictions,
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
        user_profiles=[],  # Not using dict, it expects a list
    )
