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
    _get_continuity_summary,
    _get_localized_times,
    _get_recent_tasks,
    _get_secrets_data,
    _get_shutdown_context,
    _get_telemetry_summary,
    _get_top_tasks,
    _resolve_channel_context,
)

logger = logging.getLogger(__name__)


def json_serial(obj: Any) -> Any:
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
    """
    DEPRECATED: Legacy wrapper for backwards compatibility.

    This function is now a thin wrapper around the unified batch snapshot builder.
    All production code should use build_system_snapshot_with_batch directly or
    go through ContextBuilder.build_system_snapshot().

    The unified batch approach:
    - Creates minimal batch context on-demand for single thoughts
    - Uses pre-fetched batch context for batch processing
    - Ensures consistent user enrichment across all code paths
    - Eliminates code duplication between batch and single-thought processing

    This wrapper exists only for test compatibility and will be removed in a
    future version once all tests are updated.
    """
    from .batch_context import build_system_snapshot_with_batch

    logger.debug("[LEGACY WRAPPER] build_system_snapshot called - redirecting to unified batch builder")

    # Redirect to unified batch builder (will create minimal batch context on-demand)
    snapshot = await build_system_snapshot_with_batch(
        task=task,
        thought=thought,
        batch_data=None,  # Will create minimal batch context on-demand
        memory_service=memory_service,
        graphql_provider=graphql_provider,
        time_service=time_service,
        secrets_service=secrets_service,
        service_registry=service_registry,
        resource_monitor=resource_monitor,
        telemetry_service=telemetry_service,
        runtime=runtime,
    )

    # Log context building statistics (for test compatibility)
    if snapshot.user_profiles:
        user_profiles_json = json.dumps([p.model_dump() for p in snapshot.user_profiles], default=json_serial)
        user_profiles_bytes = len(user_profiles_json.encode("utf-8"))
        logger.info(
            f"[CONTEXT BUILD] User Profiles queried: {len(snapshot.user_profiles)} profiles, {user_profiles_bytes} bytes added to context"
        )

    # Log final snapshot size
    snapshot_json = snapshot.model_dump_json()
    snapshot_bytes = len(snapshot_json.encode("utf-8"))
    if snapshot.channel_context is None:
        logger.warning(f"[CONTEXT BUILD] System Snapshot built with {snapshot_bytes} bytes total (no channel context)")
    else:
        logger.info(f"[CONTEXT BUILD] System Snapshot built with {snapshot_bytes} bytes total")

    return snapshot
