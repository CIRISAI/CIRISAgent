"""Tests for StateManager helper methods extracted for cognitive complexity reduction."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.processors.support.state_manager import StateManager, StateTransition
from ciris_engine.schemas.config.cognitive_state_behaviors import (
    CognitiveStateBehaviors,
    DreamBehavior,
    ShutdownBehavior,
    StateBehavior,
    WakeupBehavior,
)
from ciris_engine.schemas.processors.states import AgentState


@pytest.fixture
def mock_time_service():
    """Mock time service that returns consistent UTC time."""
    time_service = MagicMock()
    time_service.now.return_value = datetime(2025, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    time_service.now_iso.return_value = "2025-11-01T12:00:00+00:00"
    return time_service


@pytest.fixture
def default_behaviors():
    """Create default CognitiveStateBehaviors (full Covenant compliance)."""
    return CognitiveStateBehaviors()


@pytest.fixture
def wakeup_disabled_behaviors():
    """Create behaviors with wakeup ceremony disabled."""
    return CognitiveStateBehaviors(wakeup=WakeupBehavior(enabled=False, rationale="Partnership model - seamless UX"))


@pytest.fixture
def play_disabled_behaviors():
    """Create behaviors with PLAY state disabled."""
    return CognitiveStateBehaviors(play=StateBehavior(enabled=False))


@pytest.fixture
def dream_disabled_behaviors():
    """Create behaviors with DREAM state disabled."""
    return CognitiveStateBehaviors(dream=DreamBehavior(enabled=False))


@pytest.fixture
def solitude_disabled_behaviors():
    """Create behaviors with SOLITUDE state disabled."""
    return CognitiveStateBehaviors(solitude=StateBehavior(enabled=False))


class TestIsOptionalStateEnabled:
    """Tests for _is_optional_state_enabled helper."""

    def test_work_state_always_enabled(self, mock_time_service, default_behaviors):
        """WORK state is always enabled regardless of config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.WORK, default_behaviors)
        assert result is True

    def test_wakeup_state_always_enabled(self, mock_time_service, default_behaviors):
        """WAKEUP state returns True (not in optional state map)."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.WAKEUP, default_behaviors)
        assert result is True

    def test_shutdown_state_always_enabled(self, mock_time_service, default_behaviors):
        """SHUTDOWN state returns True (not in optional state map)."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.SHUTDOWN, default_behaviors)
        assert result is True

    def test_play_state_enabled_by_default(self, mock_time_service, default_behaviors):
        """PLAY state is enabled with default behaviors."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.PLAY, default_behaviors)
        assert result is True

    def test_play_state_disabled(self, mock_time_service, play_disabled_behaviors):
        """PLAY state respects disabled config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=play_disabled_behaviors)
        result = manager._is_optional_state_enabled(AgentState.PLAY, play_disabled_behaviors)
        assert result is False

    def test_dream_state_enabled_by_default(self, mock_time_service, default_behaviors):
        """DREAM state is enabled with default behaviors."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.DREAM, default_behaviors)
        assert result is True

    def test_dream_state_disabled(self, mock_time_service, dream_disabled_behaviors):
        """DREAM state respects disabled config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=dream_disabled_behaviors)
        result = manager._is_optional_state_enabled(AgentState.DREAM, dream_disabled_behaviors)
        assert result is False

    def test_solitude_state_enabled_by_default(self, mock_time_service, default_behaviors):
        """SOLITUDE state is enabled with default behaviors."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._is_optional_state_enabled(AgentState.SOLITUDE, default_behaviors)
        assert result is True

    def test_solitude_state_disabled(self, mock_time_service, solitude_disabled_behaviors):
        """SOLITUDE state respects disabled config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=solitude_disabled_behaviors)
        result = manager._is_optional_state_enabled(AgentState.SOLITUDE, solitude_disabled_behaviors)
        assert result is False


class TestCheckShutdownWakeupTransition:
    """Tests for _check_shutdown_wakeup_transition helper."""

    def test_non_shutdown_source_returns_none(self, mock_time_service, default_behaviors):
        """Non-SHUTDOWN source state returns None (not handled by this method)."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._check_shutdown_wakeup_transition(AgentState.WORK, AgentState.WAKEUP, default_behaviors)
        assert result is None

    def test_shutdown_to_wakeup_enabled(self, mock_time_service, default_behaviors):
        """SHUTDOWN -> WAKEUP allowed when wakeup.enabled=True."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._check_shutdown_wakeup_transition(AgentState.SHUTDOWN, AgentState.WAKEUP, default_behaviors)
        assert result is True

    def test_shutdown_to_wakeup_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """SHUTDOWN -> WAKEUP blocked when wakeup.enabled=False."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        result = manager._check_shutdown_wakeup_transition(
            AgentState.SHUTDOWN, AgentState.WAKEUP, wakeup_disabled_behaviors
        )
        assert result is False

    def test_shutdown_to_work_when_wakeup_enabled(self, mock_time_service, default_behaviors):
        """SHUTDOWN -> WORK blocked when wakeup.enabled=True."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._check_shutdown_wakeup_transition(AgentState.SHUTDOWN, AgentState.WORK, default_behaviors)
        assert result is False

    def test_shutdown_to_work_when_wakeup_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """SHUTDOWN -> WORK allowed when wakeup.enabled=False (direct to work)."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        result = manager._check_shutdown_wakeup_transition(
            AgentState.SHUTDOWN, AgentState.WORK, wakeup_disabled_behaviors
        )
        assert result is True

    def test_shutdown_to_play_returns_none(self, mock_time_service, default_behaviors):
        """SHUTDOWN -> PLAY returns None (not handled by this method)."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        result = manager._check_shutdown_wakeup_transition(AgentState.SHUTDOWN, AgentState.PLAY, default_behaviors)
        assert result is None


class TestIsTransitionAllowed:
    """Tests for _is_transition_allowed method using helpers."""

    def test_shutdown_to_wakeup_with_wakeup_enabled(self, mock_time_service, default_behaviors):
        """SHUTDOWN -> WAKEUP allowed with default config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        transition = StateTransition(AgentState.SHUTDOWN, AgentState.WAKEUP)
        result = manager._is_transition_allowed(transition, default_behaviors)
        assert result is True

    def test_shutdown_to_wakeup_with_wakeup_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """SHUTDOWN -> WAKEUP blocked when wakeup disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        transition = StateTransition(AgentState.SHUTDOWN, AgentState.WAKEUP)
        result = manager._is_transition_allowed(transition, wakeup_disabled_behaviors)
        assert result is False

    def test_shutdown_to_work_with_wakeup_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """SHUTDOWN -> WORK allowed when wakeup disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        transition = StateTransition(AgentState.SHUTDOWN, AgentState.WORK)
        result = manager._is_transition_allowed(transition, wakeup_disabled_behaviors)
        assert result is True

    def test_work_to_play_with_play_enabled(self, mock_time_service, default_behaviors):
        """WORK -> PLAY allowed with default config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.PLAY)
        result = manager._is_transition_allowed(transition, default_behaviors)
        assert result is True

    def test_work_to_play_with_play_disabled(self, mock_time_service, play_disabled_behaviors):
        """WORK -> PLAY blocked when play disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=play_disabled_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.PLAY)
        result = manager._is_transition_allowed(transition, play_disabled_behaviors)
        assert result is False

    def test_work_to_dream_with_dream_enabled(self, mock_time_service, default_behaviors):
        """WORK -> DREAM allowed with default config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.DREAM)
        result = manager._is_transition_allowed(transition, default_behaviors)
        assert result is True

    def test_work_to_dream_with_dream_disabled(self, mock_time_service, dream_disabled_behaviors):
        """WORK -> DREAM blocked when dream disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=dream_disabled_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.DREAM)
        result = manager._is_transition_allowed(transition, dream_disabled_behaviors)
        assert result is False

    def test_work_to_solitude_with_solitude_enabled(self, mock_time_service, default_behaviors):
        """WORK -> SOLITUDE allowed with default config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.SOLITUDE)
        result = manager._is_transition_allowed(transition, default_behaviors)
        assert result is True

    def test_work_to_solitude_with_solitude_disabled(self, mock_time_service, solitude_disabled_behaviors):
        """WORK -> SOLITUDE blocked when solitude disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=solitude_disabled_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.SOLITUDE)
        result = manager._is_transition_allowed(transition, solitude_disabled_behaviors)
        assert result is False

    def test_work_to_shutdown_always_allowed(self, mock_time_service, default_behaviors):
        """WORK -> SHUTDOWN always allowed."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        transition = StateTransition(AgentState.WORK, AgentState.SHUTDOWN)
        result = manager._is_transition_allowed(transition, default_behaviors)
        assert result is True


class TestStartupTargetState:
    """Tests for startup_target_state property."""

    def test_startup_target_wakeup_when_enabled(self, mock_time_service, default_behaviors):
        """Startup target is WAKEUP when wakeup ceremony enabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        assert manager.startup_target_state == AgentState.WAKEUP

    def test_startup_target_work_when_wakeup_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """Startup target is WORK when wakeup ceremony disabled."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        assert manager.startup_target_state == AgentState.WORK


class TestWakeupBypassed:
    """Tests for wakeup_bypassed property."""

    def test_wakeup_not_bypassed_by_default(self, mock_time_service, default_behaviors):
        """Wakeup is not bypassed with default config."""
        manager = StateManager(mock_time_service, cognitive_behaviors=default_behaviors)
        assert manager.wakeup_bypassed is False

    def test_wakeup_bypassed_when_disabled(self, mock_time_service, wakeup_disabled_behaviors):
        """Wakeup is bypassed when wakeup.enabled=False."""
        manager = StateManager(mock_time_service, cognitive_behaviors=wakeup_disabled_behaviors)
        assert manager.wakeup_bypassed is True
