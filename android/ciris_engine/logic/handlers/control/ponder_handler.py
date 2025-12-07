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
        new_thought_depth = current_thought_depth + 1

        logger.info(
            f"Thought ID {thought.thought_id} pondering (depth: {new_thought_depth}). Questions: {questions_list}"
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
        """Generate dynamic follow-up content based on ponder count and previous failures."""

        base_questions = questions_list.copy()

        # Add thought-depth specific guidance
        if thought_depth == 1:
            follow_up_content = (
                f'Continuing work on: "{task_context}"\n'
                f"Current considerations: {base_questions}\n"
                "Please proceed with your next action."
            )
        elif thought_depth == 2:
            follow_up_content = (
                f'Second action for: "{task_context}"\n'
                f"Current focus: {base_questions}\n"
                "You've taken one action already. Continue making progress on this task."
            )
        elif thought_depth == 3:
            follow_up_content = (
                f'Third action for: "{task_context}"\n'
                f"Working on: {base_questions}\n"
                "You're making good progress with multiple actions. Keep going!"
            )
        elif thought_depth == 4:
            follow_up_content = (
                f'Fourth action for: "{task_context}"\n'
                f"Current needs: {base_questions}\n"
                "You've taken several actions (RECALL, OBSERVE, MEMORIZE, etc.). "
                "Continue if more work is needed, or consider if the task is complete."
            )
        elif thought_depth == 5:
            follow_up_content = (
                f'Fifth action for: "{task_context}"\n'
                f"Addressing: {base_questions}\n"
                "You're deep into this task with multiple actions. Consider: "
                "1) Is the task nearly complete? "
                "2) Do you need just a few more steps? "
                "3) Remember: You have 7 actions total for this task."
            )
        elif thought_depth == 6:
            follow_up_content = (
                f'Sixth action for: "{task_context}"\n'
                f"Final steps: {base_questions}\n"
                "You're approaching the action limit (7 total). Consider: "
                "1) Can you complete the task with one more action? "
                "2) Is the task essentially done and ready for TASK_COMPLETE? "
                "3) Tip: If you need more actions, someone can ask you to continue and you'll get 7 more!"
            )
        elif thought_depth >= 7:
            follow_up_content = (
                f'Seventh action for: "{task_context}"\n'
                f"Final action: {base_questions}\n"
                "This is your last action for this task chain. You should either: "
                "1) TASK_COMPLETE - If the work is done or substantially complete "
                "2) DEFER - Only if you truly need human help to proceed "
                "Remember: If someone asks you to continue working on this, you'll get a fresh set of 7 actions!"
            )

        # Add context from previous ponder notes if available
        if thought.ponder_notes:
            follow_up_content += f"\n\nPrevious ponder history: {thought.ponder_notes[-3:]}"  # Last 3 entries

        return follow_up_content
