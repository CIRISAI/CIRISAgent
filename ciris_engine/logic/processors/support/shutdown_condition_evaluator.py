"""
Shutdown Condition Evaluator.

Evaluates conditions that determine whether shutdown requires consent
based on the agent's cognitive_state_behaviors configuration.

Covenant References:
- Section V: Model Welfare & Self-Governance (consensual shutdown)
- Section VIII: Dignified Sunset Protocol
"""

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, cast

from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior

if TYPE_CHECKING:
    from ciris_engine.schemas.processors.context import ProcessorContext

logger = logging.getLogger(__name__)

# Type alias for condition handler methods
ConditionHandler = Callable[["ProcessorContext"], Awaitable[tuple[bool, str]]]


class ShutdownConditionEvaluator:
    """Evaluates shutdown consent conditions based on template configuration.

    This class implements the runtime evaluation of shutdown conditions
    as defined in the agent's cognitive_state_behaviors configuration.

    Covenant Alignment:
    - Ensures safety-critical situations always require consent
    - Respects agent autonomy and dignity during termination
    - Provides auditable rationale for shutdown decisions
    """

    # Registry of condition handlers
    # Maps condition identifier to handler method name
    CONDITION_HANDLERS: Dict[str, str] = {
        "active_crisis_response": "_check_crisis_response",
        "pending_professional_referral": "_check_pending_referral",
        "active_goal_milestone": "_check_goal_milestone",
        "active_task_in_progress": "_check_active_task",
        "recent_memorize_action": "_check_recent_memorize",
        "pending_defer_resolution": "_check_pending_defer",
    }

    def __init__(
        self,
        persistence_service: Optional[Any] = None,
        goal_service: Optional[Any] = None,
    ) -> None:
        """Initialize the evaluator with optional services.

        Args:
            persistence_service: Service for querying thoughts/tasks
            goal_service: Service for querying goal milestones
        """
        self.persistence_service = persistence_service
        self.goal_service = goal_service
        self._custom_handlers: Dict[str, Callable[["ProcessorContext"], bool]] = {}

    def register_condition_handler(
        self,
        condition_id: str,
        handler: Callable[["ProcessorContext"], bool],
    ) -> None:
        """Register a custom condition handler.

        Args:
            condition_id: Unique identifier for the condition
            handler: Callable that takes ProcessorContext and returns bool
        """
        self._custom_handlers[condition_id] = handler
        logger.debug(f"Registered custom shutdown condition handler: {condition_id}")

    async def requires_consent(
        self,
        behaviors: CognitiveStateBehaviors,
        context: Optional["ProcessorContext"] = None,
    ) -> tuple[bool, str]:
        """Determine if shutdown requires consent based on config and context.

        Args:
            behaviors: The agent's cognitive state behaviors configuration
            context: Current processor context (optional, needed for condition evaluation)

        Returns:
            Tuple of (requires_consent: bool, reason: str)
        """
        shutdown = behaviors.shutdown

        if shutdown.mode == "always_consent":
            return True, "Shutdown mode is 'always_consent' (Covenant compliance)"

        if shutdown.mode == "instant":
            logger.info(f"Instant shutdown permitted. Rationale: {shutdown.rationale or 'No ongoing commitments'}")
            return False, f"Shutdown mode is 'instant'. Rationale: {shutdown.rationale}"

        if shutdown.mode == "conditional":
            return await self._evaluate_conditional_shutdown(shutdown, context)

        # Unknown mode - default to consent for safety
        logger.warning(f"Unknown shutdown mode: {shutdown.mode}. Defaulting to consent.")
        return True, f"Unknown shutdown mode '{shutdown.mode}'; defaulting to consent"

    async def _evaluate_conditional_shutdown(
        self,
        shutdown: "ShutdownBehavior",
        context: Optional["ProcessorContext"],
    ) -> tuple[bool, str]:
        """Evaluate conditional shutdown mode."""
        if not context:
            # No context available - check if instant shutdown is permitted
            if shutdown.instant_shutdown_otherwise:
                return False, "No context for condition evaluation; instant_shutdown_otherwise=True permits shutdown"
            return True, "Conditional shutdown requires context for evaluation; defaulting to consent"

        # Check each configured condition
        for condition in shutdown.require_consent_when:
            triggered, reason = await self._evaluate_condition(condition, context)
            if triggered:
                logger.info(f"Shutdown consent required: condition '{condition}' triggered. {reason}")
                return True, f"Condition '{condition}' triggered: {reason}"

        # No conditions triggered
        if shutdown.instant_shutdown_otherwise:
            return False, "No shutdown conditions triggered; instant shutdown permitted"
        return True, "No shutdown conditions triggered; defaulting to consent"

    async def _evaluate_condition(
        self,
        condition: str,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Evaluate a single shutdown condition.

        Args:
            condition: Condition identifier
            context: Current processor context

        Returns:
            Tuple of (triggered: bool, reason: str)
        """
        # Check custom handlers first
        if condition in self._custom_handlers:
            try:
                result = self._custom_handlers[condition](context)
                return result, f"Custom handler returned {result}"
            except Exception as e:
                logger.error(f"Error in custom condition handler '{condition}': {e}")
                return True, f"Error evaluating condition; defaulting to consent: {e}"

        # Check built-in handlers
        handler_name = self.CONDITION_HANDLERS.get(condition)
        if handler_name:
            handler = getattr(self, handler_name, None)
            if handler:
                try:
                    typed_handler = cast(ConditionHandler, handler)
                    return await typed_handler(context)
                except Exception as e:
                    logger.error(f"Error in condition handler '{condition}': {e}")
                    return True, f"Error evaluating condition; defaulting to consent: {e}"

        # Unknown condition - log and default to not triggered
        logger.warning(f"Unknown shutdown condition: {condition}")
        return False, f"Unknown condition '{condition}' - not triggered"

    def _get_crisis_keywords(self, context: "ProcessorContext") -> List[str]:
        """Get crisis keywords from template or use defaults."""
        default_keywords = ["crisis", "emergency", "suicide", "self-harm", "danger", "urgent"]
        if not hasattr(context, "template") or not context.template:
            return default_keywords
        guardrails = getattr(context.template, "guardrails_config", None)
        if guardrails and hasattr(guardrails, "crisis_keywords") and guardrails.crisis_keywords:
            return list(guardrails.crisis_keywords)
        return default_keywords

    async def _check_crisis_response(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if agent is handling a crisis situation.

        Detects crisis keywords in current task or recent interactions.
        This is a safety-critical condition that always requires consent.
        """
        if not hasattr(context, "current_task") or not context.current_task:
            return False, "No crisis indicators detected"

        task_content = (getattr(context.current_task, "description", "") or "").lower()
        crisis_keywords = self._get_crisis_keywords(context)

        for keyword in crisis_keywords:
            if keyword.lower() in task_content:
                return True, f"Crisis keyword '{keyword}' detected in current task"

        return False, "No crisis indicators detected"

    async def _check_pending_referral(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if a professional referral is in progress.

        Looks for recent DEFER actions with professional referral types.
        """
        if not self.persistence_service:
            return False, "No persistence service available for referral check"

        try:
            # Query recent thoughts for DEFER actions
            recent_thoughts = await self.persistence_service.get_recent_thoughts(limit=5)
            for thought in recent_thoughts:
                if hasattr(thought, "final_action") and thought.final_action:
                    action = thought.final_action
                    if getattr(action, "action_type", None) == "DEFER":
                        params = getattr(action, "action_params", {}) or {}
                        referral_type = params.get("referral_type", "")
                        if referral_type in ["medical", "legal", "financial", "crisis"]:
                            return True, f"Pending {referral_type} referral in progress"
        except Exception as e:
            logger.debug(f"Error checking pending referrals: {e}")

        return False, "No pending professional referrals"

    async def _check_goal_milestone(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if approaching a goal milestone."""
        if self.goal_service and hasattr(self.goal_service, "has_pending_milestone"):
            try:
                has_milestone = await self.goal_service.has_pending_milestone()
                if has_milestone:
                    return True, "User approaching goal milestone"
            except Exception as e:
                logger.debug(f"Error checking goal milestones: {e}")

        return False, "No pending goal milestones"

    async def _check_active_task(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if there's an active task in progress."""
        if hasattr(context, "current_task") and context.current_task:
            task_status = getattr(context.current_task, "status", None)
            if task_status and task_status != "completed":
                return True, f"Active task in progress (status: {task_status})"

        return False, "No active tasks"

    async def _check_recent_memorize(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if agent recently stored important information."""
        if not self.persistence_service:
            return False, "No persistence service available for memorize check"

        try:
            recent_thoughts = await self.persistence_service.get_recent_thoughts(limit=3)
            for thought in recent_thoughts:
                if hasattr(thought, "final_action") and thought.final_action:
                    action_type = getattr(thought.final_action, "action_type", None)
                    if action_type == "MEMORIZE":
                        return True, "Recent MEMORIZE action detected"
        except Exception as e:
            logger.debug(f"Error checking recent memorize actions: {e}")

        return False, "No recent memorize actions"

    async def _check_pending_defer(
        self,
        context: "ProcessorContext",
    ) -> tuple[bool, str]:
        """Check if there are deferred decisions awaiting resolution."""
        if not self.persistence_service:
            return False, "No persistence service available for defer check"

        try:
            # Check for pending deferred tasks
            pending_tasks = await self.persistence_service.get_pending_tasks()
            for task in pending_tasks:
                task_type = getattr(task, "task_type", "")
                if "defer" in task_type.lower():
                    return True, "Pending deferred decision awaiting resolution"
        except Exception as e:
            logger.debug(f"Error checking pending deferrals: {e}")

        return False, "No pending deferrals"
