import logging
from typing import Any, Dict, Optional

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.memory_service import LocalGraphMemoryService
from ciris_engine.logic.utils import GraphQLContextProvider
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought
from ciris_engine.schemas.runtime.processing_context import ProcessingThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict

from .batch_context import build_system_snapshot_with_batch as _build_snapshot_unified
from .channel_resolution import resolve_channel_id_and_context
from .secrets_snapshot import build_secrets_snapshot as _secrets_snapshot

logger = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(
        self,
        memory_service: Optional[LocalGraphMemoryService] = None,
        graphql_provider: Optional[GraphQLContextProvider] = None,
        app_config: Optional[Any] = None,
        telemetry_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        runtime: Optional[Any] = None,
        service_registry: Optional[Any] = None,
        resource_monitor: Optional[Any] = None,  # Will be REQUIRED
        time_service: Any = None,  # REQUIRED - will fail fast and loud if None
    ) -> None:
        self.memory_service = memory_service
        self.graphql_provider = graphql_provider
        self.app_config = app_config
        self.telemetry_service = telemetry_service
        self.secrets_service = secrets_service  # Must be provided, no fallback creation
        self.runtime = runtime
        self.service_registry = service_registry
        self.resource_monitor = resource_monitor
        self.time_service = time_service

    async def build_thought_context(
        self, thought: Thought, task: Optional[Task] = None, system_snapshot: Optional[SystemSnapshot] = None
    ) -> ProcessingThoughtContext:
        """Build complete context for thought processing."""
        # Use provided snapshot or build new one
        if system_snapshot:
            system_snapshot_data = system_snapshot
            logger.info("[CONTEXT] Using provided system snapshot")
        else:
            system_snapshot_data = await self.build_system_snapshot(task, thought)
            logger.info("[CONTEXT] Built new system snapshot")
        # Convert list of UserProfile to dict keyed by user_id
        user_profiles_list = getattr(system_snapshot_data, "user_profiles", []) or []
        user_profiles_data = {profile.user_id: profile for profile in user_profiles_list}
        task_history_data = getattr(system_snapshot_data, "recently_completed_tasks_summary", None) or []

        # Log user context details
        if user_profiles_data:
            logger.info(f"[CONTEXT] Built user profiles for {len(user_profiles_data)} users")
            for user_id, profile in list(user_profiles_data.items())[:3]:  # Log first 3
                logger.debug(f"[CONTEXT]   User {user_id}: {getattr(profile, 'name', 'unknown')}")

        # Get identity context from memory service
        identity_context_str = await self.memory_service.export_identity_context() if self.memory_service else None

        # --- Mission-Critical Channel ID Resolution ---
        # Use centralized channel resolution to avoid duplication
        channel_id, _channel_context = await resolve_channel_id_and_context(
            task=task, thought=thought, memory_service=self.memory_service, app_config=self.app_config
        )

        # Override with system snapshot's channel_id if present
        if hasattr(system_snapshot_data, "channel_id") and system_snapshot_data.channel_id:
            if channel_id != system_snapshot_data.channel_id:
                logger.debug(
                    f"[CONTEXT] Overriding resolved channel_id '{channel_id}' with "
                    f"system_snapshot channel_id '{system_snapshot_data.channel_id}'"
                )
                channel_id = system_snapshot_data.channel_id

        # Log final channel resolution
        logger.info(f"[CONTEXT] Channel ID resolved: '{channel_id}'")

        # Only set channel_id if it's not already set in system_snapshot
        if channel_id and hasattr(system_snapshot_data, "channel_id"):
            if not system_snapshot_data.channel_id:
                system_snapshot_data.channel_id = channel_id
            elif system_snapshot_data.channel_id != channel_id:
                logger.warning(
                    f"System snapshot already has channel_id '{system_snapshot_data.channel_id}', not overwriting with '{channel_id}'"
                )

        channel_context_str = f"Our assigned channel is {channel_id}" if channel_id else None
        if identity_context_str and channel_context_str:
            identity_context_str = f"{identity_context_str}\n{channel_context_str}"
        elif channel_context_str:
            identity_context_str = channel_context_str
        initial_task_context = None
        if task and hasattr(task, "context") and isinstance(task.context, TaskContext):
            # task.context is typed as Optional[TaskContext], so we use it directly
            initial_task_context = task.context
        return ProcessingThoughtContext(
            system_snapshot=system_snapshot_data,
            user_profiles=user_profiles_data,
            task_history=task_history_data,
            identity_context=identity_context_str,
            initial_task_context=initial_task_context,
        )

    async def build_system_snapshot(
        self, task: Optional[Task], thought: Any  # Accept Thought or ProcessingQueueItem
    ) -> SystemSnapshot:
        """
        Build system snapshot for the thought using unified batch approach.

        This method now uses the unified batch snapshot builder which:
        - Creates minimal batch context on-demand for single thoughts
        - Uses pre-fetched batch context when available (batch processing)
        - Ensures consistent snapshot building across all code paths
        """
        return await _build_snapshot_unified(
            task=task,
            thought=thought,
            batch_data=None,  # Will create minimal batch context on-demand
            memory_service=self.memory_service,
            graphql_provider=self.graphql_provider,
            time_service=self.time_service,
            # Services for on-demand batch context creation
            secrets_service=self.secrets_service,
            service_registry=self.service_registry,
            resource_monitor=self.resource_monitor,
            telemetry_service=self.telemetry_service,
            runtime=self.runtime,
        )

    async def _build_secrets_snapshot(self) -> JSONDict:
        """Build secrets information for SystemSnapshot.

        Returns JSON-compatible dict with SystemSnapshot secret fields:
        - detected_secrets: List[str]
        - secrets_filter_version: int
        - total_secrets_stored: int
        """
        if self.secrets_service is None:
            # Return empty snapshot if no secrets service
            return {"detected_secrets": [], "secrets_filter_version": 0, "total_secrets_stored": 0}
        return await _secrets_snapshot(self.secrets_service)
