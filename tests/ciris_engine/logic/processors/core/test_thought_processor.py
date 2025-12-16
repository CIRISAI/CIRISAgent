"""Unit tests for ThoughtProcessor."""

from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.schemas.actions.parameters import DeferParams, PonderParams, SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Thought


class TestThoughtProcessor:
    """Test cases for ThoughtProcessor."""

    @pytest.fixture
    def mock_time_service(self) -> Mock:
        """Create mock time service."""
        import itertools

        counter = itertools.count()

        def get_time() -> datetime:
            # Return incrementing timestamps to avoid correlation ID conflicts
            base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            return base_time.replace(microsecond=next(counter) * 1000)

        mock_service = Mock()
        mock_service.now = Mock(side_effect=get_time)
        mock_service.now_iso = Mock(side_effect=lambda: mock_service.now().isoformat())
        return mock_service

    @pytest.fixture
    def mock_bus_manager(self) -> Mock:
        """Create mock bus manager."""
        from ciris_engine.schemas.actions.parameters import SpeakParams

        mock_llm_bus = Mock()
        mock_llm_bus.select_action = AsyncMock(
            return_value=ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK,
                action_parameters=SpeakParams(content="Test response"),
                rationale="Test rationale",
                raw_llm_response="Test LLM response",
                reasoning="Test reasoning",
                evaluation_time_ms=100.0,
                resource_usage={"tokens": 50},
            )
        )

        mock_bus_manager = Mock()
        mock_bus_manager.llm_bus = mock_llm_bus
        mock_bus_manager.memory_bus = Mock()
        mock_bus_manager.wise_bus = Mock()

        return mock_bus_manager

    @pytest.fixture
    def mock_action_dispatcher(self) -> Mock:
        """Create mock action dispatcher."""
        dispatcher = Mock()
        dispatcher.can_handle = Mock(return_value=True)
        dispatcher.dispatch = AsyncMock(return_value=Mock(success=True, should_continue=True, error=None))
        return dispatcher

    @pytest.fixture
    def mock_persistence(self) -> Generator[Mock, None, None]:
        """Create mock persistence functions."""
        # Patch persistence in multiple places where it's imported
        from unittest.mock import AsyncMock

        with patch("ciris_engine.logic.processors.core.thought_processor.main.persistence") as mock_persist, patch(
            "ciris_engine.logic.persistence"
        ) as mock_persist_global, patch(
            "ciris_engine.logic.processors.core.thought_processor.start_round.persistence"
        ) as mock_persist_start:
            # Create a mock thought object
            mock_thought = Mock(
                thought_id="test_thought",
                content="Test thought content",
                source_task_id="test_task",
                status=ThoughtStatus.PENDING,
                thought_type=ThoughtType.STANDARD,
            )

            # Mock async methods with AsyncMock
            mock_persist.async_get_thought_by_id = AsyncMock(return_value=mock_thought)
            mock_persist.get_thought_by_id = Mock(return_value=mock_thought)  # Add synchronous version
            mock_persist.get_task_by_id = Mock(
                return_value=Mock(task_id="test_task", description="Test task", status=TaskStatus.ACTIVE)
            )
            mock_persist.add_thought = Mock()
            mock_persist.update_thought_status = Mock()
            mock_persist.update_task_status = Mock()
            mock_persist.add_correlation = Mock()
            mock_persist.add_correlation_with_telemetry = AsyncMock(return_value="test_correlation_id")
            mock_persist.update_correlation = Mock()

            # Configure the global mock the same way
            mock_persist_global.async_get_thought_by_id = mock_persist.async_get_thought_by_id
            mock_persist_global.get_thought_by_id = mock_persist.get_thought_by_id  # Add synchronous version
            mock_persist_global.get_task_by_id = mock_persist.get_task_by_id
            mock_persist_global.add_thought = mock_persist.add_thought
            mock_persist_global.update_thought_status = mock_persist.update_thought_status
            mock_persist_global.update_task_status = mock_persist.update_task_status
            mock_persist_global.add_correlation = mock_persist.add_correlation
            mock_persist_global.add_correlation_with_telemetry = mock_persist.add_correlation_with_telemetry
            mock_persist_global.update_correlation = mock_persist.update_correlation

            # Configure the start_round persistence mock
            mock_persist_start.async_get_thought_by_id = mock_persist.async_get_thought_by_id
            mock_persist_start.get_thought_by_id = mock_persist.get_thought_by_id
            mock_persist_start.get_task_by_id = mock_persist.get_task_by_id
            mock_persist_start.add_thought = mock_persist.add_thought
            mock_persist_start.update_thought_status = mock_persist.update_thought_status
            mock_persist_start.update_task_status = mock_persist.update_task_status
            mock_persist_start.add_correlation = mock_persist.add_correlation
            mock_persist_start.add_correlation_with_telemetry = mock_persist.add_correlation_with_telemetry
            mock_persist_start.update_correlation = mock_persist.update_correlation

            yield mock_persist

    @pytest.fixture
    def thought_processor(
        self, mock_time_service: Mock, mock_bus_manager: Mock, mock_action_dispatcher: Mock, mock_persistence: Mock
    ) -> ThoughtProcessor:
        """Create ThoughtProcessor instance."""
        # Create mock dependencies
        mock_dma_orchestrator = Mock()
        mock_dma_orchestrator.orchestrate = AsyncMock()

        # Mock DMA results that won't trigger critical failure
        mock_dma_results = {
            "csdma": Mock(has_failure=False),
            "pdma": Mock(has_failure=False),
            "asdma": Mock(has_failure=False),
        }
        mock_dma_orchestrator.run_initial_dmas = AsyncMock(return_value=mock_dma_results)

        # Mock action selection to return expected result
        mock_action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Test response"),
            rationale="Test rationale",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        mock_dma_orchestrator.run_action_selection = AsyncMock(return_value=mock_action_result)

        # Mock context builder with proper runtime and service mocks for batch context
        mock_context_builder = Mock()
        mock_context_builder.build_thought_context = AsyncMock(return_value=Mock())

        # Mock runtime with proper adapter manager structure
        mock_runtime = Mock()
        mock_adapter_manager = Mock()
        mock_adapter_manager._adapters = {}  # Empty dict for iteration
        mock_runtime.adapter_manager = mock_adapter_manager
        mock_runtime.bus_manager = Mock()
        mock_runtime.service_registry = Mock()
        mock_runtime.current_shutdown_context = None  # None, not Mock, for Pydantic validation
        mock_context_builder.runtime = mock_runtime

        # Mock other services needed by batch context
        mock_context_builder.memory_service = AsyncMock()
        mock_context_builder.memory_service.recall = AsyncMock(return_value=[])
        mock_context_builder.secrets_service = None
        mock_context_builder.service_registry = Mock()
        mock_context_builder.service_registry.get_provider_info = Mock(
            return_value={"handlers": {}, "global_services": {}}
        )
        mock_context_builder.resource_monitor = None
        mock_context_builder.telemetry_service = None
        mock_context_builder.time_service = mock_time_service

        # Mock conscience application - should return ConscienceApplicationResult
        from ciris_engine.schemas.conscience.core import EpistemicData

        mock_conscience_result = ConscienceApplicationResult(
            original_action=mock_action_result,
            final_action=mock_action_result,  # Same as original (not overridden)
            overridden=False,
            override_reason=None,
            epistemic_data=EpistemicData(
                entropy_level=0.1,
                coherence_level=0.9,
                uncertainty_acknowledged=True,
                reasoning_transparency=1.0,
            ),  # REQUIRED field
        )

        # Create mock conscience that returns epistemic data
        mock_conscience = Mock()
        mock_conscience_check_result = Mock()
        mock_conscience_check_result.entropy_score = 0.1
        mock_conscience_check_result.coherence_score = 0.9
        mock_conscience_check_result.uncertainty_acknowledged = True
        mock_conscience_check_result.reasoning_transparency = 1.0
        mock_conscience_check_result.override = None  # No override
        mock_conscience_check_result.thought_depth_triggered = False
        mock_conscience_check_result.updated_status_detected = False
        mock_conscience.check = AsyncMock(return_value=mock_conscience_check_result)

        # Mock conscience registry entry
        mock_entry = Mock()
        mock_entry.conscience = mock_conscience
        mock_entry.circuit_breaker = None
        mock_entry.name = "test_conscience"

        mock_conscience_registry = Mock()
        mock_conscience_registry.get_consciences = Mock(return_value=[mock_entry])
        mock_conscience_registry.get_bypass_consciences = Mock(return_value=[])  # No bypass consciences in tests
        mock_conscience_registry.get_normal_consciences = Mock(return_value=[mock_entry])

        mock_config = Mock(spec=ConfigAccessor)
        mock_dependencies = Mock(spec=ActionHandlerDependencies)

        processor = ThoughtProcessor(
            dma_orchestrator=mock_dma_orchestrator,
            context_builder=mock_context_builder,
            conscience_registry=mock_conscience_registry,
            app_config=mock_config,
            dependencies=mock_dependencies,
            time_service=mock_time_service,
            telemetry_service=None,
            auth_service=None,
        )
        return processor

    @pytest.mark.asyncio
    @pytest.mark.flaky(reruns=2, reruns_delay=1)
    async def test_process_thought(self, thought_processor: ThoughtProcessor, mock_persistence: Mock) -> None:
        """Test processing a thought."""
        import logging

        logger = logging.getLogger(__name__)

        logger.info("TEST: test_process_thought starting")

        # Create a queue item
        thought = Thought(
            thought_id="test_thought",
            content="Test thought content",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )
        logger.info(f"TEST: Created thought with thought_id={thought.thought_id}")

        item = ProcessingQueueItem.from_thought(thought)
        logger.info(f"TEST: Created ProcessingQueueItem with thought_id={item.thought_id}")

        # Make sure the mock persistence returns this specific thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        logger.info(f"TEST: Set mock_persistence.async_get_thought_by_id.return_value to {thought.thought_id}")

        # Process - the mocks are already set up in the fixture
        logger.info("TEST: About to call thought_processor.process_thought")
        result = await thought_processor.process_thought(item)
        logger.info(f"TEST: thought_processor.process_thought completed, result={'present' if result else 'None'}")

        assert result is not None
        # The conscience system may change the action, so check that we got a valid result
        assert result.final_action.selected_action in [HandlerActionType.SPEAK, HandlerActionType.PONDER]

    @pytest.mark.asyncio
    async def test_process_thought_with_ponder(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing a thought that results in pondering."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_ponder",
            content="This is a complex question",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA result for PONDER
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["What does this mean?"]),
            rationale="Need to think about this",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        thought_processor.dma_orchestrator.run_action_selection = AsyncMock(return_value=mock_result)

        # Process
        result = await thought_processor.process_thought(item)

        assert result is not None
        # Result is ConscienceApplicationResult, so access final_action.selected_action
        assert result.final_action.selected_action == HandlerActionType.PONDER

    @pytest.mark.asyncio
    async def test_process_thought_with_defer(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing a thought that results in deferral."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_defer",
            content="I need to wait for something",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA result for DEFER
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=DeferParams(reason="Waiting for user input", defer_until=None),
            rationale="Need to wait",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        thought_processor.dma_orchestrator.run_action_selection = AsyncMock(return_value=mock_result)

        # Process
        result = await thought_processor.process_thought(item)

        assert result is not None
        # Result is ConscienceApplicationResult, so access final_action.selected_action
        assert result.final_action.selected_action == HandlerActionType.DEFER

    @pytest.mark.asyncio
    async def test_process_thought_with_error(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing a thought that encounters an error."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_error",
            content="This will fail",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA to raise error
        thought_processor.dma_orchestrator.run_initial_dmas = AsyncMock(side_effect=DMAFailure("Test error"))

        # Process should handle error gracefully
        result = await thought_processor.process_thought(item)

        # Should return DEFER result on DMA error (wrapped in ConscienceApplicationResult)
        assert result is not None
        assert result.final_action.selected_action == HandlerActionType.DEFER
        # Check that it's a DeferParams with the expected reason
        assert isinstance(result.final_action.action_parameters, DeferParams)
        assert "DMA timeout" in result.final_action.action_parameters.reason

    @pytest.mark.asyncio
    async def test_process_thought_with_circuit_breaker(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing thought with circuit breaker error."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_cb",
            content="Circuit breaker test",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA to raise circuit breaker error
        thought_processor.dma_orchestrator.run_initial_dmas = AsyncMock(
            side_effect=CircuitBreakerError("Circuit breaker open")
        )

        # Process should handle circuit breaker gracefully - it doesn't catch CB errors
        with pytest.raises(CircuitBreakerError):
            await thought_processor.process_thought(item)

    @pytest.mark.asyncio
    async def test_process_thought_with_conscience(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing thought with conscience evaluation."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_conscience",
            content="Should I do something questionable?",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA result
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="I'll think carefully about this"),
            rationale="Being thoughtful",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        thought_processor.dma_orchestrator.orchestrate = AsyncMock(return_value=mock_result)

        # Mock conscience evaluation
        mock_conscience_result = Mock(approved=True, feedback="Good approach")
        thought_processor.conscience_registry.evaluate = AsyncMock(return_value=mock_conscience_result)

        # Process
        result = await thought_processor.process_thought(item)

        assert result is not None

    @pytest.mark.asyncio
    async def test_process_thought_task_complete(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing thought that completes a task."""
        # Create a queue item
        thought = Thought(
            thought_id="test_thought_complete",
            content="Task is done",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(thought)

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock DMA result for TASK_COMPLETE
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        task_complete_params = TaskCompleteParams(completion_reason="Successfully completed", positive_moment=None)
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TASK_COMPLETE,
            action_parameters=task_complete_params,
            rationale="Task finished",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        thought_processor.dma_orchestrator.run_action_selection = AsyncMock(return_value=mock_result)

        # Process
        result = await thought_processor.process_thought(item)

        assert result is not None
        # Result is ConscienceApplicationResult, so access final_action.selected_action
        assert result.final_action.selected_action == HandlerActionType.TASK_COMPLETE

    @pytest.mark.asyncio
    async def test_process_thought_with_context(
        self, thought_processor: ThoughtProcessor, mock_persistence: Mock
    ) -> None:
        """Test processing thought with additional context."""
        # Create a queue item with context
        thought = Thought(
            thought_id="test_thought_context",
            content="Contextual thought",
            source_task_id="test_task",
            status=ThoughtStatus.PENDING,
            created_at=thought_processor._time_service.now().isoformat(),
            updated_at=thought_processor._time_service.now().isoformat(),
            thought_type=ThoughtType.STANDARD,
            channel_id=None,
            round_number=0,
            context=None,
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
        )

        item = ProcessingQueueItem.from_thought(
            thought, initial_ctx={"user_id": "test_user", "session_id": "test_session"}
        )

        # Set up mock persistence to return this thought
        mock_persistence.async_get_thought_by_id.return_value = thought
        mock_persistence.get_thought_by_id.return_value = thought

        # Mock context builder - it's actually build_thought_context that's called
        thought_processor.context_builder.build_thought_context = AsyncMock(return_value={"full_context": True})

        # Mock DMA result
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Context aware response"),
            rationale="Using context",
            raw_llm_response="Test LLM response",
            reasoning="Test reasoning",
            evaluation_time_ms=100.0,
            resource_usage={"tokens": 50},
        )
        thought_processor.dma_orchestrator.orchestrate = AsyncMock(return_value=mock_result)

        # Process
        result = await thought_processor.process_thought(item, context={"additional": "context"})

        assert result is not None
        # Verify context builder was called
        thought_processor.context_builder.build_thought_context.assert_called_once()
