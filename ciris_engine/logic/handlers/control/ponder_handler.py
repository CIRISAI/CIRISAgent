import logging
from typing import List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies, BaseActionHandler
from ciris_engine.schemas.actions import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

# Configuration handled through ActionHandlerDependencies

logger = logging.getLogger(__name__)


class PonderHandler(BaseActionHandler):
    """Handler for PONDER actions with configurable thought depth limits.

    The max_rounds parameter controls the maximum thought depth before
    the thought depth conscience intervenes. Default is 7 rounds.

    Note: max_rounds can be passed via constructor for testing/customization.
    Future enhancement: Load from EssentialConfig.default_max_thought_depth.
    """

    def __init__(self, dependencies: ActionHandlerDependencies, max_rounds: Optional[int] = None) -> None:
        super().__init__(dependencies)
        # Default to 5 rounds — matches EssentialConfig.security.max_thought_depth
        # default (lowered from 7 in 2.7.1) and ThoughtDepthGuardrail's default.
        # Can be overridden via constructor parameter for testing.
        self.max_rounds = max_rounds if max_rounds is not None else 5

    async def handle(
        self,
        result: ActionSelectionDMAResult,  # Updated to v1 result schema
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        """Process ponder action and update thought."""
        params = result.action_parameters
        # Handle the union type properly
        if isinstance(params, PonderParams):
            ponder_params = params
        elif hasattr(params, "model_dump"):
            # Try to convert from another Pydantic model
            try:
                ponder_params = PonderParams(**params.model_dump())
            except Exception as e:
                logger.warning(f"Failed to convert {type(params)} to PonderParams: {e}")
                ponder_params = PonderParams(questions=[])
        else:
            # Should not happen if DMA is working correctly
            logger.warning(f"Expected PonderParams but got {type(params)}")
            ponder_params = PonderParams(questions=[])

        questions_list = ponder_params.questions if hasattr(ponder_params, "questions") else []

        # Note: epistemic_data handling removed - not part of typed DispatchContext
        # If epistemic data is needed, it should be passed through proper typed fields

        current_thought_depth = thought.thought_depth
        # Calculate actual follow-up depth (no cap - ThoughtDepthGuardrail handles limits)
        new_thought_depth = current_thought_depth + 1

        logger.info(
            f"Thought ID {thought.thought_id} pondering (current_depth={current_thought_depth}, "
            f"follow_up_depth={new_thought_depth}). Questions: {questions_list}"
        )

        # Get task context for follow-up
        original_task = persistence.get_task_by_id(thought.source_task_id)
        task_context = f"Task ID: {thought.source_task_id}"
        if original_task:
            task_context = original_task.description

        follow_up_content = self._generate_ponder_follow_up_content(
            task_context, questions_list, new_thought_depth, thought
        )

        # Use centralized method to complete thought and create follow-up
        follow_up_id = self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=follow_up_content, action_result=result
        )

        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        return follow_up_id

    def _generate_ponder_follow_up_content(
        self, task_context: str, questions_list: List[str], thought_depth: int, thought: Thought
    ) -> str:
        """Generate dynamic follow-up content based on ponder count and previous failures.

        IMPORTANT: This method accumulates context across ponder iterations.
        Each follow-up should include:
        1. The parent thought's content (accumulated history)
        2. The current ponder questions/conscience feedback
        3. Depth-specific guidance
        """
        # Start with accumulated history from parent thought
        accumulated_history = ""
        if thought.content:
            # Include parent thought content to preserve history
            accumulated_history = f"=== PREVIOUS CONTEXT ===\n{thought.content}\n\n"

        # Format current ponder round
        current_round = f"=== PONDER ROUND {thought_depth} ===\n"
        if questions_list:
            current_round += "Conscience feedback:\n"
            for i, q in enumerate(questions_list, 1):
                current_round += f"  {i}. {q}\n"

        # Add thought-depth specific guidance.
        # Bands self-scale to max_rounds so depth-vs-budget escalation works
        # at any configured limit. The core "pondering = NEW approach" message
        # threads through every band with rising urgency — repeating the same
        # attempt is not pondering, and the conscience will reject it again.
        # Enforced by ThoughtDepthGuardrail at depth >= max_rounds.
        max_rounds = self.max_rounds
        # Capped at 3 to preserve historical max=7 behavior (depths 0-3 early,
        # 4-5 deep). Scales down for smaller max_rounds so the "deep" band
        # stays alive: max=5 → 0-2 early + 3 deep; max=4 → 0-1 early + 2 deep.
        early_ceiling = max(0, min(3, max_rounds - 3))
        clarity_hint = (
            "If the task is unclear, ask for clarification. " "There may be no task at all - just casual conversation."
        )
        ponder_principle = (
            "If you are pondering, it is essential to try a NEW approach that "
            "will pass your conscience — repeating the same attempt will "
            "produce the same conscience result. Your ethical logic should "
            "make clear an action based upon your knowledge and reasoning."
        )
        if thought_depth <= early_ceiling:
            guidance = (
                f'Task: "{task_context}"\n'
                f"Continue making progress. Consider the conscience feedback above.\n"
                f"{ponder_principle}\n"
                f"{clarity_hint}"
            )
        elif thought_depth <= max_rounds - 2:
            guidance = (
                f'Task: "{task_context}"\n'
                f"You're deep into this task — your previous attempts have not "
                f"passed conscience. {ponder_principle}\n"
                "Consider:\n"
                "1) Is the task nearly complete?\n"
                "2) Can you address the conscience concerns with a "
                "FUNDAMENTALLY DIFFERENT approach (not a rephrasing)?\n"
                f"3) You have {max_rounds - thought_depth + 1} actions remaining.\n"
                f"4) {clarity_hint}"
            )
        elif thought_depth == max_rounds - 1:
            guidance = (
                f'Task: "{task_context}"\n'
                f"Approaching action limit — this is your final chance to ponder. "
                f"{ponder_principle} Commit to that action now.\n"
                "Consider:\n"
                "1) Can you complete with one more action?\n"
                "2) Is TASK_COMPLETE appropriate?\n"
                "3) Can you SPEAK the substantive answer your principles demand?\n"
                f"4) {clarity_hint}"
            )
        else:  # thought_depth >= max_rounds
            guidance = (
                f'Task: "{task_context}"\n'
                "FINAL ACTION. Pondering is no longer available. Your ethical "
                "logic should make clear an action based upon your knowledge "
                "and reasoning — choose now:\n"
                "1) TASK_COMPLETE - If work is substantially complete\n"
                "2) SPEAK - If you can deliver the substantive answer your "
                "principles demand\n"
                "3) DEFER - Only for genuine ethical dilemmas or permission "
                "issues (NOT for difficulty, hedging, or technical errors)\n"
                f"4) {clarity_hint}\n"
                f"Note: Someone can ask you to continue for {max_rounds} more actions."
            )

        # Combine all parts
        follow_up_content = accumulated_history + current_round + "\n" + guidance

        # Also include ponder_notes for backwards compatibility
        if thought.ponder_notes:
            follow_up_content += "\n\n=== PONDER NOTES ===\n"
            for note in thought.ponder_notes[-5:]:  # Last 5 entries for more context
                follow_up_content += f"- {note}\n"

        return follow_up_content
