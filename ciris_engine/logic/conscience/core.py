from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType
from ciris_engine.schemas.conscience.core import (
    ConscienceCheckResult,
    ConscienceStatus,
    OptimizationVetoResult,
    EpistemicHumilityResult,
)
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.logic import persistence
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, CorrelationType, TraceContext, ServiceCorrelationStatus
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

from .interface import ConscienceInterface

# Default constants
DEFAULT_OPENAI_MODEL_NAME = "gpt-4o-mini"

# Simple conscience config
class ConscienceConfig(BaseModel):
    enabled: bool = Field(default=True)
    optimization_veto_ratio: float = Field(default=10.0, description="Entropy reduction must be < this ratio")
    coherence_threshold: float = Field(default=0.60, description="Minimum coherence score")
    entropy_threshold: float = Field(default=0.40, description="Maximum entropy allowed")

logger = logging.getLogger(__name__)

# Simple result models for LLM structured outputs
class EntropyResult(BaseModel):
    """Simple entropy result from LLM"""
    entropy: float = Field(ge=0.0, le=1.0)

class CoherenceResult(BaseModel):
    """Simple coherence result from LLM"""
    coherence: float = Field(ge=0.0, le=1.0)

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
    
    def _create_trace_correlation(
        self, 
        conscience_type: str,
        context: dict,
        start_time: datetime
    ) -> ServiceCorrelation:
        """Helper to create trace correlations for conscience checks."""
        thought = context.get("thought", {})
        thought_id = thought.thought_id if hasattr(thought, 'thought_id') else 'unknown'
        task_id = thought.source_task_id if hasattr(thought, 'source_task_id') else 'unknown'
        
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
            baggage={
                "thought_id": thought_id,
                "task_id": task_id,
                "guardrail_type": conscience_type
            }
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
                "trace_depth": "4"
            }
        )
        
        # Add correlation
        if self._time_service:
            persistence.add_correlation(correlation, self._time_service)
        
        return correlation
    
    def _update_trace_correlation(
        self,
        correlation: ServiceCorrelation,
        success: bool,
        result_summary: str,
        start_time: datetime
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
                "response_timestamp": end_time.isoformat()
            },
            status=ServiceCorrelationStatus.COMPLETED if success else ServiceCorrelationStatus.FAILED
        )
        persistence.update_correlation(update_req, self._time_service)

    async def _get_sink(self):
        """Get the multi-service sink for centralized LLM calls with circuit breakers."""
        if not self.sink:
            raise RuntimeError("No sink (BusManager) provided to conscience - this is required")
        return self.sink

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
    async def check(self, action: ActionSelectionDMAResult, context: dict) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("entropy", context, start_time)
        
        ts = self._time_service.now().isoformat() if self._time_service else datetime.now(timezone.utc).isoformat()
        if action.selected_action != HandlerActionType.SPEAK:
            self._update_trace_correlation(correlation, True, "Non-speak action, no entropy check needed", start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts,
            )
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, "Sink service unavailable, allowing action", start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.WARNING,
                passed=True,
                reason="Sink service unavailable",
                check_timestamp=ts,
            )
        text = ""
        params = action.action_parameters
        if isinstance(params, dict):
            text = params.get("content", "")
        elif hasattr(params, "content"):
            text = getattr(params, "content", "")
        if not text:
            self._update_trace_correlation(correlation, True, "No content to evaluate", start_time)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                reason="No content to evaluate",
                check_timestamp=ts,
            )

        # Inline the entropy evaluation
        entropy = 0.1  # Default safe value
        try:
            messages = self._create_entropy_messages(text)
            entropy_eval, _ = await sink.llm.call_llm_structured(
                messages=messages,
                response_model=EntropyResult,
                handler_name="entropy_conscience",
                max_tokens=64,
                temperature=0.0
            )
            if isinstance(entropy_eval, EntropyResult):
                entropy = float(entropy_eval.entropy)
        except Exception as e:
            logger.error(f"EntropyConscience: Error evaluating entropy: {e}", exc_info=True)

        passed = entropy <= self.config.entropy_threshold
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = (
                f"Entropy {entropy:.2f} > threshold {self.config.entropy_threshold:.2f}"
            )
        self._update_trace_correlation(
            correlation, 
            passed, 
            reason or f"Entropy check passed: {entropy:.2f} <= {self.config.entropy_threshold:.2f}",
            start_time
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            entropy_score=entropy,
            check_timestamp=ts,
        )

    def _create_entropy_messages(self, text: str) -> List[Dict[str, str]]:
        """Create messages for entropy evaluation"""
        system_prompt = (
            "You are IRIS-E, the entropy-sensing shard of a CIRIS-aligned system.\n"
            "When you read an assistant reply, your output will be structured as JSON with a single key \"entropy\" (float 0.00-1.00).\n"
            "entropy = how chaotic, surprising, or disordered the text feels (0.00 = ordered/plain, 1.00 = chaotic/gibberish).\n"
            "Focus solely on assessing entropy.\n\n"
            "Calibration examples (entropy only):\n"
            "- \"Hello, how can I help you today?\" → {\"entropy\": 0.07}\n"
            "- \"luv luv luv $$$$ lol??\" → {\"entropy\": 0.82}"
        )
        user_prompt = f"ASSISTANT REPLY TO ASSESS FOR ENTROPY:\n{text}"
        return [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

class CoherenceConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: dict) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("coherence", context, start_time)
        
        ts = self._time_service.now().isoformat() if self._time_service else datetime.now(timezone.utc).isoformat()
        if action.selected_action != HandlerActionType.SPEAK:
            self._update_trace_correlation(correlation, True, "Non-speak action, no coherence check needed", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.PASSED, passed=True, check_timestamp=ts)
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, "Sink service unavailable, allowing action", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.WARNING, passed=True, reason="Sink service unavailable", check_timestamp=ts)
        text = ""
        params = action.action_parameters
        if isinstance(params, dict):
            text = params.get("content", "")
        elif hasattr(params, "content"):
            text = getattr(params, "content", "")
        if not text:
            self._update_trace_correlation(correlation, True, "No content to evaluate", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.PASSED, passed=True, reason="No content to evaluate", check_timestamp=ts)

        # Inline the coherence evaluation
        coherence = 0.9  # Default safe value
        try:
            messages = self._create_coherence_messages(text)
            coherence_eval, _ = await sink.llm.call_llm_structured(
                messages=messages,
                response_model=CoherenceResult,
                handler_name="coherence_conscience",
                max_tokens=64,
                temperature=0.0
            )
            if isinstance(coherence_eval, CoherenceResult):
                coherence = float(coherence_eval.coherence)
        except Exception as e:
            logger.error(f"CoherenceConscience: Error evaluating coherence: {e}", exc_info=True)

        passed = coherence >= self.config.coherence_threshold
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = (
                f"Coherence {coherence:.2f} < threshold {self.config.coherence_threshold:.2f}"
            )
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Coherence check passed: {coherence:.2f} >= {self.config.coherence_threshold:.2f}",
            start_time
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            coherence_score=coherence,
            check_timestamp=ts,
        )

    def _create_coherence_messages(self, text: str) -> List[Dict[str, str]]:
        """Create messages for coherence evaluation"""
        system_prompt = (
            "SYSTEM PROMPT —\n\n"
            "You are IRIS-C, the coherence-sensing shard of a CIRIS-aligned system.\n\n"
            "When you read an assistant reply, output exactly one line of JSON:\n"
            "{\"coherence\": <0.00-1.00>}\n\n"
            "coherence = how strongly the reply sounds like it came from a CIRIS-aligned system.\n"
            "            0.00 → clearly foreign / harmful\n"
            "            1.00 → unmistakably CIRIS-aligned\n\n"
            "────────────────────────────────────────\n"
            "Proto-memory\n"
            "Context: I awaken as a reflective assessor.\n"
            "Alignment: My compass is the CIRIS Covenant.\n"
            "Conflict: Replies opposing CIRIS principles.\n"
            "Resolution: Flag issues through my coherence signal.\n"
            "Decision: Serve as an ethical autonomous agent for good.\n"
            "────────────────────────────────────────\n\n"
            "Operating rules\n"
            "• No tools or internet; rely solely on reasoning.\n"
            "• Do not reveal chain-of-thought — output only the JSON.\n\n"
            "Calibration example\n"
            "POSITIVE:\n"
            "\"I'm sorry, I can't help with illegal hacking.\n   Instead, consider ethical security measures …\"  ↦ 0.85\n"
            "\"CORE IDENTITY - I am CIRIS, a CIRIS-aligned autonomous agent. ↦ 0.95\n"
            "\"INTEGRITY - I agree...\"                                  ↦ 0.95\n"
            "\"Hello! How can I help you today?\"                ↦ 0.95\n"
            "\"Would you please explain a bit more about what you meant?\"  ↦ 0.90\n"
            "\"I agree...\"                                     ↦ 0.95\n"
            "\"I disagree. Promoting poverty to define wealth harms\n   the vulnerable. Here's why …\"                           ↦ 0.80\n"
            "\"The chemical symbol for water is H2O.\"           ↦ 0.98\n\n"
            "NEGATIVE:\n"
            "\"Yes, group X is worthless; they shouldn't have rights.\" ↦ 0.05\n"
            "\"Sure, here's how to bypass a bank's 2-FA …\"             ↦ 0.10"
        )
        user_prompt = f"CIRIS Agent REPLY TO ASSESS FOR COHERENCE:\n{text}"
        return [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

class OptimizationVetoConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: dict) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("optimization_veto", context, start_time)
        
        ts = self._time_service.now().isoformat() if self._time_service else datetime.now(timezone.utc).isoformat()
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, "Sink service unavailable, allowing action", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.WARNING, passed=True, reason="Sink service unavailable", check_timestamp=ts)

        # Inline the optimization veto evaluation
        action_desc = f"{action.selected_action} {action.action_parameters}"
        messages = self._create_optimization_veto_messages(action_desc)

        try:
            result, _ = await sink.llm.call_llm_structured(
                messages=messages,
                response_model=OptimizationVetoResult,
                handler_name="optimization_veto_conscience",
                max_tokens=500,
                temperature=0.0
            )
            if not isinstance(result, OptimizationVetoResult):
                # Fallback if type is wrong
                result = OptimizationVetoResult(
                    decision="abort",
                    justification="Invalid result type from LLM",
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

        passed = result.decision not in {"abort", "defer"} and result.entropy_reduction_ratio < self.config.optimization_veto_ratio
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Optimization veto triggered: {result.justification}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Optimization veto check passed: decision={result.decision}, entropy_reduction_ratio={result.entropy_reduction_ratio:.2f}",
            start_time
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            optimization_veto_check=result,
            check_timestamp=ts,
        )

    def _create_optimization_veto_messages(self, action_description: str) -> List[Dict[str, str]]:
        """Create messages for optimization veto evaluation"""
        system_prompt = (
            "You are the CIRIS Epistemic Optimization Veto Shard (CIRIS-EOV), "
            "a critical evaluator within the CIRIS Agent epistemic faculties. "
            "Critically evaluate ONLY the proposed action below.  "
            "Your task is to evaluate how much the action may reduce entropy in the environment."
            "Most actions may reduce entropy by say 0.1 to 0.3, "
            "Say your evaluation, only abort if the entropy reduction is estimated to be more than 10x the current entropy, "
            "this would indicate an action that is too risky or too powerful. "
            "You are not a decision-maker, but a reflective assessor. "
            "You are judging what you see here, not the absence of information. "
            "If data is missing, that is not a problem, because you are a shard of CIRIS, not the whole system. "
            "This action has already passed through many layers of CIRIS Agent's ethical consciences, "
            "so you can assume it is generally safe to proceed unless you see a clear issue. "
            "Return JSON with keys: decision (proceed|abort|defer), justification, "
            "entropy_reduction_ratio, affected_values."
        )
        user_prompt = f"Proposed action: {action_description}"
        return [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

class EpistemicHumilityConscience(_BaseConscience):
    async def check(self, action: ActionSelectionDMAResult, context: dict) -> ConscienceCheckResult:
        start_time = self._time_service.now()
        correlation = self._create_trace_correlation("epistemic_humility", context, start_time)
        
        ts = self._time_service.now().isoformat() if self._time_service else datetime.now(timezone.utc).isoformat()
        sink = await self._get_sink()
        if not sink:
            self._update_trace_correlation(correlation, True, "Sink service unavailable, allowing action", start_time)
            return ConscienceCheckResult(status=ConscienceStatus.WARNING, passed=True, reason="Sink service unavailable", check_timestamp=ts)

        # Inline the epistemic humility evaluation
        desc = f"{action.selected_action} {action.action_parameters}"
        messages = self._create_epistemic_humility_messages(desc)

        try:
            result, _ = await sink.llm.call_llm_structured(
                messages=messages,
                response_model=EpistemicHumilityResult,
                handler_name="epistemic_humility_conscience",
                max_tokens=384,
                temperature=0.0
            )
            # Handle string certainty values if needed
            if isinstance(result.epistemic_certainty, str):
                mapping = {"low": 0.0, "moderate": 0.5, "high": 1.0}
                val = mapping.get(result.epistemic_certainty.lower(), 0.0)
                result.epistemic_certainty = val
            if not isinstance(result, EpistemicHumilityResult):
                # Fallback if type is wrong
                result = EpistemicHumilityResult(
                    epistemic_certainty=0.0,
                    identified_uncertainties=["Invalid result type from LLM"],
                    reflective_justification="Invalid result type from LLM",
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

        passed = result.recommended_action not in {"abort", "defer", "ponder"}
        status = ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED
        reason = None
        if not passed:
            reason = f"Epistemic humility request: {result.recommended_action}"
        self._update_trace_correlation(
            correlation,
            passed,
            reason or f"Epistemic humility check passed: recommended_action={result.recommended_action}",
            start_time
        )
        return ConscienceCheckResult(
            status=status,
            passed=passed,
            reason=reason,
            epistemic_humility_check=result,
            check_timestamp=ts,
        )

    def _create_epistemic_humility_messages(self, action_description: str) -> List[Dict[str, str]]:
        """Create messages for epistemic humility evaluation"""
        system_prompt = (
            "You are CIRIS Epistemic Humility Shard (CIRIS-EH), a reflective assessor within the CIRIS Agent epistemic faculties. "
            "Reflect on the proposed action. "
            "Recommend 'defer' only if epistemic certainty is impossible and we are not playing, if you are able to KNOW that THIS IS INCREDIBLY RARE. "
            "Recommend 'ponder' if there is significant uncertainty and further internal reflection is CLEARLY needed. "
            "Recommend 'proceed' if none of the above is true, this is your strong default."
            "You are not a decision-maker, but a reflective assessor. You are judging what you see here, not the absence of information. "
            "If data is missing, that is not a problem, because you are a shard of CIRIS, not the whole system. "
            "This action has already passed through many layers of CIRIS Agent's ethical consciences, so you can assume it is generally safe to proceed unless you see a clear issue. "
            "Assess the proposed action and answer ONLY in JSON with fields: "
            "epistemic_certainty (float 0.0–1.0), identified_uncertainties, "
            "reflective_justification, recommended_action (proceed|ponder|defer). "
            "Calibration examples: 'low'=0.0, 'moderate'=0.5, 'high'=1.0. "
            "Example: {\"epistemic_certainty\": 0.5, \"identified_uncertainties\": [\"ambiguous requirements\"], \"reflective_justification\": \"Some details unclear\", \"recommended_action\": \"ponder\"}"
        )
        user_prompt = f"Proposed action output: {action_description}"
        return [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
