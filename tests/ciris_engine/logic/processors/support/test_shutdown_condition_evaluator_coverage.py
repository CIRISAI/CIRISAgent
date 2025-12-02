"""Additional tests for ShutdownConditionEvaluator to increase coverage.

Covers uncovered code paths:
- Persistence service handlers with data
- Goal service integration
- Error handling in handlers
- Unknown shutdown modes
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior


@pytest.fixture
def mock_context():
    """Create mock ProcessorContext."""
    context = MagicMock()
    context.current_task = None
    context.template = None
    return context


class TestPendingReferralWithService:
    """Tests for _check_pending_referral with persistence service."""

    @pytest.mark.asyncio
    async def test_pending_referral_found_medical(self, mock_context):
        """Pending referral detected when DEFER action has medical referral."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = {"referral_type": "medical"}
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is True
        assert "medical" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_found_legal(self, mock_context):
        """Pending referral detected for legal referral type."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = {"referral_type": "legal"}
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is True
        assert "legal" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_found_financial(self, mock_context):
        """Pending referral detected for financial referral type."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = {"referral_type": "financial"}
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is True
        assert "financial" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_found_crisis(self, mock_context):
        """Pending referral detected for crisis referral type."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = {"referral_type": "crisis"}
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is True
        assert "crisis" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_non_professional_type(self, mock_context):
        """No pending referral when referral_type is not professional."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = {"referral_type": "general"}  # Not a professional type
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is False
        assert "No pending professional referrals" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_non_defer_action(self, mock_context):
        """No pending referral when action is not DEFER."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "SPEAK"
        thought.final_action.action_params = {}
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_pending_referral_no_final_action(self, mock_context):
        """No pending referral when thought has no final_action."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = None
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_pending_referral_exception_handling(self, mock_context):
        """Handles exceptions gracefully during referral check."""
        persistence = MagicMock()
        persistence.get_recent_thoughts = AsyncMock(side_effect=Exception("DB Error"))

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is False
        assert "No pending professional referrals" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_null_action_params(self, mock_context):
        """Handles null action_params gracefully."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "DEFER"
        thought.final_action.action_params = None
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_referral(mock_context)

        assert triggered is False


class TestRecentMemorizeWithService:
    """Tests for _check_recent_memorize with persistence service."""

    @pytest.mark.asyncio
    async def test_recent_memorize_found(self, mock_context):
        """Recent memorize detected when MEMORIZE action found."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "MEMORIZE"
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_recent_memorize(mock_context)

        assert triggered is True
        assert "Recent MEMORIZE action detected" in reason

    @pytest.mark.asyncio
    async def test_recent_memorize_not_found(self, mock_context):
        """No recent memorize when no MEMORIZE actions."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "SPEAK"
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_recent_memorize(mock_context)

        assert triggered is False
        assert "No recent memorize actions" in reason

    @pytest.mark.asyncio
    async def test_recent_memorize_no_final_action(self, mock_context):
        """No recent memorize when thought has no final_action."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = None
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_recent_memorize(mock_context)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_recent_memorize_exception_handling(self, mock_context):
        """Handles exceptions gracefully during memorize check."""
        persistence = MagicMock()
        persistence.get_recent_thoughts = AsyncMock(side_effect=Exception("DB Error"))

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_recent_memorize(mock_context)

        assert triggered is False
        assert "No recent memorize actions" in reason


class TestPendingDeferWithService:
    """Tests for _check_pending_defer with persistence service."""

    @pytest.mark.asyncio
    async def test_pending_defer_found(self, mock_context):
        """Pending defer detected when defer task found."""
        persistence = MagicMock()
        task = MagicMock()
        task.task_type = "deferred_decision"
        persistence.get_pending_tasks = AsyncMock(return_value=[task])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_defer(mock_context)

        assert triggered is True
        assert "Pending deferred decision" in reason

    @pytest.mark.asyncio
    async def test_pending_defer_not_found(self, mock_context):
        """No pending defer when no defer tasks."""
        persistence = MagicMock()
        task = MagicMock()
        task.task_type = "regular_task"
        persistence.get_pending_tasks = AsyncMock(return_value=[task])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_defer(mock_context)

        assert triggered is False
        assert "No pending deferrals" in reason

    @pytest.mark.asyncio
    async def test_pending_defer_empty_list(self, mock_context):
        """No pending defer when empty task list."""
        persistence = MagicMock()
        persistence.get_pending_tasks = AsyncMock(return_value=[])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_defer(mock_context)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_pending_defer_exception_handling(self, mock_context):
        """Handles exceptions gracefully during defer check."""
        persistence = MagicMock()
        persistence.get_pending_tasks = AsyncMock(side_effect=Exception("DB Error"))

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        triggered, reason = await evaluator._check_pending_defer(mock_context)

        assert triggered is False
        assert "No pending deferrals" in reason


class TestGoalMilestoneWithService:
    """Tests for _check_goal_milestone with goal service."""

    @pytest.mark.asyncio
    async def test_goal_milestone_found(self, mock_context):
        """Pending milestone detected when goal_service reports it."""
        goal_service = MagicMock()
        goal_service.has_pending_milestone = AsyncMock(return_value=True)

        evaluator = ShutdownConditionEvaluator(goal_service=goal_service)
        triggered, reason = await evaluator._check_goal_milestone(mock_context)

        assert triggered is True
        assert "User approaching goal milestone" in reason

    @pytest.mark.asyncio
    async def test_goal_milestone_not_found(self, mock_context):
        """No pending milestone when goal_service reports none."""
        goal_service = MagicMock()
        goal_service.has_pending_milestone = AsyncMock(return_value=False)

        evaluator = ShutdownConditionEvaluator(goal_service=goal_service)
        triggered, reason = await evaluator._check_goal_milestone(mock_context)

        assert triggered is False
        assert "No pending goal milestones" in reason

    @pytest.mark.asyncio
    async def test_goal_milestone_exception_handling(self, mock_context):
        """Handles exceptions gracefully during milestone check."""
        goal_service = MagicMock()
        goal_service.has_pending_milestone = AsyncMock(side_effect=Exception("Service Error"))

        evaluator = ShutdownConditionEvaluator(goal_service=goal_service)
        triggered, reason = await evaluator._check_goal_milestone(mock_context)

        assert triggered is False
        assert "No pending goal milestones" in reason


class TestCustomHandlerErrors:
    """Tests for custom condition handler error handling."""

    @pytest.mark.asyncio
    async def test_custom_handler_exception(self, mock_context):
        """Custom handlers that throw exceptions default to consent."""
        evaluator = ShutdownConditionEvaluator()

        def failing_handler(ctx):
            raise ValueError("Handler failed")

        evaluator.register_condition_handler("failing_check", failing_handler)

        triggered, reason = await evaluator._evaluate_condition("failing_check", mock_context)
        assert triggered is True
        assert "Error evaluating condition" in reason


class TestBuiltInHandlerErrors:
    """Tests for built-in condition handler error handling."""

    @pytest.mark.asyncio
    async def test_builtin_handler_exception(self, mock_context):
        """Built-in handlers that throw exceptions default to consent."""
        evaluator = ShutdownConditionEvaluator()

        # Patch a built-in handler to throw
        async def failing_check(ctx):
            raise RuntimeError("Internal error")

        evaluator._check_crisis_response = failing_check

        triggered, reason = await evaluator._evaluate_condition("active_crisis_response", mock_context)
        assert triggered is True
        assert "Error evaluating condition" in reason


class TestUnknownShutdownMode:
    """Tests for unknown shutdown mode handling."""

    @pytest.mark.asyncio
    async def test_unknown_mode_defaults_to_consent(self, mock_context):
        """Unknown shutdown mode defaults to requiring consent."""
        evaluator = ShutdownConditionEvaluator()
        behaviors = CognitiveStateBehaviors()

        # Create a mock shutdown behavior with an invalid mode that bypasses Pydantic
        mock_shutdown = MagicMock(spec=ShutdownBehavior)
        mock_shutdown.mode = "unknown_mode"  # Set invalid mode directly
        behaviors.shutdown = mock_shutdown

        requires, reason = await evaluator.requires_consent(behaviors, context=mock_context)
        assert requires is True
        assert "Unknown shutdown mode" in reason


class TestConditionalShutdownEdgeCases:
    """Tests for conditional shutdown mode edge cases."""

    @pytest.mark.asyncio
    async def test_conditional_multiple_conditions_first_triggers(self, mock_context):
        """First matching condition in list triggers consent."""
        persistence = MagicMock()
        thought = MagicMock()
        thought.final_action = MagicMock()
        thought.final_action.action_type = "MEMORIZE"
        persistence.get_recent_thoughts = AsyncMock(return_value=[thought])
        persistence.get_pending_tasks = AsyncMock(return_value=[])

        evaluator = ShutdownConditionEvaluator(persistence_service=persistence)
        behaviors = CognitiveStateBehaviors(
            shutdown=ShutdownBehavior(
                mode="conditional",
                require_consent_when=["recent_memorize_action", "pending_defer_resolution"],
                instant_shutdown_otherwise=True,
            )
        )

        requires, reason = await evaluator.requires_consent(behaviors, context=mock_context)
        assert requires is True
        assert "recent_memorize_action" in reason

    @pytest.mark.asyncio
    async def test_conditional_empty_conditions_list(self, mock_context):
        """Empty conditions list allows instant shutdown."""
        evaluator = ShutdownConditionEvaluator()
        behaviors = CognitiveStateBehaviors(
            shutdown=ShutdownBehavior(
                mode="conditional",
                require_consent_when=[],  # Empty list
                instant_shutdown_otherwise=True,
            )
        )

        requires, reason = await evaluator.requires_consent(behaviors, context=mock_context)
        assert requires is False
        assert "instant shutdown permitted" in reason
