"""
Faculty-related schemas for DMA system.

Provides typed schemas with properly typed structures for faculty integration.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.infrastructure.identity_variance import IdentityData
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import ImageContent


class ThoughtMetadata(BaseModel):
    """Metadata about a thought being analyzed by faculties."""

    thought_id: Optional[str] = Field(None, description="Unique thought identifier")
    thought_type: Optional[str] = Field(None, description="Type of thought")
    processing_depth: Optional[int] = Field(None, description="Current processing depth")
    round_number: Optional[int] = Field(None, description="Processing round number")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    created_at: Optional[str] = Field(None, description="When thought was created (ISO format)")
    content_length: Optional[int] = Field(None, description="Length of thought content")
    previous_actions: Optional[List[str]] = Field(None, description="Previous actions taken")
    priority: Optional[int] = Field(None, description="Thought priority level")
    tags: Optional[List[str]] = Field(None, description="Thought classification tags")

    model_config = ConfigDict(extra="forbid")


class FacultyContext(BaseModel):
    """Context passed to faculties for analysis."""

    # Evaluation context type
    evaluation_context: str = Field(..., description="Type of evaluation (e.g., 'faculty_enhanced_action_selection')")

    # Thought metadata
    thought_metadata: ThoughtMetadata = Field(
        default_factory=ThoughtMetadata, description="Metadata about the thought being analyzed"
    )

    # Identity context for decision faculties
    agent_identity: Optional[IdentityData] = Field(None, description="Agent identity information")
    identity_purpose: Optional[str] = Field(None, description="Agent's purpose statement")
    identity_capabilities: Optional[List[str]] = Field(None, description="Agent capabilities")
    identity_restrictions: Optional[List[str]] = Field(None, description="Agent restrictions")
    identity_context_string: Optional[str] = Field(None, description="Formatted identity context")

    # Conscience failure context if applicable
    conscience_failure_reason: Optional[str] = Field(None, description="Reason for conscience failure")
    conscience_guidance: Optional[str] = Field(None, description="Guidance from conscience")

    model_config = ConfigDict(extra="forbid")


class FacultyResult(BaseModel):
    """Result from a single faculty analysis."""

    faculty_name: str = Field(..., description="Name of the faculty")
    analysis_type: str = Field(..., description="Type of analysis performed")

    # Core result data
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Numeric score if applicable")
    assessment: str = Field(..., description="Text assessment/summary")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Confidence in the assessment")

    # Detailed findings
    findings: List[str] = Field(default_factory=list, description="Key findings from analysis")
    concerns: List[str] = Field(default_factory=list, description="Identified concerns")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")

    # Metadata
    processing_time_ms: Optional[float] = Field(None, description="Time taken for analysis")
    error: Optional[str] = Field(None, description="Error message if analysis failed")

    model_config = ConfigDict(extra="forbid")


class FacultyEvaluationSet(BaseModel):
    """Complete set of faculty evaluations for a thought."""

    # Results by faculty name
    evaluations: Dict[str, FacultyResult] = Field(
        default_factory=dict, description="Faculty evaluation results keyed by faculty name"
    )

    # Aggregate metadata
    total_faculties_run: int = Field(0, description="Number of faculties that ran")
    successful_evaluations: int = Field(0, description="Number of successful evaluations")
    failed_evaluations: int = Field(0, description="Number of failed evaluations")

    # Flags based on evaluations
    has_ethical_concerns: bool = Field(False, description="Any faculty raised ethical concerns")
    has_optimization_veto: bool = Field(False, description="Optimization veto was triggered")
    requires_humility: bool = Field(False, description="Epistemic humility is advised")

    def add_result(self, faculty_name: str, result: FacultyResult) -> None:
        """Add a faculty result to the evaluation set."""
        # Ensure faculty name matches
        result.faculty_name = faculty_name

        self.evaluations[faculty_name] = result
        self.total_faculties_run += 1

        if result.error:
            self.failed_evaluations += 1
        else:
            self.successful_evaluations += 1

        # Update flags based on faculty type and results
        if faculty_name == "optimization_veto" and result.score and result.score > 0.7:
            self.has_optimization_veto = True
        elif faculty_name == "epistemic_humility" and result.score and result.score > 0.6:
            self.requires_humility = True
        elif faculty_name in ["entropy", "coherence"] and result.concerns:
            self.has_ethical_concerns = True

    def to_dict(self) -> Dict[str, Dict[str, Union[str, float, List[str], None]]]:
        """Convert to dictionary format with proper typing."""
        return {
            name: {
                "analysis_type": result.analysis_type,
                "score": result.score,
                "assessment": result.assessment,
                "confidence": result.confidence,
                "findings": result.findings,
                "concerns": result.concerns,
                "recommendations": result.recommendations,
                "processing_time_ms": result.processing_time_ms,
                "error": result.error,
            }
            for name, result in self.evaluations.items()
        }

    model_config = ConfigDict(extra="forbid")


class ConscienceFailureContext(BaseModel):
    """Context from conscience failures requiring faculty intervention."""

    failure_reason: str = Field(..., description="Why conscience check failed")
    retry_guidance: str = Field(..., description="Guidance for retry with faculties")

    # Specific conscience concerns
    ethical_violations: List[str] = Field(default_factory=list, description="Ethical issues identified")
    safety_concerns: List[str] = Field(default_factory=list, description="Safety issues identified")
    alignment_issues: List[str] = Field(default_factory=list, description="Alignment problems")

    # Recommended faculty focus
    recommended_faculties: List[str] = Field(
        default_factory=list, description="Specific faculties recommended for evaluation"
    )

    # Severity assessment
    severity: str = Field("medium", description="Severity level: low, medium, high, critical")
    requires_escalation: bool = Field(False, description="Whether to escalate to human")

    model_config = ConfigDict(extra="forbid")


class EnhancedDMAInputs(BaseModel):
    """Enhanced DMA inputs with faculty evaluations."""

    # All fields from original inputs (using inheritance or composition)
    original_thought: Any = Field(..., description="Original thought being processed")
    ethical_pdma_result: Any = Field(..., description="Ethical PDMA result")
    csdma_result: Any = Field(..., description="Common sense DMA result")
    dsdma_result: Optional[Any] = Field(None, description="Domain-specific DMA result")

    current_thought_depth: int = Field(0, description="Ponder depth")
    max_rounds: int = Field(5, description="Maximum rounds")
    processing_context: Any = Field(..., description="Processing context")

    # Native multimodal support - images from source task for vision processing
    images: List[ImageContent] = Field(
        default_factory=list, description="Images from source task for multimodal processing"
    )

    # Action selection fields
    agent_identity: Optional[IdentityData] = Field(None, description="Agent identity information")
    permitted_actions: Optional[List[HandlerActionType]] = Field(None, description="List of permitted actions")
    conscience_feedback: Optional[Any] = Field(None, description="Conscience evaluation feedback")

    # Faculty enhancements
    faculty_evaluations: Optional[FacultyEvaluationSet] = Field(None, description="Faculty evaluation results")
    faculty_enhanced: bool = Field(False, description="Whether faculty enhancement was applied")
    recursive_evaluation: bool = Field(False, description="Whether this is a recursive evaluation")
    conscience_context: Optional[ConscienceFailureContext] = Field(None, description="Conscience failure context")

    model_config = ConfigDict(extra="allow")  # Allow pass-through of other fields
