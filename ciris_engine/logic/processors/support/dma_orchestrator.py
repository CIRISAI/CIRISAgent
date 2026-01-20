import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
from ciris_engine.logic.dma.csdma import CSDMAEvaluator
from ciris_engine.logic.dma.dma_executor import (
    run_action_selection_pdma,
    run_csdma,
    run_dma_with_retries,
    run_dsdma,
    run_idma,
    run_pdma,
)
from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.logic.dma.idma import IDMAEvaluator
from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import (
    ActionSelectionDMAResult,
    CSDMAResult,
    DSDMAResult,
    EthicalDMAResult,
    IDMAResult,
)
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
        idma_evaluator: Optional[IDMAEvaluator] = None,
    ) -> None:
        self.ethical_pdma_evaluator = ethical_pdma_evaluator
        self.csdma_evaluator = csdma_evaluator
        self.dsdma = dsdma
        self.action_selection_pdma_evaluator = action_selection_pdma_evaluator
        self.idma_evaluator = idma_evaluator
        self.time_service = time_service
        self.app_config = app_config
        self.llm_service = llm_service
        self.memory_service = memory_service

        self.retry_limit = getattr(app_config.workflow, "DMA_RETRY_LIMIT", 3) if app_config else 3
        # DMA timeout can be overridden via environment variable for slow LLM providers
        # Should be higher than CIRIS_LLM_TIMEOUT to allow for retries
        dma_timeout_env = os.environ.get("CIRIS_DMA_TIMEOUT")
        if dma_timeout_env:
            self.timeout_seconds = float(dma_timeout_env)
        else:
            self.timeout_seconds = getattr(app_config.workflow, "DMA_TIMEOUT_SECONDS", 30.0) if app_config else 30.0

        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            "ethical_pdma": CircuitBreaker("ethical_pdma"),
            "csdma": CircuitBreaker("csdma"),
        }
        if self.dsdma is not None:
            self._circuit_breakers["dsdma"] = CircuitBreaker("dsdma")
        if self.idma_evaluator is not None:
            self._circuit_breakers["idma"] = CircuitBreaker("idma")

    def _set_dma_error(self, errors: DMAErrors, name: str, error: DMAError) -> None:
        """Set a DMA error by name."""
        error_map = {"ethical_pdma": "ethical_pdma", "csdma": "csdma", "dsdma": "dsdma", "idma": "idma"}
        if name in error_map:
            setattr(errors, error_map[name], error)

    async def _run_idma_evaluation(
        self,
        thought_item: ProcessingQueueItem,
        processing_context: Optional[Any],
        dma_results: Dict[str, Any],
    ) -> tuple[Optional[IDMAResult], Optional[str]]:
        """Run IDMA evaluation with circuit breaker protection. Returns (result, prompt)."""
        # If IDMA not configured, return None (optional DMA)
        if not self.idma_evaluator:
            return None, None

        cb = self._circuit_breakers.get("idma")
        if not cb:
            return None, None

        # Circuit breaker tripped = IDMA has failed too many times, treat as error
        if not cb.is_available():
            from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError

            raise CircuitBreakerError("IDMA circuit breaker open - too many recent failures")

        try:
            idma_result = await run_dma_with_retries(
                run_idma,
                self.idma_evaluator,
                thought_item,
                processing_context,
                retry_limit=self.retry_limit,
                timeout_seconds=self.timeout_seconds,
                time_service=self.time_service,
                ethical_result=dma_results["ethical_pdma"],
                csdma_result=dma_results["csdma"],
                dsdma_result=dma_results["dsdma"],
            )
            idma_prompt = getattr(self.idma_evaluator, "last_user_prompt", None)
            cb.record_success()

            if idma_result and idma_result.fragility_flag:
                logger.warning(
                    f"IDMA fragility detected for thought {thought_item.thought_id}: "
                    f"k_eff={idma_result.k_eff:.2f}, phase={idma_result.phase}"
                )
            return idma_result, idma_prompt

        except Exception as e:
            logger.error(f"IDMA evaluation failed: {e}")
            cb.record_failure()
            # NO BYPASS - re-raise to trigger proper deferral/ponder behavior
            # If IDMA runs and fails, the thought should defer, not continue without epistemic grounding
            raise

    def _create_dma_task(
        self,
        run_func: Any,
        evaluator: Any,
        thought_item: ProcessingQueueItem,
        context: Any,
    ) -> "asyncio.Task[Any]":
        """Create a DMA task with standard retry configuration."""
        return asyncio.create_task(
            run_dma_with_retries(
                run_func,
                evaluator,
                thought_item,
                context,
                retry_limit=self.retry_limit,
                timeout_seconds=self.timeout_seconds,
                time_service=self.time_service,
            )
        )

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

        if not self.dsdma:
            raise RuntimeError("DSDMA is not configured - all 3 DMA results (ethical_pdma, csdma, dsdma) are required")

        errors = DMAErrors()
        tasks = {
            "ethical_pdma": self._create_dma_task(
                run_pdma, self.ethical_pdma_evaluator, thought_item, processing_context
            ),
            "csdma": self._create_dma_task(run_csdma, self.csdma_evaluator, thought_item, processing_context),
            "dsdma": self._create_dma_task(run_dsdma, self.dsdma, thought_item, dsdma_context or DMAMetadata()),
        }

        # Collect results - must get ALL 3
        dma_results: Dict[str, Any] = {}
        for name, task in tasks.items():
            try:
                dma_results[name] = await task
            except Exception as e:
                logger.error(f"DMA '{name}' failed: {e}", exc_info=True)
                error = DMAError(dma_name=name, error_message=str(e), error_type=type(e).__name__)
                self._set_dma_error(errors, name, error)

        if errors.has_errors():
            raise Exception(f"DMA(s) failed: {errors.get_error_summary()}")

        # Run IDMA sequentially after initial 3 DMAs (needs their results as input)
        # IDMA is INFORMATIONAL, not a gate - failures don't block the thought
        # A nascent agent will have low k_eff, that's expected, not an error
        idma_result: Optional[IDMAResult] = None
        idma_prompt: Optional[str] = None
        try:
            idma_result, idma_prompt = await self._run_idma_evaluation(thought_item, processing_context, dma_results)
        except Exception as e:
            # Log but don't fail - IDMA is informational
            logger.warning(f"IDMA evaluation unavailable (non-blocking): {e}")
            # idma_result stays None - thought continues without epistemic metadata

        # Capture prompts from evaluators (set during evaluation)
        return InitialDMAResults(
            ethical_pdma=dma_results["ethical_pdma"],
            csdma=dma_results["csdma"],
            dsdma=dma_results["dsdma"],
            idma=idma_result,
            ethical_pdma_prompt=getattr(self.ethical_pdma_evaluator, "last_user_prompt", None),
            csdma_prompt=getattr(self.csdma_evaluator, "last_user_prompt", None),
            dsdma_prompt=getattr(self.dsdma, "last_user_prompt", None) if self.dsdma else None,
            idma_prompt=idma_prompt,
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
            idma_result=dma_results.idma,  # Pass IDMA result for information diversity context
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
