"""Faculty integration for Action Selection PDMA."""

import logging
from typing import Any, Dict, Optional

from ciris_engine.protocols.faculties import EpistemicFaculty
from ciris_engine.schemas.dma.faculty import (
    ConscienceFailureContext,
    EnhancedDMAInputs,
    FacultyContext,
    FacultyEvaluationSet,
    ThoughtMetadata,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class FacultyIntegration:
    """Handles epistemic faculty integration for enhanced action selection."""

    def __init__(self, faculties: Dict[str, EpistemicFaculty]):
        self.faculties = faculties

    async def apply_faculties_to_content(
        self, content: str, context: Optional[FacultyContext] = None
    ) -> FacultyEvaluationSet:
        """Apply available epistemic faculties to content - consolidated approach."""
        results = FacultyEvaluationSet()

        # Group 1: Content Analysis Faculties (entropy, coherence)
        # These analyze the output content and need minimal context
        content_faculties = {
            name: faculty for name, faculty in self.faculties.items() if name in ["entropy", "coherence"]
        }

        # Group 2: Decision Analysis Faculties (optimization_veto, epistemic_humility)
        # These analyze the action decision and need full identity context
        decision_faculties = {
            name: faculty
            for name, faculty in self.faculties.items()
            if name in ["optimization_veto", "epistemic_humility"]
        }

        # Call content faculties with minimal context (just the content)
        minimal_context = FacultyContext(
            evaluation_context=context.evaluation_context if context else "content_analysis",
            thought_metadata=context.thought_metadata if context else ThoughtMetadata(),
        )

        for name, faculty in content_faculties.items():
            try:
                # Faculty analyze expects FacultyContext | None
                result = await faculty.analyze(content, minimal_context)
                results.add_result(name, result)
            except Exception as e:
                logger.warning(f"Content faculty {name} evaluation failed: {e}")

        # Call decision faculties with full identity context
        for name, faculty in decision_faculties.items():
            try:
                # These faculties need the full context including identity
                # Faculty analyze expects FacultyContext | None
                result = await faculty.analyze(content, context)
                results.add_result(name, result)
            except Exception as e:
                logger.warning(f"Decision faculty {name} evaluation failed: {e}")

        return results

    def build_faculty_insights_string(self, faculty_results: FacultyEvaluationSet) -> str:
        """Build a formatted string of faculty insights for prompt injection."""
        if not faculty_results or not faculty_results.evaluations:
            return ""

        faculty_insights_str = "\n\nEPISTEMIC FACULTY INSIGHTS:\n"
        for faculty_name, result in faculty_results.evaluations.items():
            faculty_insights_str += f"- {faculty_name}: {result.assessment}\n"
            if result.concerns:
                faculty_insights_str += f"  Concerns: {', '.join(result.concerns)}\n"
            if result.recommendations:
                faculty_insights_str += f"  Recommendations: {', '.join(result.recommendations)}\n"
        faculty_insights_str += "\nConsider these faculty evaluations in your decision-making process.\n"

        return faculty_insights_str

    async def enhance_evaluation_with_faculties(
        self,
        original_thought: Thought,
        triaged_inputs: JSONDict,
        conscience_failure_context: Optional[ConscienceFailureContext] = None,
    ) -> EnhancedDMAInputs:
        """Enhance triaged inputs with faculty evaluations."""

        # Extract identity context from processing context (ThoughtContext)
        identity_context = {}
        processing_context = triaged_inputs.get("processing_context")

        if processing_context:
            # Handle both dict and ThoughtContext object
            if hasattr(processing_context, "system_snapshot"):
                system_snapshot = processing_context.system_snapshot
                if system_snapshot:
                    # Extract identity data from system snapshot
                    identity_context = {
                        "agent_identity": getattr(system_snapshot, "agent_identity", {}),
                        "identity_purpose": getattr(system_snapshot, "identity_purpose", ""),
                        "identity_capabilities": getattr(system_snapshot, "identity_capabilities", []),
                        "identity_restrictions": getattr(system_snapshot, "identity_restrictions", []),
                    }
            elif isinstance(processing_context, dict) and "system_snapshot" in processing_context:
                system_snapshot = processing_context["system_snapshot"]
                if isinstance(system_snapshot, dict):
                    identity_context = {
                        "agent_identity": system_snapshot.get("agent_identity", {}),
                        "identity_purpose": system_snapshot.get("identity_purpose", ""),
                        "identity_capabilities": system_snapshot.get("identity_capabilities", []),
                        "identity_restrictions": system_snapshot.get("identity_restrictions", []),
                    }

            # Also extract identity_context string if available
            if hasattr(processing_context, "identity_context"):
                identity_context["identity_context_string"] = processing_context.identity_context
            elif isinstance(processing_context, dict):
                identity_context["identity_context_string"] = processing_context.get("identity_context", "")

        # Apply faculties to the thought content with enhanced context
        context = FacultyContext(
            evaluation_context="faculty_enhanced_action_selection",
            thought_metadata={
                "thought_id": original_thought.thought_id,
                "thought_type": (
                    original_thought.thought_type.value
                    if hasattr(original_thought.thought_type, "value")
                    else str(original_thought.thought_type)
                ),
                "source_task_id": original_thought.source_task_id,
            },
            **identity_context,
            conscience_failure_reason=conscience_failure_context.failure_reason if conscience_failure_context else None,
            conscience_guidance=conscience_failure_context.retry_guidance if conscience_failure_context else None,
        )

        faculty_results = await self.apply_faculties_to_content(content=str(original_thought.content), context=context)

        logger.debug(f"Faculty evaluation results for thought {original_thought.thought_id}: {faculty_results}")

        # Create enhanced inputs with typed model
        enhanced_inputs = EnhancedDMAInputs(
            original_thought=triaged_inputs["original_thought"],
            ethical_pdma_result=triaged_inputs["ethical_pdma_result"],
            csdma_result=triaged_inputs["csdma_result"],
            dsdma_result=triaged_inputs.get("dsdma_result"),
            current_thought_depth=triaged_inputs["current_thought_depth"],
            max_rounds=triaged_inputs["max_rounds"],
            processing_context=triaged_inputs["processing_context"],
            faculty_evaluations=faculty_results,
            faculty_enhanced=True,
            recursive_evaluation=False,
            conscience_context=conscience_failure_context,
            images=triaged_inputs.get("images", []),  # Pass through images for vision
        )

        # Copy any additional fields from triaged_inputs
        for key, value in triaged_inputs.items():
            if key not in enhanced_inputs.model_fields_set:
                setattr(enhanced_inputs, key, value)

        return enhanced_inputs

    def add_faculty_metadata_to_result(
        self, result: ActionSelectionDMAResult, faculty_enhanced: bool = False, recursive_evaluation: bool = False
    ) -> ActionSelectionDMAResult:
        """Add faculty-related metadata to the action selection result."""

        if not faculty_enhanced:
            return result

        metadata_suffix = "\n\nNote: This decision incorporated insights from epistemic faculties"
        if recursive_evaluation:
            metadata_suffix += " through recursive evaluation due to conscience failure"
        metadata_suffix += "."

        updated_rationale = result.rationale + metadata_suffix

        return ActionSelectionDMAResult(
            selected_action=result.selected_action,
            action_parameters=result.action_parameters,
            rationale=updated_rationale,
            resource_usage=result.resource_usage,
        )
