"""
ThoughtProcessor: Core orchestration logic for H3ERE pipeline.
Main coordinator that executes the 7 phases of ethical reasoning.
"""

import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.handlers.control.ponder_handler import PonderHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.logic.utils.channel_utils import create_channel_context
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import DeferParams, PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought, ThoughtStatus
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)

# Import phase mixins
from .gather_context import ContextGatheringPhase
from .perform_dmas import DMAExecutionPhase
from .perform_aspdma import ActionSelectionPhase
from .conscience_execution import ConscienceExecutionPhase
from .recursive_processing import RecursiveProcessingPhase
from .finalize_action import ActionFinalizationPhase
from .action_execution import ActionExecutionPhase

logger = logging.getLogger(__name__)


class ThoughtProcessor(
    ContextGatheringPhase,
    DMAExecutionPhase,
    ActionSelectionPhase,
    ConscienceExecutionPhase,
    RecursiveProcessingPhase,
    ActionFinalizationPhase,
    ActionExecutionPhase,
):
    """
    Main orchestrator for the H3ERE (Hyper3 Ethical Recursive Engine) pipeline.
    
    Inherits phase-specific methods from mixin classes and coordinates
    the 7-step ethical reasoning process:
    1. GATHER_CONTEXT - Build processing context
    2. PERFORM_DMAS - Multi-perspective analysis
    3. PERFORM_ASPDMA - Action selection
    4. CONSCIENCE_EXECUTION - Ethical validation
    5. RECURSIVE_* - Retry logic (optional)
    6. FINALIZE_ACTION - Final action determination
    7. ACTION_* - Action dispatch and completion
    """

    def __init__(
        self,
        dma_orchestrator: Any,
        context_builder: Any,
        conscience_registry: Any,
        app_config: ConfigAccessor,
        dependencies: ActionHandlerDependencies,
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        auth_service: Optional[Any] = None,
    ) -> None:
        self.dma_orchestrator = dma_orchestrator
        self.context_builder = context_builder
        self.conscience_registry = conscience_registry
        self.app_config = app_config
        self.dependencies = dependencies
        self._time_service = time_service
        self.telemetry_service = telemetry_service
        self.auth_service = auth_service
        self._pipeline_controller = None  # Will be deprecated

    async def process_thought(
        self, thought_item: ProcessingQueueItem, context: Optional[dict] = None
    ) -> Optional[ActionSelectionDMAResult]:
        """
        Main H3ERE pipeline orchestration.
        
        Executes all 7 phases using decorated step methods that handle
        streaming and single-step pause/resume automatically.
        """
        start_time = self._time_service.now()

        # Initialize correlation for tracking
        correlation = ServiceCorrelation(
            correlation_id=f"thought_processing_{thought_item.thought_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.THOUGHT_PROCESSING,
            service_name="ThoughtProcessor",
            operation_name="process_thought",
            initiated_at=start_time.isoformat(),
            request_context=TraceContext(
                thought_id=thought_item.thought_id,
                task_id=thought_item.source_task_id,
                correlation_id=f"thought_processing_{thought_item.thought_id}_{start_time.timestamp()}",
                operation_type="process_thought",
            ),
        )
        persistence.create_correlation(correlation, self._time_service)

        # Fetch the actual thought
        thought = await self._fetch_thought(thought_item.thought_id)
        if not thought:
            logger.warning(f"ThoughtProcessor: Could not fetch thought {thought_item.thought_id}")
            return None

        # 1. GATHER_CONTEXT - Build processing context
        thought_context = await self._gather_context_step(thought_item, context)

        # 2. PERFORM_DMAS - Multi-perspective analysis
        dma_results = await self._perform_dmas_step(thought_item, thought_context)

        # 3. Check for failures/escalations
        if self._has_critical_failure(dma_results):
            end_time = self._time_service.now()
            persistence.update_correlation(
                correlation.correlation_id,
                {
                    "success": "false",
                    "error_message": "Critical DMA failure",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                ServiceCorrelationStatus.FAILED,
                self._time_service
            )
            return self._create_deferral_result(dma_results, thought)

        # 4. PERFORM_ASPDMA - LLM-powered action selection
        action_result = await self._perform_aspdma_step(thought_item, thought_context, dma_results)

        # Debug logging for action result
        if action_result:
            selected_action = getattr(action_result, "selected_action", "UNKNOWN")
            logger.info(f"ThoughtProcessor: Action selection result for {thought.thought_id}: {selected_action}")

            if selected_action == HandlerActionType.OBSERVE:
                logger.warning(
                    f"OBSERVE ACTION DEBUG: ThoughtProcessor received OBSERVE action for thought {thought.thought_id}"
                )
        else:
            logger.error(f"ThoughtProcessor: No action result for thought {thought.thought_id}")

        # 5. CONSCIENCE_EXECUTION - Apply ethical safety validation
        conscience_result = await self._conscience_execution_step(thought_item, action_result)

        # 6. Handle recursive processing if needed (RECURSIVE_ASPDMA + RECURSIVE_CONSCIENCE)
        final_result, final_conscience_result = await self._handle_recursive_processing(
            thought_item, thought, thought_context, dma_results, conscience_result, action_result
        )

        # 7. FINALIZE_ACTION - Determine final action
        finalized_result = await self._finalize_action_step(thought_item, final_result or action_result)

        # Record successful completion
        if self.telemetry_service:
            await self.telemetry_service.record_metric(
                "thought_processing_completed",
                value=1.0,
                tags={"thought_id": thought.thought_id, "path_type": "hot", "source_module": "thought_processor"},
            )
            if finalized_result:
                action_metric = f"action_selected_{finalized_result.selected_action.value}"
                await self.telemetry_service.record_metric(
                    action_metric,
                    value=1.0,
                    tags={
                        "thought_id": thought.thought_id,
                        "action": finalized_result.selected_action.value,
                        "path_type": "hot",
                        "source_module": "thought_processor",
                    },
                )

        # Update correlation with success
        end_time = self._time_service.now()
        persistence.update_correlation(
            correlation.correlation_id,
            {
                "success": "true",
                "result_summary": f"Successfully processed thought with action: {finalized_result.selected_action if finalized_result else 'none'}",
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat(),
            },
            ServiceCorrelationStatus.COMPLETED,
            self._time_service
        )

        return finalized_result

    # Helper methods that will remain in main.py
    async def _fetch_thought(self, thought_id: str) -> Optional[Thought]:
        """Fetch thought from persistence layer."""
        from ciris_engine.schemas.persistence.core import ThoughtQuery
        
        query = ThoughtQuery(thought_id=thought_id)
        thoughts = persistence.get_thoughts(query)
        return thoughts[0] if thoughts else None

    def _has_critical_failure(self, dma_results) -> bool:
        """Check if DMA results indicate critical failure requiring escalation."""
        if not dma_results:
            return True
        
        # Check for specific failure indicators
        if hasattr(dma_results, 'critical_failure') and dma_results.critical_failure:
            return True
            
        if hasattr(dma_results, 'should_escalate') and dma_results.should_escalate:
            return True
            
        return False

    def _create_deferral_result(self, dma_results, thought) -> ActionSelectionDMAResult:
        """Create a deferral result for failed processing."""
        context = {"dma_failure": str(dma_results)} if dma_results else {"error": "No DMA results"}
        defer_params = DeferParams(reason="Critical processing failure", context=context, defer_until=None)
        
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=defer_params,
            rationale="Critical failure during thought processing",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

    def _get_profile_name(self, thought: Thought) -> str:
        """Get profile name for DMA processing."""
        # Extract profile from thought context or use default
        if hasattr(thought, 'context') and thought.context:
            return getattr(thought.context, 'profile_name', 'default')
        return 'default'

    def _describe_action(self, action_result) -> str:
        """Get human-readable description of an action."""
        if not action_result:
            return "unknown action"
        
        action_type = getattr(action_result, 'selected_action', 'UNKNOWN')
        return f"{action_type.value.lower()}" if hasattr(action_type, 'value') else str(action_type).lower()

    def _handle_special_cases(self, conscience_result, thought, thought_context):
        """Handle special processing cases (PONDER, DEFER overrides)."""
        # This method handles edge cases and will be kept in main.py
        # Implementation would go here based on current logic
        if conscience_result and hasattr(conscience_result, "final_action"):
            return conscience_result.final_action
        return None