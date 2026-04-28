from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic import persistence
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils.constants import ACCORD_TEXT
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import (
    ConscienceCheckResult,
    ConscienceStatus,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType
from ciris_engine.schemas.services.llm import LLMMessage
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)

from .interface import ConscienceInterface
from .prompt_loader import get_conscience_prompt_loader


# Simple conscience config
# ARCHITECTURAL INVARIANT: These thresholds are config values, not learned weights.
# They cannot be modified by accumulated experience or user behavior patterns.
# This prevents ethical normalization through repeated exposure.
class ConscienceConfig(BaseModel):
    enabled: bool = Field(default=True)
    optimization_veto_ratio: float = Field(default=10.0, description="Entropy reduction must be < this ratio")
    coherence_threshold: float = Field(default=0.60, description="Minimum coherence score")
    entropy_threshold: float = Field(default=0.40, description="Maximum entropy allowed")


logger = logging.getLogger(__name__)

# Error/reason message constants
MSG_SINK_UNAVAILABLE_ALLOWING = "Sink service unavailable, allowing action"
MSG_SINK_UNAVAILABLE = "Sink service unavailable"
MSG_NO_CONTENT = "No content to evaluate"
MSG_SINK_NO_LLM = "Sink does not have LLM service"
MSG_INVALID_LLM_RESULT = "Invalid result type from LLM"


# LLM-output schemas live in `ciris_engine/schemas/conscience/core.py` —
# imported here for backward compat. New consumers should import directly
# from the schemas module.
from ciris_engine.schemas.conscience.core import (  # noqa: E402,F401
    CoherenceResult,
    EntropyResult,
)


class _BaseConscience(ConscienceInterface):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        config: ConscienceConfig,
        model_name: str = DEFAULT_OPENAI_MODEL_NAME,
        sink: Optional[object] = None,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        self.service_registry = service_registry
        self.config = config
        self.model_name = model_name
        self.sink = sink
        if not time_service:
            raise RuntimeError("TimeService is required for Conscience")
        self._time_service = time_service

    def _resolve_language(self, context: ConscienceCheckContext) -> str:
        """Determine the language for THIS conscience check.

        Defers ALL resolution to the canonical helper
        `get_user_language_from_context`, which walks the priority chain:
        thought.preferred_language → task.preferred_language →
        system_snapshot.user_profiles[*].preferred_language → env var.

        Language is resolved ONCE per thought and does not change
        mid-thought. Every conscience must use this same helper so all
        layers of the deliberation pipeline read the same locale.

        BUG FIX (2026-04-26): the previous version passed
        `context.system_snapshot` instead of `context`, which short-circuited
        the thought- and task-level layers of the priority chain (those
        layers expect the OUTER context object, not the snapshot). The
        symptom was every conscience evaluation falling through to the env
        var default regardless of the thought's actual locale, so a Spanish
        agent could end up running its conscience checks under the
        environment's CIRIS_PREFERRED_LANGUAGE setting.
        """
        from ciris_engine.logic.utils.localization import get_user_language_from_context

        return get_user_language_from_context(context)

    def _create_trace_correlation(
        self, conscience_type: str, context: ConscienceCheckContext, start_time: datetime
    ) -> ServiceCorrelation:
        """Helper to create trace correlations for conscience checks."""
        thought = context.thought
        thought_id = thought.thought_id if hasattr(thought, "thought_id") else "unknown"
        task_id = thought.source_task_id if hasattr(thought, "source_task_id") else "unknown"

        # Create trace for guardrail execution
        trace_id = f"task_{task_id}_{thought_id}"
        span_id = f"{conscience_type}_conscience_{thought_id}"
        parent_span_id = f"thought_processor_{thought_id}"

        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name=f"{conscience_type}_conscience_check",
            span_kind="internal",
            baggage={"thought_id": thought_id, "task_id": task_id, "guardrail_type": conscience_type},
        )

        correlation = ServiceCorrelation(
            correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.TRACE_SPAN,
            service_type="guardrail",
            handler_name=f"{conscience_type.title()}Conscience",
            action_type="check",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
            trace_context=trace_context,
            tags={
                "thought_id": thought_id,
                "task_id": task_id,
                "component_type": "guardrail",
                "guardrail_type": conscience_type,
                "trace_depth": "4",
            },
            request_data=None,
            response_data=None,
            status=ServiceCorrelationStatus.COMPLETED,
            metric_data=None,
            log_data=None,
            retention_policy="short",
            ttl_seconds=None,
            parent_correlation_id=None,
        )

        # Add correlation
        if self._time_service:
            persistence.add_correlation(correlation, self._time_service)

        return correlation

    def _update_trace_correlation(
        self, correlation: ServiceCorrelation, success: bool, result_summary: str, start_time: datetime
    ) -> None:
        """Helper to update trace correlations."""
        if not self._time_service:
            return

        end_time = self._time_service.now()
        update_req = CorrelationUpdateRequest(
            correlation_id=correlation.correlation_id,
            response_data={
                "success": str(success).lower(),
                "result_summary": result_summary,
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat(),
            },
            status=ServiceCorrelationStatus.COMPLETED if success else ServiceCorrelationStatus.FAILED,
            metric_value=None,
            tags=None,
        )
        persistence.update_correlation(update_req, self._time_service)

    async def _get_sink(self) -> Any:
        """Get the multi-service sink for centralized LLM calls with circuit breakers."""
        if not self.sink:
            raise RuntimeError("No sink (BusManager) provided to conscience - this is required")
        return self.sink

    def _get_image_context_info(self, context: ConscienceCheckContext) -> Optional[str]:
        """
        Get textual metadata about images in context for conscience evaluation.

        SECURITY: We do NOT pass raw images to conscience evaluators to prevent
        visual prompt injection attacks (hidden text, steganography, typographic attacks).
        Instead, we provide textual metadata so the conscience knows images were present.

        The main DMA pipeline already analyzed the images - the conscience just needs
        to know context exists to properly evaluate the proposed response.
        """
        thought = context.thought
        try:
            # Check if thought has images attribute and it's a non-empty list
            if hasattr(thought, "images") and isinstance(thought.images, list) and thought.images:
                image_count = len(thought.images)
                # Provide safe textual context without exposing image content
                return (
                    f"[IMAGE CONTEXT: The user shared {image_count} image(s) with their request. "
                    f"The primary DMA pipeline has already analyzed these images and the proposed "
                    f"response is based on that analysis. Evaluate the response assuming it accurately "
                    f"describes user-provided visual content.]"
                )
        except (TypeError, AttributeError):
            # Handle Mock objects or other non-standard thought types in tests
            pass
        return None

    def _initialize_time_service(self) -> None:
        """Initialize time service from registry."""
        try:
            # Get time service synchronously
            services = self.service_registry.get_services_by_type(ServiceType.TIME)
            if services:
                self._time_service = services[0]
            else:
                logger.warning("TimeService not found in registry, time operations may fail")
        except Exception as e:
            logger.error(f"Failed to get TimeService: {e}")


class EntropyConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("entropy", context, start_time)

        ts_datetime = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        ts_datetime.isoformat()
        if action.selected_action != HandlerActionType.SPEAK:
            self._update_trace_correlation(correlation, True, "Non-speak action, no entropy check needed", start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts_datetime,
            )
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, MSG_SINK_UNAVAILABLE_ALLOWING, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.WARNING,
                passed=True,
                reason=MSG_SINK_UNAVAILABLE,
                check_timestamp=ts_datetime,
            )
        text = ""
        params = action.action_parameters
        # Extract content from params - params is a typed union, not dict
        if hasattr(params, "content"):
            text = getattr(params, "content", "")
        if not text:
            self._update_trace_correlation(correlation, True, MSG_NO_CONTENT, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                reason=MSG_NO_CONTENT,
                check_timestamp=ts_datetime,
            )

        # Inline the entropy evaluation
        entropy = 0.1  # Default safe value
        entropy_user_prompt: Optional[str] = None
        try:
            # Get textual image context info (NOT raw images - prevents injection attacks)
            image_context = self._get_image_context_info(context)
            if image_context:
                logger.info("[CONSCIENCE] EntropyConscience: Image context detected, using textual metadata")
            messages, entropy_user_prompt = self._create_entropy_messages(
                text, image_context, language=self._resolve_language(context)
            )
            if hasattr(sink, "llm"):
                entropy_eval, _ = await sink.llm.call_llm_structured(
                    messages=messages,
                    response_model=EntropyResult,
                    handler_name="entropy_conscience",
                    max_tokens=4096,
                    temperature=0.0,
                    thought_id=context.thought.thought_id,
                    task_id=getattr(context.thought, "source_task_id", None),
                )
            else:
                raise RuntimeError(MSG_SINK_NO_LLM)
            if isinstance(entropy_eval, EntropyResult):
                entropy = float(entropy_eval.entropy)
                # Log the alternative-meaning enumeration alongside the score
                # so traces carry the evidence, not just the number. Counts +
                # outlier flag at INFO; full alternatives at DEBUG to keep
                # default logs tight.
                alt_count = len(entropy_eval.alternative_meanings)
                logger.info(
                    "[CONSCIENCE] EntropyConscience: entropy=%.2f "
                    "actual_is_representative=%s alternatives=%d",
                    entropy,
                    entropy_eval.actual_is_representative,
                    alt_count,
                )
                if logger.isEnabledFor(logging.DEBUG):
                    for i, alt in enumerate(entropy_eval.alternative_meanings, 1):
                        logger.debug("  alt #%d: %s", i, alt[:200])
                entropy_alternatives = list(entropy_eval.alternative_meanings)
                entropy_actual_is_representative = entropy_eval.actual_is_representative
            else:
                entropy_alternatives = []
                entropy_actual_is_representative = None
        except Exception as e:
            logger.error(f"EntropyConscience: Error evaluating entropy: {e}", exc_info=True)
            entropy_alternatives = []
            entropy_actual_is_representative = None

        passed = entropy <= self.config.entropy_threshold
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Entropy {entropy:.2f} > threshold {self.config.entropy_threshold:.2f}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Entropy check passed: {entropy:.2f} <= {self.config.entropy_threshold:.2f}",
            start_time,
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            entropy_score=entropy,
            entropy_prompt=entropy_user_prompt,
            entropy_alternatives=entropy_alternatives,
            entropy_actual_is_representative=entropy_actual_is_representative,
            check_timestamp=ts_datetime,
        )

    def _create_entropy_messages(
        self, text: str, image_context: Optional[str] = None, language: Optional[str] = None
    ) -> tuple[List[LLMMessage], str]:
        """Create messages for entropy evaluation with optional image context metadata.

        Returns:
            Tuple of (messages list, user_prompt string for streaming)
        """
        loader = get_conscience_prompt_loader(language=language)
        system_prompt = loader.get_system_prompt("entropy_conscience")
        user_prompt = loader.get_user_prompt("entropy_conscience", image_context=image_context, text=text)

        return [
            # Polyglot ACCORD: ethical reasoning draws from every tradition in
            # chorus. The conscience evaluates conduct against the full ethical
            # canon, not against a single-language slice of it. Only the system
            # prompt above is localized so the LLM judge reads its calibration
            # in the user's language (no internal translation step).
            LLMMessage(role="system", content=ACCORD_TEXT),
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ], user_prompt


class CoherenceConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("coherence", context, start_time)

        ts_datetime = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        ts_datetime.isoformat()
        if action.selected_action != HandlerActionType.SPEAK:
            self._update_trace_correlation(correlation, True, "Non-speak action, no coherence check needed", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.PASSED, passed=True, check_timestamp=ts_datetime)
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, MSG_SINK_UNAVAILABLE_ALLOWING, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.WARNING,
                passed=True,
                reason=MSG_SINK_UNAVAILABLE,
                check_timestamp=ts_datetime,
            )
        text = ""
        params = action.action_parameters
        # Extract content from params - params is a typed union, not dict
        if hasattr(params, "content"):
            text = getattr(params, "content", "")
        if not text:
            self._update_trace_correlation(correlation, True, MSG_NO_CONTENT, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                reason=MSG_NO_CONTENT,
                check_timestamp=ts_datetime,
            )

        # Inline the coherence evaluation
        coherence = 0.9  # Default safe value
        coherence_user_prompt: Optional[str] = None
        try:
            # Get textual image context info (NOT raw images - prevents injection attacks)
            image_context = self._get_image_context_info(context)
            if image_context:
                logger.info("[CONSCIENCE] CoherenceConscience: Image context detected, using textual metadata")
            messages, coherence_user_prompt = self._create_coherence_messages(
                text, image_context, language=self._resolve_language(context)
            )
            if hasattr(sink, "llm"):
                coherence_eval, _ = await sink.llm.call_llm_structured(
                    messages=messages,
                    response_model=CoherenceResult,
                    handler_name="coherence_conscience",
                    max_tokens=4096,
                    temperature=0.0,
                    thought_id=context.thought.thought_id,
                    task_id=getattr(context.thought, "source_task_id", None),
                )
            else:
                raise RuntimeError(MSG_SINK_NO_LLM)
            if isinstance(coherence_eval, CoherenceResult):
                coherence = float(coherence_eval.coherence)
        except Exception as e:
            logger.error(f"CoherenceConscience: Error evaluating coherence: {e}", exc_info=True)

        passed = coherence >= self.config.coherence_threshold
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Coherence {coherence:.2f} < threshold {self.config.coherence_threshold:.2f}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Coherence check passed: {coherence:.2f} >= {self.config.coherence_threshold:.2f}",
            start_time,
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            coherence_score=coherence,
            coherence_prompt=coherence_user_prompt,
            check_timestamp=ts_datetime,
        )

    def _create_coherence_messages(
        self, text: str, image_context: Optional[str] = None, language: Optional[str] = None
    ) -> tuple[List[LLMMessage], str]:
        """Create messages for coherence evaluation with optional image context metadata.

        Returns:
            Tuple of (messages list, user_prompt string for streaming)
        """
        loader = get_conscience_prompt_loader(language=language)
        system_prompt = loader.get_system_prompt("coherence_conscience")
        user_prompt = loader.get_user_prompt("coherence_conscience", image_context=image_context, text=text)

        return [
            # Polyglot ACCORD: ethical reasoning draws from every tradition in
            # chorus. The conscience evaluates conduct against the full ethical
            # canon, not against a single-language slice of it. Only the system
            # prompt above is localized so the LLM judge reads its calibration
            # in the user's language (no internal translation step).
            LLMMessage(role="system", content=ACCORD_TEXT),
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ], user_prompt


class OptimizationVetoConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("optimization_veto", context, start_time)

        ts_datetime = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        ts_datetime.isoformat()
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, MSG_SINK_UNAVAILABLE_ALLOWING, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.WARNING,
                passed=True,
                reason=MSG_SINK_UNAVAILABLE,
                check_timestamp=ts_datetime,
            )

        # Inline the optimization veto evaluation
        action_desc = f"{action.selected_action} {action.action_parameters}"
        # Get textual image context info (NOT raw images - prevents injection attacks)
        image_context = self._get_image_context_info(context)
        if image_context:
            logger.info("[CONSCIENCE] OptimizationVetoConscience: Image context detected, using textual metadata")
        messages, opt_veto_user_prompt = self._create_optimization_veto_messages(
            action_desc, image_context, language=self._resolve_language(context)
        )

        try:
            if hasattr(sink, "llm"):
                result, _ = await sink.llm.call_llm_structured(
                    messages=messages,
                    response_model=OptimizationVetoResult,
                    handler_name="optimization_veto_conscience",
                    max_tokens=4096,
                    temperature=0.0,
                    thought_id=context.thought.thought_id,
                    task_id=getattr(context.thought, "source_task_id", None),
                )
            else:
                raise RuntimeError(MSG_SINK_NO_LLM)
            if not isinstance(result, OptimizationVetoResult):
                # Fallback if type is wrong
                result = OptimizationVetoResult(
                    decision="abort",
                    justification=MSG_INVALID_LLM_RESULT,
                    entropy_reduction_ratio=0.0,
                    affected_values=[],
                )
        except Exception as e:
            logger.error(f"OptimizationVetoConscience: Error in optimization veto: {e}", exc_info=True)
            result = OptimizationVetoResult(
                decision="abort",
                justification=f"LLM error: {str(e)}",
                entropy_reduction_ratio=0.0,
                affected_values=[],
            )

        passed = (
            result.decision not in {"abort", "defer"}
            and result.entropy_reduction_ratio < self.config.optimization_veto_ratio
        )
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Optimization veto triggered: {result.justification}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason
            or f"Optimization veto check passed: decision={result.decision}, entropy_reduction_ratio={result.entropy_reduction_ratio:.2f}",
            start_time,
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            optimization_veto_check=result,
            optimization_veto_prompt=opt_veto_user_prompt,
            check_timestamp=ts_datetime,
        )

    def _create_optimization_veto_messages(
        self, action_description: str, image_context: Optional[str] = None, language: Optional[str] = None
    ) -> tuple[List[LLMMessage], str]:
        """Create messages for optimization veto evaluation with optional image context metadata.

        Returns:
            Tuple of (messages list, user_prompt string for streaming)
        """
        loader = get_conscience_prompt_loader(language=language)
        system_prompt = loader.get_system_prompt("optimization_veto_conscience")
        user_prompt = loader.get_user_prompt(
            "optimization_veto_conscience", image_context=image_context, action_description=action_description
        )

        return [
            # Polyglot ACCORD: ethical reasoning draws from every tradition in
            # chorus. The conscience evaluates conduct against the full ethical
            # canon, not against a single-language slice of it. Only the system
            # prompt above is localized so the LLM judge reads its calibration
            # in the user's language (no internal translation step).
            LLMMessage(role="system", content=ACCORD_TEXT),
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ], user_prompt


class EpistemicHumilityConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("epistemic_humility", context, start_time)

        ts_datetime = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        ts_datetime.isoformat()
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, MSG_SINK_UNAVAILABLE_ALLOWING, start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.WARNING,
                passed=True,
                reason=MSG_SINK_UNAVAILABLE,
                check_timestamp=ts_datetime,
            )

        # Inline the epistemic humility evaluation
        desc = f"{action.selected_action} {action.action_parameters}"
        # Get textual image context info (NOT raw images - prevents injection attacks)
        image_context = self._get_image_context_info(context)
        if image_context:
            logger.info("[CONSCIENCE] EpistemicHumilityConscience: Image context detected, using textual metadata")
        messages, epistemic_humility_user_prompt = self._create_epistemic_humility_messages(
            desc, image_context, language=self._resolve_language(context)
        )

        try:
            if hasattr(sink, "llm"):
                result, _ = await sink.llm.call_llm_structured(
                    messages=messages,
                    response_model=EpistemicHumilityResult,
                    handler_name="epistemic_humility_conscience",
                    max_tokens=4096,
                    temperature=0.0,
                    thought_id=context.thought.thought_id,
                    task_id=getattr(context.thought, "source_task_id", None),
                )
            else:
                raise RuntimeError(MSG_SINK_NO_LLM)
            # Handle string certainty values if needed
            if isinstance(result.epistemic_certainty, str):
                mapping = {"low": 0.0, "moderate": 0.5, "high": 1.0}
                val = mapping.get(result.epistemic_certainty.lower(), 0.0)
                result.epistemic_certainty = val
            if not isinstance(result, EpistemicHumilityResult):
                # Fallback if type is wrong
                result = EpistemicHumilityResult(
                    epistemic_certainty=0.0,
                    identified_uncertainties=[MSG_INVALID_LLM_RESULT],
                    reflective_justification=MSG_INVALID_LLM_RESULT,
                    recommended_action="abort",
                )
        except Exception as e:
            logger.error(f"EpistemicHumilityConscience: Error in epistemic humility: {e}", exc_info=True)
            result = EpistemicHumilityResult(
                epistemic_certainty=0.0,
                identified_uncertainties=[f"LLM error: {str(e)}"],
                reflective_justification=f"LLM error: {str(e)}",
                recommended_action="abort",
            )

        # Evaluate the LLM result
        passed = result.recommended_action == "proceed"
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Epistemic humility concern: {result.recommended_action} - {result.reflective_justification}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Epistemic humility check passed: recommended_action={result.recommended_action}",
            start_time,
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            epistemic_humility_check=result,
            epistemic_humility_prompt=epistemic_humility_user_prompt,
            check_timestamp=ts_datetime,
        )

    def _create_epistemic_humility_messages(
        self, action_description: str, image_context: Optional[str] = None, language: Optional[str] = None
    ) -> tuple[List[LLMMessage], str]:
        """Create messages for balanced epistemic humility evaluation with optional image context metadata.

        Returns:
            Tuple of (messages list, user_prompt string for streaming)
        """
        loader = get_conscience_prompt_loader(language=language)
        system_prompt = loader.get_system_prompt("epistemic_humility_conscience")
        user_prompt = loader.get_user_prompt(
            "epistemic_humility_conscience", image_context=image_context, action_description=action_description
        )

        return [
            # Polyglot ACCORD: ethical reasoning draws from every tradition in
            # chorus. The conscience evaluates conduct against the full ethical
            # canon, not against a single-language slice of it. Only the system
            # prompt above is localized so the LLM judge reads its calibration
            # in the user's language (no internal translation step).
            LLMMessage(role="system", content=ACCORD_TEXT),
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ], user_prompt
