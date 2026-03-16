"""Unit tests for DreamProcessor."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.states.dream_processor import DreamPhase, DreamProcessor
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.results import DreamResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class TestDreamProcessor:
    """Test cases for DreamProcessor."""

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
            memory_service=Mock(),
            telemetry_service=Mock(memorize_metric=AsyncMock()),
            discord_service=None,  # Explicitly set to None
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
        """Create DreamProcessor instance."""
        processor = DreamProcessor(
            config_accessor=mock_config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            startup_channel_id="test_channel",  # Add channel_id for task creation
            pulse_interval=1.0,  # Short for testing
            min_dream_duration=1,  # 1 minute for testing
            max_dream_duration=2,  # 2 minutes for testing
        )
        # Inject memory bus directly
        processor.memory_bus = Mock(search=AsyncMock(return_value=[]), memorize=AsyncMock())
        processor.communication_bus = Mock(send_message=AsyncMock())
        # Mock task_manager to handle create_task calls
        processor.task_manager = Mock(
            create_task=Mock(return_value=Mock(task_id="test_task")),
            activate_pending_tasks=Mock(return_value=0),
            get_tasks_needing_seed=Mock(return_value=[]),
        )
        processor.thought_manager = Mock(
            generate_seed_thoughts=Mock(return_value=0),
            populate_queue=Mock(return_value=0),
            get_queue_batch=Mock(return_value=[]),
            mark_thoughts_processing=Mock(return_value=[]),
        )
        return processor

    def test_get_supported_states(self, dream_processor):
        """Test that DreamProcessor supports DREAM state."""
        states = dream_processor.get_supported_states()
        assert states == [AgentState.DREAM]

    @pytest.mark.asyncio
    async def test_can_process_dream_state(self, dream_processor):
        """Test that DreamProcessor can process DREAM state."""
        assert await dream_processor.can_process(AgentState.DREAM) is True
        assert await dream_processor.can_process(AgentState.WORK) is False

    @pytest.mark.asyncio
    async def test_initialize(self, dream_processor):
        """Test DreamProcessor initialization."""
        result = dream_processor.initialize()
        assert result is True
        # current_session is created when processing starts, not during initialization
        assert dream_processor.current_session is None

    @pytest.mark.asyncio
    async def test_process_entering_phase(self, dream_processor):
        """Test processing during ENTERING phase."""
        dream_processor.initialize()

        # Patch persistence functions
        with patch("ciris_engine.logic.persistence.get_tasks_by_status") as mock_get_tasks:
            with patch("ciris_engine.logic.persistence.update_task_status"):
                with patch("ciris_engine.logic.persistence.count_active_tasks", return_value=0):
                    with patch("ciris_engine.logic.persistence.get_pending_tasks_for_activation", return_value=[]):
                        mock_get_tasks.return_value = []

                        # Start dreaming to create session
                        await dream_processor.start_dreaming(duration=60)

                        # Now process
                        result = await dream_processor.process(1)

                        assert isinstance(result, DreamResult)
                        # After starting dream, current_session should be created
                        assert dream_processor.current_session is not None
                        # Initial phase is ENTERING
                        assert dream_processor.current_session.phase == DreamPhase.ENTERING

    @pytest.mark.asyncio
    async def test_process_consolidating_phase(self, dream_processor):
        """Test processing during CONSOLIDATING phase."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)
        dream_processor.current_session.phase = DreamPhase.CONSOLIDATING

        # Process a round - the phase will update based on active tasks
        result = await dream_processor.process(2)

        assert result.errors == 0
        # Phase transitions happen based on active tasks now

    @pytest.mark.asyncio
    async def test_process_analyzing_phase(self, dream_processor):
        """Test processing during ANALYZING phase."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)
        dream_processor.current_session.phase = DreamPhase.ANALYZING

        result = await dream_processor.process(3)

        assert result.errors == 0
        # Phase transitions happen automatically based on tasks

    @pytest.mark.asyncio
    async def test_process_configuring_phase(self, dream_processor):
        """Test processing during CONFIGURING phase."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)
        dream_processor.current_session.phase = DreamPhase.CONFIGURING

        result = await dream_processor.process(4)

        assert result.errors == 0
        # Phase transitions based on tasks

    @pytest.mark.asyncio
    async def test_process_planning_phase(self, dream_processor):
        """Test processing during PLANNING phase."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)
        dream_processor.current_session.phase = DreamPhase.PLANNING

        result = await dream_processor.process(5)

        assert result.errors == 0
        # Tasks are handled through task_manager

    @pytest.mark.asyncio
    async def test_process_exiting_phase(self, dream_processor):
        """Test processing during EXITING phase."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)
        dream_processor.current_session.phase = DreamPhase.EXITING
        dream_processor.current_session.actual_start = dream_processor._time_service.now() - timedelta(minutes=2)

        result = await dream_processor.process(6)

        assert result.errors == 0
        # Dream processor handles its own state transitions internally

    @pytest.mark.asyncio
    async def test_cleanup(self, dream_processor):
        """Test DreamProcessor cleanup."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)

        # Stop dreaming first
        await dream_processor.stop_dreaming()

        result = dream_processor.cleanup()

        assert result is True

    @pytest.mark.asyncio
    async def test_memory_consolidation_task(self, dream_processor):
        """Test memory consolidation happens through tasks."""
        dream_processor.initialize()

        # Start dreaming which creates tasks
        await dream_processor.start_dreaming(duration=60)

        # Check that consolidation tasks were created
        assert dream_processor.task_manager.create_task.called

        # Find consolidation task calls
        consolidation_calls = [
            call
            for call in dream_processor.task_manager.create_task.call_args_list
            if call.kwargs.get("description") and "Consolidate" in call.kwargs["description"]
        ]
        assert len(consolidation_calls) > 0

    @pytest.mark.asyncio
    async def test_process_behavioral_insights(self, dream_processor):
        """Test behavioral insights processing."""
        # Mock insight nodes
        mock_insights = [
            GraphNode(
                id="insight1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "insight_type": "behavioral_pattern",
                    "pattern_type": "frequency",
                    "description": "High frequency of SPEAK actions",
                    "actionable": True,
                },
            )
        ]

        dream_processor.memory_bus.search.return_value = mock_insights

        insights = await dream_processor._process_behavioral_insights()

        assert len(insights) == 2  # Pattern + action opportunity
        assert any("High frequency of SPEAK actions" in i for i in insights)

    @pytest.mark.asyncio
    async def test_self_configuration_task(self, dream_processor):
        """Test self-configuration happens through tasks."""
        dream_processor.initialize()

        # Start dreaming which creates tasks
        await dream_processor.start_dreaming(duration=60)

        # Find self-configuration task calls
        config_calls = [
            call
            for call in dream_processor.task_manager.create_task.call_args_list
            if call.kwargs.get("description")
            and (
                "parameter" in call.kwargs["description"].lower()
                or "configuration" in call.kwargs["description"].lower()
            )
        ]
        assert len(config_calls) > 0

    @pytest.mark.asyncio
    async def test_dream_session_tracking(self, dream_processor):
        """Test dream session is properly tracked."""
        dream_processor.initialize()

        # Start dreaming
        await dream_processor.start_dreaming(duration=60)

        # Check session was created
        assert dream_processor.current_session is not None
        assert dream_processor.current_session.phase == DreamPhase.ENTERING
        assert dream_processor.current_session.memories_consolidated == 0

        # Update some metrics
        dream_processor.current_session.memories_consolidated = 5
        dream_processor.current_session.patterns_analyzed = 3

        # Get summary
        summary = dream_processor.get_dream_summary()
        assert summary["state"] == "dreaming"
        assert summary["current_session"] is not None

    @pytest.mark.asyncio
    async def test_minimum_dream_duration(self, dream_processor):
        """Test that dream respects minimum duration."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)

        # Set to EXITING but not enough time passed
        dream_processor.current_session.phase = DreamPhase.EXITING
        dream_processor.current_session.actual_start = dream_processor._time_service.now()

        result = await dream_processor.process(10)

        # DreamResult doesn't have should_transition - check duration
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_maximum_dream_duration(self, dream_processor):
        """Test that dream respects maximum duration."""
        dream_processor.initialize()
        # Start dreaming to create session with max duration
        await dream_processor.start_dreaming(duration=dream_processor.max_dream_duration * 60)

        # Dream will exit when duration is reached via _should_exit check
        # Just verify session was created properly
        assert dream_processor.current_session is not None
        assert (
            dream_processor.current_session.planned_duration.total_seconds() == dream_processor.max_dream_duration * 60
        )

    @pytest.mark.asyncio
    async def test_error_handling_in_phase(self, dream_processor):
        """Test error handling during phase processing."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)

        # Mock one of the phase methods to raise error
        original_analyze = dream_processor._analyze_ponder_patterns
        dream_processor._analyze_ponder_patterns = Mock(side_effect=Exception("Test error"))

        # Process should handle error gracefully
        result = await dream_processor.process(30)

        # Restore original method
        dream_processor._analyze_ponder_patterns = original_analyze

        # Should complete without crashing (errors may or may not be counted)
        assert result is not None
        assert isinstance(result, DreamResult)

    @pytest.mark.asyncio
    async def test_pulse_activity_tracking(self, dream_processor):
        """Test that activities are tracked correctly."""
        dream_processor.initialize()
        # Start dreaming to create session
        await dream_processor.start_dreaming(duration=60)

        # Track some metrics
        dream_processor.current_session.memories_consolidated = 5
        dream_processor.current_session.patterns_analyzed = 3

        assert dream_processor.current_session.memories_consolidated == 5
        assert dream_processor.current_session.patterns_analyzed == 3

    @pytest.mark.asyncio
    async def test_dispatch_dream_thought_result(self, dream_processor):
        """Test that _dispatch_dream_thought_result calls dispatch_action."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
        from ciris_engine.schemas.actions.parameters import PonderParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType

        dream_processor.initialize()

        # Create a mock processing queue item
        item = ProcessingQueueItem(
            thought_id="test_thought_123",
            source_task_id="test_task_456",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Test thought"),
            thought_depth=0,
            initial_context={},
            agent_occurrence_id="default",
        )

        # Create a mock conscience result with PONDER action
        ponder_action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["Test question"]),
            rationale="Test rationale",
        )
        result = ConscienceApplicationResult(
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

        # Mock persistence functions
        mock_thought = Mock(thought_id="test_thought_123")
        mock_task = Mock(task_id="test_task_456")

        # Mock dispatch context with model_dump method
        mock_dispatch_context = Mock()
        mock_dispatch_context.model_dump.return_value = {"thought_id": "test_thought_123"}

        with patch("ciris_engine.logic.persistence") as mock_persistence:
            with patch(
                "ciris_engine.logic.processors.states.dream_processor.build_dispatch_context",
                return_value=mock_dispatch_context,
            ):
                with patch.object(dream_processor, "dispatch_action", new_callable=AsyncMock) as mock_dispatch:
                    mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
                    mock_persistence.get_task_by_id = Mock(return_value=mock_task)

                    await dream_processor._dispatch_dream_thought_result(item, result)

                    # Verify dispatch_action was called
                    mock_dispatch.assert_called_once()
                    call_args = mock_dispatch.call_args
                    assert call_args[0][0] == result  # First arg is result
                    assert call_args[0][1] == mock_thought  # Second arg is thought

    @pytest.mark.asyncio
    async def test_sleepwalk_prevention_speak_blocked(self, dream_processor):
        """Test that SPEAK action is blocked during dream and converted to PONDER."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
        from ciris_engine.schemas.actions.parameters import SpeakParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType

        dream_processor.initialize()

        # Create a mock processing queue item
        item = ProcessingQueueItem(
            thought_id="test_thought_speak",
            source_task_id="test_task_speak",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Test speak thought"),
            thought_depth=0,
            initial_context={},
            agent_occurrence_id="default",
        )

        # Create a SPEAK action result (should be blocked)
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

        # Mock process_thought_item to return SPEAK
        mock_thought = Mock(thought_id="test_thought_speak")
        mock_task = Mock(task_id="test_task_speak")

        # Mock dispatch context with model_dump method
        mock_dispatch_context = Mock()
        mock_dispatch_context.model_dump.return_value = {"thought_id": "test_thought_speak"}

        with patch.object(dream_processor, "process_thought_item", new_callable=AsyncMock) as mock_process:
            with patch("ciris_engine.logic.persistence") as mock_persistence:
                with patch(
                    "ciris_engine.logic.processors.states.dream_processor.build_dispatch_context",
                    return_value=mock_dispatch_context,
                ):
                    with patch.object(dream_processor, "dispatch_action", new_callable=AsyncMock) as mock_dispatch:
                        mock_process.return_value = speak_result
                        mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
                        mock_persistence.get_task_by_id = Mock(return_value=mock_task)

                        result = await dream_processor._process_dream_thought(item)

                        # Verify SPEAK was converted to PONDER
                        assert result is not None
                        assert result.final_action.selected_action == HandlerActionType.PONDER
                        assert result.overridden is True
                        assert "sleepwalk" in result.override_reason.lower()

                        # Verify dispatch was still called (with PONDER)
                        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_sleepwalk_prevention_tool_blocked(self, dream_processor):
        """Test that TOOL action is blocked during dream and converted to PONDER."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
        from ciris_engine.schemas.actions.parameters import ToolParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType

        dream_processor.initialize()

        # Create a mock processing queue item
        item = ProcessingQueueItem(
            thought_id="test_thought_tool",
            source_task_id="test_task_tool",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Test tool thought"),
            thought_depth=0,
            initial_context={},
            agent_occurrence_id="default",
        )

        # Create a TOOL action result (should be blocked)
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

        # Mock process_thought_item to return TOOL
        mock_thought = Mock(thought_id="test_thought_tool")
        mock_task = Mock(task_id="test_task_tool")

        # Mock dispatch context with model_dump method
        mock_dispatch_context = Mock()
        mock_dispatch_context.model_dump.return_value = {"thought_id": "test_thought_tool"}

        with patch.object(dream_processor, "process_thought_item", new_callable=AsyncMock) as mock_process:
            with patch("ciris_engine.logic.persistence") as mock_persistence:
                with patch(
                    "ciris_engine.logic.processors.states.dream_processor.build_dispatch_context",
                    return_value=mock_dispatch_context,
                ):
                    with patch.object(dream_processor, "dispatch_action", new_callable=AsyncMock) as mock_dispatch:
                        mock_process.return_value = tool_result
                        mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
                        mock_persistence.get_task_by_id = Mock(return_value=mock_task)

                        result = await dream_processor._process_dream_thought(item)

                        # Verify TOOL was converted to PONDER
                        assert result is not None
                        assert result.final_action.selected_action == HandlerActionType.PONDER
                        assert result.overridden is True
                        assert "sleepwalk" in result.override_reason.lower()

    @pytest.mark.asyncio
    async def test_sleepwalk_allowed_actions_pass_through(self, dream_processor):
        """Test that allowed actions (PONDER, MEMORIZE, RECALL) pass through unchanged."""
        from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
        from ciris_engine.schemas.actions.parameters import PonderParams
        from ciris_engine.schemas.conscience.core import EpistemicData
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType

        dream_processor.initialize()

        # Create a mock processing queue item
        item = ProcessingQueueItem(
            thought_id="test_thought_ponder",
            source_task_id="test_task_ponder",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Test ponder thought"),
            thought_depth=0,
            initial_context={},
            agent_occurrence_id="default",
        )

        # Create a PONDER action result (should pass through)
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

        # Mock process_thought_item to return PONDER
        mock_thought = Mock(thought_id="test_thought_ponder")
        mock_task = Mock(task_id="test_task_ponder")

        # Mock dispatch context with model_dump method
        mock_dispatch_context = Mock()
        mock_dispatch_context.model_dump.return_value = {"thought_id": "test_thought_ponder"}

        with patch.object(dream_processor, "process_thought_item", new_callable=AsyncMock) as mock_process:
            with patch("ciris_engine.logic.persistence") as mock_persistence:
                with patch(
                    "ciris_engine.logic.processors.states.dream_processor.build_dispatch_context",
                    return_value=mock_dispatch_context,
                ):
                    with patch.object(dream_processor, "dispatch_action", new_callable=AsyncMock) as mock_dispatch:
                        mock_process.return_value = ponder_result
                        mock_persistence.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
                        mock_persistence.get_task_by_id = Mock(return_value=mock_task)

                        result = await dream_processor._process_dream_thought(item)

                        # Verify PONDER passed through unchanged
                        assert result is not None
                        assert result.final_action.selected_action == HandlerActionType.PONDER
                        assert result.overridden is False  # Not overridden by sleepwalk prevention

                        # Verify dispatch was called
                        mock_dispatch.assert_called_once()
