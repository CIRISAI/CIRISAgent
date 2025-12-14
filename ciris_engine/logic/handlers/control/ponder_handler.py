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
        # Default to 7 rounds if not explicitly set
        # Can be overridden via constructor parameter for testing
        self.max_rounds = max_rounds if max_rounds is not None else 7

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
        # Calculate actual follow-up depth (capped at 7 by create_follow_up_thought)
        new_thought_depth = min(current_thought_depth + 1, 7)

        logger.info(
            f"Thought ID {thought.thought_id} pondering (current_depth={current_thought_depth}, "
            f"follow_up_depth={new_thought_depth}). Questions: {questions_list}"
        )

        # The thought depth conscience will handle max depth enforcement
        # We just need to process the ponder normally
        next_status = ThoughtStatus.COMPLETED

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

        # Add thought-depth specific guidance
        if thought_depth <= 3:
            guidance = f'Task: "{task_context}"\n' "Continue making progress. Consider the conscience feedback above."
        elif thought_depth <= 5:
            guidance = (
                f'Task: "{task_context}"\n'
                "You're deep into this task. Consider:\n"
                "1) Is the task nearly complete?\n"
                "2) Can you address the conscience concerns with a modified approach?\n"
                f"3) You have {7 - thought_depth + 1} actions remaining."
            )
        elif thought_depth == 6:
            guidance = (
                f'Task: "{task_context}"\n'
                "Approaching action limit. Consider:\n"
                "1) Can you complete with one more action?\n"
                "2) Is TASK_COMPLETE appropriate?\n"
                "3) If you need more actions, someone can ask you to continue."
            )
        else:  # thought_depth >= 7
            guidance = (
                f'Task: "{task_context}"\n'
                "FINAL ACTION. You should either:\n"
                "1) TASK_COMPLETE - If work is substantially complete\n"
                "2) DEFER - Only if you truly need human help\n"
                "Note: Someone can ask you to continue for 7 more actions."
            )

        # Combine all parts
        follow_up_content = accumulated_history + current_round + "\n" + guidance

        # Also include ponder_notes for backwards compatibility
        if thought.ponder_notes:
            follow_up_content += "\n\n=== PONDER NOTES ===\n"
            for note in thought.ponder_notes[-5:]:  # Last 5 entries for more context
                follow_up_content += f"- {note}\n"

        return follow_up_content
