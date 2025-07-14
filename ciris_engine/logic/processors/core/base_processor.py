"""
Base processor abstract class defining the interface for all processor types.
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, List, TYPE_CHECKING
from pydantic import ValidationError

from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.processors.base import (
    ProcessorMetrics, MetricsUpdate
)
from ciris_engine.schemas.processors.results import ProcessingResult
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

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
        services: dict
    ) -> None:
        """Initialize base processor with common dependencies."""
        self.config = config_accessor
        self.thought_processor = thought_processor
        self.action_dispatcher = action_dispatcher
        self.services = services
        if services and "discord_service" in services:
            self.discord_service = services["discord_service"]

        # Get TimeService from services
        time_service = services.get('time_service')
        if not time_service:
            raise ValueError("time_service is required for processors")
        self.time_service: TimeServiceProtocol = time_service

        # Get ResourceMonitor from services - REQUIRED for system snapshots
        self.resource_monitor = services.get('resource_monitor')
        if not self.resource_monitor:
            raise ValueError("resource_monitor is required for processors")

        # Extract other commonly used services
        self.memory_service = services.get('memory_service')
        self.graphql_provider = services.get('graphql_provider')
        self.app_config = services.get('app_config')
        self.runtime = services.get('runtime')
        self.service_registry = services.get('service_registry')
        self.secrets_service = services.get('secrets_service')
        self.telemetry_service = services.get('telemetry_service')

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

    async def initialize(self) -> bool:
        """
        Initialize the processor.
        Override in subclasses for specific initialization.
        """
        self.metrics.start_time = self.time_service.now()
        return True

    async def cleanup(self) -> bool:
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
            additional.custom_counters[key] = additional.custom_counters.get(key, 0) + value
        for key, value in updates.custom_gauges.items():
            additional.custom_gauges[key] = value

    async def dispatch_action(
        self,
        result: Any,
        thought: Any,
        context: dict
    ) -> bool:
        """
        Common action dispatch logic.
        Returns True if dispatch succeeded.
        """
        try:
            # Convert dict to DispatchContext
            from ciris_engine.schemas.runtime.contexts import DispatchContext
            dispatch_ctx = DispatchContext(**context)

            await self.action_dispatcher.dispatch(
                action_selection_result=result,
                thought=thought,
                dispatch_context=dispatch_ctx
            )
            return True
        except Exception as e:
            logger.error(f"Error dispatching action: {e}", exc_info=True)
            self.metrics.errors += 1
            return False

    async def process_thought_item(
        self,
        item: ProcessingQueueItem,
        context: Optional[dict] = None
    ) -> Any:
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
            error_msg = str(e).replace('\n', ' ')[:200]
            logger.error(f"Error processing thought {item.thought_id}: {error_msg}")
            # Only log full trace for non-validation errors
            if not isinstance(e, ValidationError):
                logger.debug("Full exception details:", exc_info=True)
            self.metrics.errors += 1
            if hasattr(e, "is_dma_failure") and getattr(e, "is_dma_failure", False):
                if hasattr(self, "force_ponder"):
                    logger.warning(f"DMA failure for {item.thought_id}, forcing PONDER fallback.")
                    return await self.force_ponder(item, context)
                elif hasattr(self, "force_defer"):
                    logger.warning(f"DMA failure for {item.thought_id}, forcing DEFER fallback.")
                    return await self.force_defer(item, context)
            raise

    async def force_ponder(self, item: ProcessingQueueItem, context: Optional[dict] = None) -> None:
        """Force a PONDER action for the given thought item. Override in subclass for custom logic."""
        logger.info(f"Forcing PONDER for thought {item.thought_id}")
        # Implement actual logic in subclass

    async def force_defer(self, item: ProcessingQueueItem, context: Optional[dict] = None) -> None:
        """Force a DEFER action for the given thought item. Override in subclass for custom logic."""
        logger.info(f"Forcing DEFER for thought {item.thought_id}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
