"""Tests for ShutdownConditionEvaluator helper methods extracted for cognitive complexity reduction."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior


@pytest.fixture
def evaluator():
    """Create ShutdownConditionEvaluator without services."""
    return ShutdownConditionEvaluator()


@pytest.fixture
def evaluator_with_persistence():
    """Create ShutdownConditionEvaluator with mock persistence service."""
    persistence = MagicMock()
    persistence.get_recent_thoughts = AsyncMock(return_value=[])
    persistence.get_pending_tasks = AsyncMock(return_value=[])
    return ShutdownConditionEvaluator(persistence_service=persistence)


@pytest.fixture
def mock_context():
    """Create mock ProcessorContext."""
    context = MagicMock()
    context.current_task = None
    context.template = None
    return context


@pytest.fixture
def mock_context_with_crisis_task():
    """Create mock ProcessorContext with crisis task content."""
    context = MagicMock()
    context.current_task = MagicMock()
    context.current_task.description = "User mentioned suicide and needs help"
    context.template = None
    return context


@pytest.fixture
def mock_context_with_custom_keywords():
    """Create mock ProcessorContext with template containing custom crisis keywords."""
    context = MagicMock()
    context.current_task = MagicMock()
    context.current_task.description = "User mentioned burnout"
    context.template = MagicMock()
    context.template.guardrails_config = MagicMock()
    context.template.guardrails_config.crisis_keywords = ["burnout", "overwhelmed", "breakdown"]
    return context


@pytest.fixture
def always_consent_behaviors():
    """Create behaviors with always_consent shutdown mode."""
    return CognitiveStateBehaviors(shutdown=ShutdownBehavior(mode="always_consent"))


@pytest.fixture
def instant_shutdown_behaviors():
    """Create behaviors with instant shutdown mode."""
    return CognitiveStateBehaviors(shutdown=ShutdownBehavior(mode="instant", rationale="Ephemeral scout agent"))


@pytest.fixture
def conditional_shutdown_behaviors():
    """Create behaviors with conditional shutdown mode."""
    return CognitiveStateBehaviors(
        shutdown=ShutdownBehavior(
            mode="conditional",
            require_consent_when=["active_crisis_response"],
            instant_shutdown_otherwise=True,
        )
    )


class TestGetCrisisKeywords:
    """Tests for _get_crisis_keywords helper."""

    def test_returns_default_keywords_when_no_template(self, evaluator, mock_context):
        """Returns default keywords when context has no template."""
        keywords = evaluator._get_crisis_keywords(mock_context)
        assert "crisis" in keywords
        assert "emergency" in keywords
        assert "suicide" in keywords
        assert "self-harm" in keywords
        assert "danger" in keywords
        assert "urgent" in keywords

    def test_returns_default_keywords_when_no_guardrails(self, evaluator, mock_context):
        """Returns default keywords when template has no guardrails."""
        mock_context.template = MagicMock()
        mock_context.template.guardrails_config = None
        keywords = evaluator._get_crisis_keywords(mock_context)
        assert "crisis" in keywords

    def test_returns_custom_keywords_from_template(self, evaluator, mock_context_with_custom_keywords):
        """Returns custom keywords from template guardrails."""
        keywords = evaluator._get_crisis_keywords(mock_context_with_custom_keywords)
        assert "burnout" in keywords
        assert "overwhelmed" in keywords
        assert "breakdown" in keywords
        assert "crisis" not in keywords  # Not in custom list

    def test_returns_default_when_guardrails_has_no_keywords(self, evaluator, mock_context):
        """Returns default when guardrails exists but no crisis_keywords."""
        mock_context.template = MagicMock()
        mock_context.template.guardrails_config = MagicMock()
        mock_context.template.guardrails_config.crisis_keywords = None
        keywords = evaluator._get_crisis_keywords(mock_context)
        assert "crisis" in keywords


class TestCheckCrisisResponse:
    """Tests for _check_crisis_response method using _get_crisis_keywords helper."""

    @pytest.mark.asyncio
    async def test_no_crisis_when_no_task(self, evaluator, mock_context):
        """No crisis detected when no current task."""
        triggered, reason = await evaluator._check_crisis_response(mock_context)
        assert triggered is False
        assert "No crisis indicators" in reason

    @pytest.mark.asyncio
    async def test_crisis_detected_with_default_keywords(self, evaluator, mock_context_with_crisis_task):
        """Crisis detected when task contains default crisis keywords."""
        triggered, reason = await evaluator._check_crisis_response(mock_context_with_crisis_task)
        assert triggered is True
        assert "suicide" in reason

    @pytest.mark.asyncio
    async def test_crisis_detected_with_custom_keywords(self, evaluator, mock_context_with_custom_keywords):
        """Crisis detected when task contains custom crisis keywords."""
        triggered, reason = await evaluator._check_crisis_response(mock_context_with_custom_keywords)
        assert triggered is True
        assert "burnout" in reason

    @pytest.mark.asyncio
    async def test_no_crisis_when_no_keywords_match(self, evaluator, mock_context):
        """No crisis detected when task content doesn't match keywords."""
        mock_context.current_task = MagicMock()
        mock_context.current_task.description = "User wants to check the weather"
        triggered, reason = await evaluator._check_crisis_response(mock_context)
        assert triggered is False
        assert "No crisis indicators" in reason


class TestRequiresConsent:
    """Tests for requires_consent method with different shutdown modes."""

    @pytest.mark.asyncio
    async def test_always_consent_mode(self, evaluator, always_consent_behaviors):
        """Always consent mode always requires consent."""
        requires, reason = await evaluator.requires_consent(always_consent_behaviors)
        assert requires is True
        assert "always_consent" in reason

    @pytest.mark.asyncio
    async def test_instant_mode(self, evaluator, instant_shutdown_behaviors):
        """Instant mode never requires consent."""
        requires, reason = await evaluator.requires_consent(instant_shutdown_behaviors)
        assert requires is False
        assert "instant" in reason

    @pytest.mark.asyncio
    async def test_conditional_mode_no_context(self, evaluator, conditional_shutdown_behaviors):
        """Conditional mode defaults to consent when no context provided."""
        requires, reason = await evaluator.requires_consent(conditional_shutdown_behaviors)
        assert requires is True
        assert "requires context" in reason

    @pytest.mark.asyncio
    async def test_conditional_mode_crisis_triggered(
        self, evaluator, conditional_shutdown_behaviors, mock_context_with_crisis_task
    ):
        """Conditional mode requires consent when crisis condition triggered."""
        requires, reason = await evaluator.requires_consent(
            conditional_shutdown_behaviors, context=mock_context_with_crisis_task
        )
        assert requires is True
        assert "active_crisis_response" in reason

    @pytest.mark.asyncio
    async def test_conditional_mode_no_triggers_instant_allowed(
        self, evaluator, conditional_shutdown_behaviors, mock_context
    ):
        """Conditional mode allows instant shutdown when no conditions triggered."""
        requires, reason = await evaluator.requires_consent(conditional_shutdown_behaviors, context=mock_context)
        assert requires is False
        assert "instant shutdown permitted" in reason

    @pytest.mark.asyncio
    async def test_conditional_mode_no_triggers_consent_required(self, evaluator, mock_context):
        """Conditional mode requires consent when instant_shutdown_otherwise=False."""
        behaviors = CognitiveStateBehaviors(
            shutdown=ShutdownBehavior(
                mode="conditional",
                require_consent_when=["active_crisis_response"],
                instant_shutdown_otherwise=False,  # Require consent if no triggers
            )
        )
        requires, reason = await evaluator.requires_consent(behaviors, context=mock_context)
        assert requires is True
        assert "defaulting to consent" in reason


class TestCustomConditionHandler:
    """Tests for custom condition handler registration."""

    def test_register_custom_handler(self, evaluator):
        """Custom handlers can be registered."""
        handler = MagicMock(return_value=True)
        evaluator.register_condition_handler("custom_check", handler)
        assert "custom_check" in evaluator._custom_handlers

    @pytest.mark.asyncio
    async def test_custom_handler_evaluated(self, evaluator, mock_context):
        """Custom handlers are evaluated during condition check."""
        handler = MagicMock(return_value=True)
        evaluator.register_condition_handler("custom_check", handler)

        triggered, reason = await evaluator._evaluate_condition("custom_check", mock_context)
        assert triggered is True
        handler.assert_called_once_with(mock_context)


class TestBuiltInConditionHandlers:
    """Tests for built-in condition handlers."""

    @pytest.mark.asyncio
    async def test_active_task_no_task(self, evaluator, mock_context):
        """No active task when current_task is None."""
        triggered, reason = await evaluator._check_active_task(mock_context)
        assert triggered is False
        assert "No active tasks" in reason

    @pytest.mark.asyncio
    async def test_active_task_completed(self, evaluator, mock_context):
        """No active task when task status is completed."""
        mock_context.current_task = MagicMock()
        mock_context.current_task.status = "completed"
        triggered, reason = await evaluator._check_active_task(mock_context)
        assert triggered is False

    @pytest.mark.asyncio
    async def test_active_task_in_progress(self, evaluator, mock_context):
        """Active task detected when task status is in progress."""
        mock_context.current_task = MagicMock()
        mock_context.current_task.status = "in_progress"
        triggered, reason = await evaluator._check_active_task(mock_context)
        assert triggered is True
        assert "in_progress" in reason

    @pytest.mark.asyncio
    async def test_pending_referral_no_persistence(self, evaluator, mock_context):
        """No pending referral when no persistence service."""
        triggered, reason = await evaluator._check_pending_referral(mock_context)
        assert triggered is False
        assert "No persistence service" in reason

    @pytest.mark.asyncio
    async def test_recent_memorize_no_persistence(self, evaluator, mock_context):
        """No recent memorize when no persistence service."""
        triggered, reason = await evaluator._check_recent_memorize(mock_context)
        assert triggered is False
        assert "No persistence service" in reason

    @pytest.mark.asyncio
    async def test_pending_defer_no_persistence(self, evaluator, mock_context):
        """No pending defer when no persistence service."""
        triggered, reason = await evaluator._check_pending_defer(mock_context)
        assert triggered is False
        assert "No persistence service" in reason

    @pytest.mark.asyncio
    async def test_goal_milestone_no_service(self, evaluator, mock_context):
        """No goal milestone when no goal service."""
        triggered, reason = await evaluator._check_goal_milestone(mock_context)
        assert triggered is False
        assert "No pending goal milestones" in reason


class TestUnknownCondition:
    """Tests for handling unknown conditions."""

    @pytest.mark.asyncio
    async def test_unknown_condition_not_triggered(self, evaluator, mock_context):
        """Unknown conditions are not triggered."""
        triggered, reason = await evaluator._evaluate_condition("unknown_condition", mock_context)
        assert triggered is False
        assert "Unknown condition" in reason
