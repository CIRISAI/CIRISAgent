import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
from ciris_engine.logic.dma.csdma import CSDMAEvaluator
from ciris_engine.logic.dma.dma_executor import (
    run_action_selection_pdma,
    run_csdma,
    run_dma_with_retries,
    run_dsdma,
    run_pdma,
)
from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.processors.core import DMAResults
from ciris_engine.schemas.processors.dma import DMAError, DMAErrors, DMAMetadata, InitialDMAResults
from ciris_engine.schemas.runtime.models import Thought

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class DMAOrchestrator:
    def __init__(
        self,
        ethical_pdma_evaluator: EthicalPDMAEvaluator,
        csdma_evaluator: CSDMAEvaluator,
        dsdma: Optional[BaseDSDMA],
        action_selection_pdma_evaluator: ActionSelectionPDMAEvaluator,
        time_service: "TimeServiceProtocol",
        app_config: Optional[Any] = None,
        llm_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
    ) -> None:
        self.ethical_pdma_evaluator = ethical_pdma_evaluator
        self.csdma_evaluator = csdma_evaluator
        self.dsdma = dsdma
        self.action_selection_pdma_evaluator = action_selection_pdma_evaluator
        self.time_service = time_service
        self.app_config = app_config
        self.llm_service = llm_service
        self.memory_service = memory_service

        self.retry_limit = getattr(app_config.workflow, "DMA_RETRY_LIMIT", 3) if app_config else 3
        self.timeout_seconds = getattr(app_config.workflow, "DMA_TIMEOUT_SECONDS", 30.0) if app_config else 30.0

        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            "ethical_pdma": CircuitBreaker("ethical_pdma"),
            "csdma": CircuitBreaker("csdma"),
        }
        if self.dsdma is not None:
            self._circuit_breakers["dsdma"] = CircuitBreaker("dsdma")

    async def run_initial_dmas(
        self,
        thought_item: ProcessingQueueItem,
        processing_context: Optional[Any] = None,  # ProcessingThoughtContext, but using Any to avoid circular import
        dsdma_context: Optional[DMAMetadata] = None,
    ) -> InitialDMAResults:
        """
        Run EthicalPDMA, CSDMA, and DSDMA in parallel (async). All 3 DMA results are required.
        """
        logger.debug(f"[DEBUG TIMING] run_initial_dmas START for thought {thought_item.thought_id}")

        # FAIL FAST: All 3 DMAs are required
        if not self.dsdma:
            raise RuntimeError("DSDMA is not configured - all 3 DMA results (ethical_pdma, csdma, dsdma) are required")

        errors = DMAErrors()
        tasks = {
            "ethical_pdma": asyncio.create_task(
                run_dma_with_retries(
                    run_pdma,
                    self.ethical_pdma_evaluator,
                    thought_item,
                    processing_context,
                    retry_limit=self.retry_limit,
                    timeout_seconds=self.timeout_seconds,
                    time_service=self.time_service,
                )
            ),
            "csdma": asyncio.create_task(
                run_dma_with_retries(
                    run_csdma,
                    self.csdma_evaluator,
                    thought_item,
                    processing_context,
                    retry_limit=self.retry_limit,
                    timeout_seconds=self.timeout_seconds,
                    time_service=self.time_service,
                )
            ),
            "dsdma": asyncio.create_task(
                run_dma_with_retries(
                    run_dsdma,
                    self.dsdma,
                    thought_item,
                    dsdma_context or DMAMetadata(),
                    retry_limit=self.retry_limit,
                    timeout_seconds=self.timeout_seconds,
                    time_service=self.time_service,
                )
            ),
        }

        # Collect results - must get ALL 3
        dma_results = {}
        for name, task in tasks.items():
            try:
                dma_results[name] = await task
            except Exception as e:
                logger.error(f"DMA '{name}' failed: {e}", exc_info=True)
                error = DMAError(dma_name=name, error_message=str(e), error_type=type(e).__name__)
                if name == "ethical_pdma":
                    errors.ethical_pdma = error
                elif name == "csdma":
                    errors.csdma = error
                elif name == "dsdma":
                    errors.dsdma = error

        if errors.has_errors():
            raise Exception(f"DMA(s) failed: {errors.get_error_summary()}")

        # Capture prompts from evaluators (set during evaluation)
        ethical_pdma_prompt = getattr(self.ethical_pdma_evaluator, "last_user_prompt", None)
        csdma_prompt = getattr(self.csdma_evaluator, "last_user_prompt", None)
        dsdma_prompt = getattr(self.dsdma, "last_user_prompt", None) if self.dsdma else None

        # Create InitialDMAResults with all 3 required fields and prompts
        return InitialDMAResults(
            ethical_pdma=dma_results["ethical_pdma"],
            csdma=dma_results["csdma"],
            dsdma=dma_results["dsdma"],
            ethical_pdma_prompt=ethical_pdma_prompt,
            csdma_prompt=csdma_prompt,
            dsdma_prompt=dsdma_prompt,
        )

    async def run_dmas(
        self,
        thought_item: ProcessingQueueItem,
        processing_context: Optional[Any] = None,  # ProcessingThoughtContext, but using Any to avoid circular import
        dsdma_context: Optional[DMAMetadata] = None,
    ) -> "DMAResults":
        """Run all DMAs with circuit breaker protection."""

        from ciris_engine.schemas.processors.core import DMAResults

        results = DMAResults()
        tasks: Dict[str, asyncio.Task[Any]] = {}

        # Ethical PDMA
        cb = self._circuit_breakers.get("ethical_pdma")
        if cb and cb.is_available():
            tasks["ethical_pdma"] = asyncio.create_task(
                run_dma_with_retries(
                    run_pdma,
                    self.ethical_pdma_evaluator,
                    thought_item,
                    processing_context,
                    retry_limit=self.retry_limit,
                    timeout_seconds=self.timeout_seconds,
                    time_service=self.time_service,
                )
            )
        else:
            results.errors.append("ethical_pdma circuit open")

        # CSDMA
        cb = self._circuit_breakers.get("csdma")
        if cb and cb.is_available():
            tasks["csdma"] = asyncio.create_task(
                run_dma_with_retries(
                    run_csdma,
                    self.csdma_evaluator,
                    thought_item,
                    processing_context,
                    retry_limit=self.retry_limit,
                    timeout_seconds=self.timeout_seconds,
                    time_service=self.time_service,
                )
            )
        else:
            results.errors.append("csdma circuit open")

        # DSDMA (required)
        if self.dsdma:
            cb = self._circuit_breakers.get("dsdma")
            if cb and cb.is_available():
                tasks["dsdma"] = asyncio.create_task(
                    run_dma_with_retries(
                        run_dsdma,
                        self.dsdma,
                        thought_item,
                        dsdma_context or DMAMetadata(),
                        retry_limit=self.retry_limit,
                        timeout_seconds=self.timeout_seconds,
                        time_service=self.time_service,
                    )
                )
            elif cb:
                results.errors.append("dsdma circuit open")
        else:
            # FAIL FAST: All 3 DMA results are required
            raise RuntimeError("DSDMA is not configured - all 3 DMA results (ethical_pdma, csdma, dsdma) are required")

        if tasks:
            task_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for (name, _), outcome in zip(tasks.items(), task_results):
                cb = self._circuit_breakers.get(name)
                if isinstance(outcome, Exception):
                    logger.error(f"DMA '{name}' failed: {outcome}", exc_info=True)
                    results.errors.append(str(outcome))
                    if cb:
                        cb.record_failure()
                else:
                    if cb:
                        cb.record_success()
                    if name == "ethical_pdma":
                        if isinstance(outcome, EthicalDMAResult):
                            results.ethical_pdma = outcome
                        else:
                            logger.error(f"Unexpected outcome type for ethical_pdma: {type(outcome)}")
                    elif name == "csdma":
                        if isinstance(outcome, CSDMAResult):
                            results.csdma = outcome
                        else:
                            logger.error(f"Unexpected outcome type for csdma: {type(outcome)}")
                    elif name == "dsdma":
                        if isinstance(outcome, DSDMAResult):
                            results.dsdma = outcome
                        else:
                            logger.error(f"Unexpected outcome type for dsdma: {type(outcome)}")

        return results

    async def run_action_selection(
        self,
        thought_item: ProcessingQueueItem,
        actual_thought: Thought,
        processing_context: Any,  # ProcessingThoughtContext, but using Any to avoid circular import
        dma_results: InitialDMAResults,
        profile_name: str,
    ) -> ActionSelectionDMAResult:
        """Run ActionSelectionPDMAEvaluator sequentially after DMAs."""
        # Create properly typed EnhancedDMAInputs
        # Pass images from thought_item (ProcessingQueueItem) for multimodal support
        triaged = EnhancedDMAInputs(
            original_thought=actual_thought,
            processing_context=processing_context,
            ethical_pdma_result=dma_results.ethical_pdma,
            csdma_result=dma_results.csdma,
            dsdma_result=dma_results.dsdma,
            current_thought_depth=getattr(actual_thought, "thought_depth", 0),
            max_rounds=5,  # Default max rounds
            faculty_enhanced=False,
            recursive_evaluation=False,
            images=thought_item.images,  # Pass images for ActionSelectionPDMA vision
        )

        # Check if this is a conscience retry from the context
        if hasattr(processing_context, "is_conscience_retry") and processing_context.is_conscience_retry:
            triaged.recursive_evaluation = True

        channel_id = None

        # Try to get channel_id from various sources
        if processing_context.system_snapshot and processing_context.system_snapshot.channel_context:
            channel_id = extract_channel_id(processing_context.system_snapshot.channel_context)

        if not channel_id and processing_context.initial_task_context:
            channel_context = getattr(processing_context.initial_task_context, "channel_context", None)
            if channel_context:
                channel_id = extract_channel_id(channel_context)

        # Update fields on the Pydantic model directly
        if triaged.current_thought_depth == 0:  # Only set if not already set
            triaged.current_thought_depth = actual_thought.thought_depth

        if self.app_config and hasattr(self.app_config, "workflow"):
            if triaged.max_rounds == 5:  # Only update if still default
                triaged.max_rounds = self.app_config.workflow.max_rounds
        else:
            logger.warning("DMAOrchestrator: app_config or workflow config not found for max_rounds, using default.")

        # Get identity from persistence tier
        from ciris_engine.logic.persistence.models import get_identity_for_context
        from ciris_engine.schemas.infrastructure.identity_variance import IdentityData

        identity_info = get_identity_for_context()
        # Convert IdentityContext to IdentityData for EnhancedDMAInputs
        triaged.agent_identity = IdentityData(
            agent_id=identity_info.agent_name,  # IdentityContext.agent_name
            description=identity_info.description,
            role=identity_info.agent_role,  # IdentityContext.agent_role
            trust_level=0.5,  # Default trust level (IdentityContext doesn't have this field)
        )

        logger.debug(f"Using identity '{identity_info.agent_name}' for thought {thought_item.thought_id}")

        # Get permitted actions directly from identity
        permitted_actions = identity_info.permitted_actions

        # Identity MUST have permitted actions - no defaults in a mission critical system
        triaged.permitted_actions = permitted_actions

        # Pass through conscience feedback if available
        if hasattr(thought_item, "conscience_feedback") and thought_item.conscience_feedback:
            triaged.conscience_feedback = thought_item.conscience_feedback

        try:
            result = await run_dma_with_retries(
                run_action_selection_pdma,
                self.action_selection_pdma_evaluator,
                triaged,
                retry_limit=self.retry_limit,
                timeout_seconds=self.timeout_seconds,
                time_service=self.time_service,
            )
        except Exception as e:
            logger.error(f"ActionSelectionPDMA failed: {e}", exc_info=True)
            raise

        if isinstance(result, ActionSelectionDMAResult):
            return result
        else:
            logger.error(f"Action selection returned unexpected type: {type(result)}")
            raise TypeError(f"Expected ActionSelectionDMAResult, got {type(result)}")
