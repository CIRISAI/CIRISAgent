"""
Base processor abstract class defining the interface for all processor types.
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import ValidationError

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.processors.base import MetricsUpdate, ProcessorMetrics, ProcessorServices
from ciris_engine.schemas.processors.results import ProcessingResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """Abstract base class for all processor types."""

    def __init__(
        self,
        config_accessor: ConfigAccessor,
        thought_processor: ThoughtProcessor,
        action_dispatcher: "ActionDispatcher",
        services: ProcessorServices,
    ) -> None:
        """Initialize base processor with common dependencies.

        Args:
            services: Type-safe ProcessorServices container with all dependencies
        """
        self.config = config_accessor
        self.thought_processor = thought_processor
        self.action_dispatcher = action_dispatcher

        # Store services directly - no dict conversion
        self.services = services

        # Direct attribute access with type safety
        if services.discord_service:
            self.discord_service = services.discord_service

        # Get TimeService from services - REQUIRED
        if not services.time_service:
            raise ValueError("time_service is required for processors")
        # Cast to correct type for mypy strictness
        from typing import cast

        self.time_service: TimeServiceProtocol = cast(TimeServiceProtocol, services.time_service)

        # Get ResourceMonitor from services - REQUIRED for system snapshots
        if not services.resource_monitor:
            raise ValueError("resource_monitor is required for processors")
        self.resource_monitor = services.resource_monitor

        # Extract other commonly used services with direct attribute access
        self.memory_service = services.memory_service
        self.audit_service = services.audit_service
        self.graphql_provider = getattr(services, "graphql_provider", None)
        self.app_config = getattr(services, "app_config", None)
        self.runtime = getattr(services, "runtime", None)
        self.service_registry = getattr(services, "service_registry", None)
        self.secrets_service = getattr(services, "secrets_service", None)
        self.telemetry_service = services.telemetry_service

        self.metrics = ProcessorMetrics()

    @abstractmethod
    def get_supported_states(self) -> List[AgentState]:
        """Return list of states this processor can handle."""

    @abstractmethod
    async def can_process(self, state: AgentState) -> bool:
        """Check if this processor can handle the current state."""

    @abstractmethod
    async def process(self, round_number: int) -> ProcessingResult:
        """
        Execute processing for one round.
        Returns metrics/results from the processing.
        """

    def initialize(self) -> bool:
        """
        Initialize the processor.
        Override in subclasses for specific initialization.
        """
        self.metrics.start_time = self.time_service.now()
        return True

    def cleanup(self) -> bool:
        """
        Clean up processor resources.
        Override in subclasses for specific cleanup.
        """
        self.metrics.end_time = self.time_service.now()
        return True

    def get_metrics(self) -> ProcessorMetrics:
        """Get processor metrics."""
        return self.metrics.model_copy()

    def update_metrics(self, updates: MetricsUpdate) -> None:
        """Update processor metrics."""
        if updates.items_processed is not None:
            self.metrics.items_processed += updates.items_processed
        if updates.errors is not None:
            self.metrics.errors += updates.errors
        if updates.rounds_completed is not None:
            self.metrics.rounds_completed += updates.rounds_completed

        # Update additional metrics
        additional = self.metrics.additional_metrics
        if updates.thoughts_generated is not None:
            additional.thoughts_generated += updates.thoughts_generated
        if updates.actions_dispatched is not None:
            additional.actions_dispatched += updates.actions_dispatched
        if updates.memories_created is not None:
            additional.memories_created += updates.memories_created
        if updates.state_transitions is not None:
            additional.state_transitions += updates.state_transitions
        if updates.llm_tokens_used is not None:
            additional.llm_tokens_used += updates.llm_tokens_used
        if updates.cache_hits is not None:
            additional.cache_hits += updates.cache_hits
        if updates.cache_misses is not None:
            additional.cache_misses += updates.cache_misses

        # Update custom metrics
        for key, value in updates.custom_counters.items():
            # Both operands are ints - value is int from custom_counters
            current_val: int = additional.custom_counters.get(key, 0)
            additional.custom_counters[key] = current_val + int(value)
        for key, value in updates.custom_gauges.items():  # type: ignore[assignment]
            # Value is float from custom_gauges
            additional.custom_gauges[key] = float(value)

    def _get_time_service(self) -> Any:
        """Get time service from either _time_service or time_service attribute."""
        return getattr(self, "_time_service", None) or getattr(self, "time_service", None)

    async def _stream_perform_action_step(self, result: Any, thought: Any, dispatch_ctx: Any) -> None:
        """Stream PERFORM_ACTION step point if streaming is enabled."""
        if not hasattr(self, "_stream_step_point"):
            return

        from ciris_engine.schemas.services.runtime_control import StepPoint

        time_svc = self._get_time_service()
        timestamp_str = time_svc.now().isoformat() if time_svc else None

        await self._stream_step_point(
            StepPoint.PERFORM_ACTION,
            thought.thought_id,
            {
                "timestamp": timestamp_str,
                "thought_id": thought.thought_id,
                "selected_action": str(getattr(result, "selected_action", "UNKNOWN")),
                "action_parameters": str(getattr(result, "action_parameters", None)),
                "dispatch_context": str(dispatch_ctx),
            },
        )

    def _extract_action_name(self, dispatch_result: Any, result: Any) -> str:
        """Extract action name from dispatch result or action selection result."""
        # Check for ActionResponse (typed response)
        if hasattr(dispatch_result, "action_type"):
            return str(dispatch_result.action_type)

        # Backward compatibility: check for dict
        if isinstance(dispatch_result, dict):
            return str(dispatch_result.get("action_type", "UNKNOWN"))

        # Check if result has final_action (ConscienceApplicationResult)
        try:
            final_action = result.final_action
            return str(final_action.selected_action)
        except AttributeError:
            pass

        # Must be ActionSelectionDMAResult directly
        try:
            return str(result.selected_action)
        except AttributeError:
            return "UNKNOWN"

    def _calculate_dispatch_time(self, dispatch_start: Any, dispatch_end: Any) -> float:
        """Calculate dispatch time in milliseconds."""
        if dispatch_start and dispatch_end:
            return float((dispatch_end - dispatch_start).total_seconds() * 1000)
        return 0.0

    async def dispatch_action(self, result: Any, thought: Any, context: JSONDict) -> bool:
        """
        Common action dispatch logic.
        Returns True if dispatch succeeded.
        """
        logger.debug(f"[DISPATCH dispatch_action called for thought {thought.thought_id}")
        try:
            from ciris_engine.schemas.runtime.contexts import DispatchContext

            dispatch_ctx = DispatchContext(**context)

            # STEP POINT: PERFORM_ACTION (before action dispatch)
            await self._stream_perform_action_step(result, thought, dispatch_ctx)

            # Get time service for dispatch timing
            time_svc = self._get_time_service()
            dispatch_start = time_svc.now() if time_svc else None

            # Dispatch returns ActionResponse (typed)
            from ciris_engine.schemas.services.runtime_control import ActionResponse

            dispatch_result: ActionResponse = await self.action_dispatcher.dispatch(
                action_selection_result=result, thought=thought, dispatch_context=dispatch_ctx
            )

            # Calculate dispatch timing
            time_svc = self._get_time_service()
            if not time_svc:
                raise RuntimeError("CRITICAL: No time service available in processor - system integrity compromised")
            dispatch_end = time_svc.now()
            dispatch_time_ms = self._calculate_dispatch_time(dispatch_start, dispatch_end)

            # Update ActionResponse with actual execution time
            dispatch_result.execution_time_ms = dispatch_time_ms

            return True
        except Exception as e:
            logger.error(f"Error dispatching action: {e}", exc_info=True)
            self.metrics.errors += 1
            return False

    async def process_thought_item(self, item: ProcessingQueueItem, context: Optional[JSONDict] = None) -> Any:
        """
        Process a single thought item through the thought processor.
        Returns the processing result.
        Implements DMA failure fallback: force PONDER or DEFER as appropriate.
        """
        try:
            result = await self.thought_processor.process_thought(item, context)
            self.metrics.items_processed += 1
            return result
        except Exception as e:
            # Log concise error without full stack trace
            error_msg = str(e).replace("\n", " ")[:200]
            logger.error(f"Error processing thought {item.thought_id}: {error_msg}")
            # Only log full trace for non-validation errors
            if not isinstance(e, ValidationError):
                logger.debug("Full exception details:", exc_info=True)
            self.metrics.errors += 1
            if hasattr(e, "is_dma_failure") and getattr(e, "is_dma_failure", False):
                if hasattr(self, "force_ponder"):
                    logger.warning(f"DMA failure for {item.thought_id}, forcing PONDER fallback.")
                    return self.force_ponder(item, context)
                elif hasattr(self, "force_defer"):
                    logger.warning(f"DMA failure for {item.thought_id}, forcing DEFER fallback.")
                    return self.force_defer(item, context)
            raise

    def force_ponder(self, item: ProcessingQueueItem, context: Optional[JSONDict] = None) -> None:
        """Force a PONDER action for the given thought item. Override in subclass for custom logic."""
        logger.info(f"Forcing PONDER for thought {item.thought_id}")
        # Implement actual logic in subclass

    def force_defer(self, item: ProcessingQueueItem, context: Optional[JSONDict] = None) -> None:
        """Force a DEFER action for the given thought item. Override in subclass for custom logic."""
        logger.info(f"Forcing DEFER for thought {item.thought_id}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
