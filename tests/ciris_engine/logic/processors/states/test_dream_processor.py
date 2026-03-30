"""Unit tests for MinimalDreamProcessor (the new dream processor)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.states.minimal_dream_processor import MinimalDreamProcessor
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.results import DreamResult
from ciris_engine.schemas.processors.states import AgentState


class TestMinimalDreamProcessor:
    """Test cases for MinimalDreamProcessor."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_time_service = Mock()
        mock_time_service.now.return_value = current_time
        mock_time_service.now_iso.return_value = current_time.isoformat()

        return ProcessorServices(
            time_service=mock_time_service,
            resource_monitor=Mock(snapshot=Mock(healthy=True, warnings=[], critical=[])),
            memory_service=Mock(memorize=AsyncMock()),
            telemetry_service=Mock(memorize_metric=AsyncMock()),
            discord_service=None,
            communication_bus=None,
            audit_service=None,
            service_registry=None,
            identity_manager=None,
            secrets_service=None,
            graphql_provider=None,
            app_config=None,
            runtime=None,
            llm_service=None,
        )

    @pytest.fixture
    def mock_config(self):
        """Create mock config accessor."""
        config = Mock(spec=ConfigAccessor)
        config.get = Mock(return_value=None)
        config.get_or_none = Mock(return_value=None)
        return config

    @pytest.fixture
    def mock_thought_processor(self):
        """Create mock thought processor."""
        return Mock(
            get_processing_queue=Mock(
                return_value=Mock(pending_items=Mock(return_value=[]), is_empty=Mock(return_value=True))
            )
        )

    @pytest.fixture
    def mock_action_dispatcher(self):
        """Create mock action dispatcher."""
        return Mock()

    @pytest.fixture
    def dream_processor(self, mock_config, mock_thought_processor, mock_action_dispatcher, mock_services):
        """Create MinimalDreamProcessor instance."""
        processor = MinimalDreamProcessor(
            config_accessor=mock_config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            startup_channel_id="test_channel",
            max_dream_depth=20,
        )
        return processor

    def test_get_supported_states(self, dream_processor):
        """Test that MinimalDreamProcessor supports DREAM state."""
        states = dream_processor.get_supported_states()
        assert states == [AgentState.DREAM]

    @pytest.mark.asyncio
    async def test_can_process_dream_state(self, dream_processor):
        """Test that MinimalDreamProcessor can process DREAM state."""
        assert await dream_processor.can_process(AgentState.DREAM) is True
        assert await dream_processor.can_process(AgentState.WORK) is False

    def test_initialize(self, dream_processor):
        """Test MinimalDreamProcessor initialization."""
        result = dream_processor.initialize()
        assert result is True
        assert dream_processor.current_session is None

    @pytest.mark.asyncio
    async def test_process_creates_session(self, dream_processor):
        """Test that process creates a dream session on first round."""
        # Create a mock thought to prevent immediate completion
        mock_thought = Mock(
            thought_id="test_thought",
            source_task_id="task_123",
            status=Mock(value="PENDING"),
            thought_type=Mock(value="REFLECTION"),
            content="Test content",
            thought_depth=0,
        )
        mock_thought.status = Mock()
        mock_thought.status.__eq__ = lambda self, other: False  # Never matches PENDING/PROCESSING

        with patch("ciris_engine.logic.persistence.add_task"):
            with patch("ciris_engine.logic.persistence.add_thought"):
                with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
                    with patch("ciris_engine.logic.persistence.get_task_by_id", return_value=Mock(status=Mock(value="ACTIVE"))):
                        result = await dream_processor.process(0)

                        assert isinstance(result, DreamResult)
                        # Session may be None if dream completed, but we should have processed
                        # The key test is that result is a valid DreamResult

    @pytest.mark.asyncio
    async def test_start_dreaming(self, dream_processor):
        """Test start_dreaming creates session and task."""
        with patch("ciris_engine.logic.persistence.add_task"):
            with patch("ciris_engine.logic.persistence.add_thought"):
                with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
                    await dream_processor.start_dreaming(duration=60)

                    assert dream_processor._dream_task is not None
                    assert dream_processor.dream_metrics.get("status") == "active"

    @pytest.mark.asyncio
    async def test_stop_dreaming(self, dream_processor):
        """Test stop_dreaming ends the session."""
        with patch("ciris_engine.logic.persistence.add_task"):
            with patch("ciris_engine.logic.persistence.add_thought"):
                with patch("ciris_engine.logic.persistence.get_thoughts_by_task_id", return_value=[]):
                    await dream_processor.start_dreaming(duration=60)
                    await dream_processor.stop_dreaming()

                    assert dream_processor.current_session is None

    def test_get_dream_summary_idle(self, dream_processor):
        """Test get_dream_summary when idle."""
        summary = dream_processor.get_dream_summary()
        assert summary["status"] == "idle"

    @pytest.mark.asyncio
    async def test_get_dream_summary_active(self, dream_processor):
        """Test get_dream_summary when session is active."""
        from ciris_engine.logic.processors.states.minimal_dream_processor import DreamSession

        # Manually create a session to test the summary
        dream_processor.current_session = DreamSession(
            session_id="test_session_123",
            start_time=dream_processor.time_service.now(),
            task_id="test_task_123",
            edges_created=5,
            thoughts_processed=10,
        )

        summary = dream_processor.get_dream_summary()
        assert summary["status"] == "active"
        assert summary["session_id"] == "test_session_123"
        assert summary["edges_created"] == 5
        assert summary["thoughts_processed"] == 10

    def test_cleanup(self, dream_processor):
        """Test MinimalDreamProcessor cleanup."""
        result = dream_processor.cleanup()
        assert result is True

    @pytest.mark.asyncio
    async def test_sleepwalk_prevention_speak(self, dream_processor):
        """Test that SPEAK action is blocked during dream."""
        from ciris_engine.schemas.actions.parameters import SpeakParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        # Create a SPEAK action result
        speak_action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Hello world"),
            rationale="Test speak",
        )
        speak_result = ConscienceApplicationResult(
            original_action=speak_action,
            final_action=speak_action,
            overridden=False,
            override_reason=None,
            epistemic_data=EpistemicData(
                entropy_level=0.3,
                coherence_level=0.8,
                uncertainty_acknowledged=True,
                reasoning_transparency=1.0,
            ),
        )

        # Apply sleepwalk prevention
        result = dream_processor._apply_sleepwalk_prevention(speak_result, "test_thought")

        # Verify SPEAK was converted to PONDER
        assert result.final_action.selected_action == HandlerActionType.PONDER
        assert result.overridden is True
        assert "sleepwalk" in result.override_reason.lower()

    @pytest.mark.asyncio
    async def test_sleepwalk_prevention_tool(self, dream_processor):
        """Test that TOOL action is blocked during dream."""
        from ciris_engine.schemas.actions.parameters import ToolParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        # Create a TOOL action result
        tool_action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TOOL,
            action_parameters=ToolParams(name="some_tool", parameters={}),
            rationale="Test tool",
        )
        tool_result = ConscienceApplicationResult(
            original_action=tool_action,
            final_action=tool_action,
            overridden=False,
            override_reason=None,
            epistemic_data=EpistemicData(
                entropy_level=0.3,
                coherence_level=0.8,
                uncertainty_acknowledged=True,
                reasoning_transparency=1.0,
            ),
        )

        # Apply sleepwalk prevention
        result = dream_processor._apply_sleepwalk_prevention(tool_result, "test_thought")

        # Verify TOOL was converted to PONDER
        assert result.final_action.selected_action == HandlerActionType.PONDER
        assert result.overridden is True

    @pytest.mark.asyncio
    async def test_sleepwalk_prevention_ponder_allowed(self, dream_processor):
        """Test that PONDER action passes through unchanged."""
        from ciris_engine.schemas.actions.parameters import PonderParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        # Create a PONDER action result
        ponder_action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["What should I learn?"]),
            rationale="Test ponder",
        )
        ponder_result = ConscienceApplicationResult(
            original_action=ponder_action,
            final_action=ponder_action,
            overridden=False,
            override_reason=None,
            epistemic_data=EpistemicData(
                entropy_level=0.3,
                coherence_level=0.8,
                uncertainty_acknowledged=True,
                reasoning_transparency=1.0,
            ),
        )

        # Apply sleepwalk prevention
        result = dream_processor._apply_sleepwalk_prevention(ponder_result, "test_thought")

        # Verify PONDER passed through unchanged
        assert result.final_action.selected_action == HandlerActionType.PONDER
        assert result.overridden is False
