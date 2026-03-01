"""
Tests for conscience execution helper methods.

Tests coverage for the helper methods extracted to reduce cognitive complexity:
- _create_ponder_fallback_action
- _check_single_bypass_conscience
- _extract_observation_content
- _log_override_details
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestCreatePonderFallbackAction:
    """Tests for _create_ponder_fallback_action helper."""

    @pytest.fixture
    def phase(self):
        """Create a ConscienceExecutionPhase instance with mocked dependencies."""
        phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
        phase._describe_action = Mock(return_value="speak to the user")
        return phase

    def test_creates_ponder_action(self, phase):
        """Test that a PONDER action is created."""
        original_action = Mock()
        original_action.selected_action = HandlerActionType.SPEAK

        result = phase._create_ponder_fallback_action(
            action_result=original_action,
            entry_name="TestConscience",
            reason="Action failed safety check",
        )

        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)

    def test_includes_questions_in_ponder(self, phase):
        """Test that PONDER includes relevant questions."""
        original_action = Mock()
        original_action.selected_action = HandlerActionType.SPEAK

        result = phase._create_ponder_fallback_action(
            action_result=original_action,
            entry_name="TestConscience",
            reason="Safety check failed",
        )

        questions = result.action_parameters.questions
        assert len(questions) == 3
        assert "speak to the user" in questions[0]
        assert "Safety check failed" in questions[1]

    def test_handles_none_reason(self, phase):
        """Test handling of None reason."""
        original_action = Mock()
        original_action.selected_action = HandlerActionType.SPEAK

        result = phase._create_ponder_fallback_action(
            action_result=original_action,
            entry_name="TestConscience",
            reason=None,
        )

        questions = result.action_parameters.questions
        assert "bypass conscience failed" in questions[1]

    def test_rationale_includes_entry_name(self, phase):
        """Test that rationale includes the conscience entry name."""
        original_action = Mock()
        original_action.selected_action = HandlerActionType.SPEAK

        result = phase._create_ponder_fallback_action(
            action_result=original_action,
            entry_name="EthicalConscience",
            reason="Failed",
        )

        assert "EthicalConscience" in result.rationale


class TestCheckSingleBypassConscience:
    """Tests for _check_single_bypass_conscience helper."""

    @pytest.fixture
    def phase(self):
        """Create a ConscienceExecutionPhase instance."""
        return ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)

    @pytest.mark.asyncio
    async def test_calls_conscience_check(self, phase):
        """Test that conscience.check is called."""
        entry = Mock()
        entry.name = "TestConscience"
        entry.conscience = AsyncMock()
        entry.conscience.check = AsyncMock(return_value=Mock(passed=True))
        entry.circuit_breaker = None

        action = Mock()
        context = Mock()

        result = await phase._check_single_bypass_conscience(entry, action, context)

        entry.conscience.check.assert_called_once_with(action, context)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_handles_circuit_breaker_check(self, phase):
        """Test circuit breaker is checked before calling conscience."""
        entry = Mock()
        entry.name = "TestConscience"
        entry.conscience = AsyncMock()
        entry.conscience.check = AsyncMock(return_value=Mock(passed=True))
        entry.circuit_breaker = Mock()
        entry.circuit_breaker.check_and_raise = Mock()
        entry.circuit_breaker.record_success = Mock()

        action = Mock()
        context = Mock()

        result = await phase._check_single_bypass_conscience(entry, action, context)

        entry.circuit_breaker.check_and_raise.assert_called_once()
        entry.circuit_breaker.record_success.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_on_circuit_breaker_error(self, phase):
        """Test returns None when circuit breaker raises."""
        from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError

        entry = Mock()
        entry.name = "TestConscience"
        entry.conscience = AsyncMock()
        entry.circuit_breaker = Mock()
        entry.circuit_breaker.check_and_raise = Mock(side_effect=CircuitBreakerError("Circuit open"))

        action = Mock()
        context = Mock()

        result = await phase._check_single_bypass_conscience(entry, action, context)

        assert result is None

    @pytest.mark.asyncio
    async def test_records_failure_on_exception(self, phase):
        """Test circuit breaker failure is recorded on exception."""
        entry = Mock()
        entry.name = "TestConscience"
        entry.conscience = AsyncMock()
        entry.conscience.check = AsyncMock(side_effect=Exception("Check failed"))
        entry.circuit_breaker = Mock()
        entry.circuit_breaker.check_and_raise = Mock()
        entry.circuit_breaker.record_failure = Mock()

        action = Mock()
        context = Mock()

        result = await phase._check_single_bypass_conscience(entry, action, context)

        entry.circuit_breaker.record_failure.assert_called_once()
        assert result is None


class TestExtractObservationContent:
    """Tests for _extract_observation_content helper."""

    @pytest.fixture
    def phase(self):
        """Create a ConscienceExecutionPhase instance."""
        return ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)

    def test_extracts_content_when_present(self, phase):
        """Test extraction when CIRIS_OBSERVATION_UPDATED_STATUS is present."""
        result = Mock()
        result.CIRIS_OBSERVATION_UPDATED_STATUS = "New message from user"

        extracted = phase._extract_observation_content(result)

        assert extracted == "New message from user"

    def test_returns_none_when_not_present(self, phase):
        """Test returns None when attribute is not present."""
        result = Mock(spec=[])  # No attributes

        extracted = phase._extract_observation_content(result)

        assert extracted is None

    def test_returns_none_when_empty(self, phase):
        """Test returns None when attribute is empty string."""
        result = Mock()
        result.CIRIS_OBSERVATION_UPDATED_STATUS = ""

        extracted = phase._extract_observation_content(result)

        assert extracted is None

    def test_returns_none_when_none(self, phase):
        """Test returns None when attribute is None."""
        result = Mock()
        result.CIRIS_OBSERVATION_UPDATED_STATUS = None

        extracted = phase._extract_observation_content(result)

        assert extracted is None


class TestLogOverrideDetails:
    """Tests for _log_override_details helper."""

    @pytest.fixture
    def phase(self):
        """Create a ConscienceExecutionPhase instance."""
        return ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)

    def test_logs_override_details(self, phase):
        """Test that override details are logged without raising."""
        action_result = Mock()
        action_result.selected_action = HandlerActionType.SPEAK

        # Should not raise
        phase._log_override_details(
            entry_name="TestConscience",
            action_result=action_result,
            override_reason="Safety check failed",
            updated_status_detected=True,
            updated_observation_content="New message",
        )

    def test_handles_none_observation_content(self, phase):
        """Test handles None observation content gracefully."""
        action_result = Mock()
        action_result.selected_action = HandlerActionType.SPEAK

        # Should not raise
        phase._log_override_details(
            entry_name="TestConscience",
            action_result=action_result,
            override_reason="Safety check failed",
            updated_status_detected=None,
            updated_observation_content=None,
        )
