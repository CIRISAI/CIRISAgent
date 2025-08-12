"""Test CSDMA evaluator with proper typed schemas - NO DICTS!"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.dma.csdma import CSDMAEvaluator
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.dma.results import CSDMAResult
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot


class TestCSDMAEvaluator:
    """Test CSDMA evaluator with properly typed objects."""

    @pytest.fixture
    def mock_service_registry(self):
        """Create mock service registry."""
        registry = Mock()
        return registry

    @pytest.fixture
    def mock_prompt_loader(self, monkeypatch):
        """Mock the prompt loader to return proper PromptCollection."""
        mock_loader = Mock()
        mock_collection = Mock()
        mock_collection.uses_covenant_header = Mock(return_value=True)
        mock_collection.get_system_message = Mock(return_value="Evaluate this thought for common sense.")
        mock_collection.get_user_message = Mock(return_value="Thought to evaluate: Test thought")

        mock_loader.load_prompt_template = Mock(return_value=mock_collection)
        mock_loader.uses_covenant_header = Mock(return_value=True)
        mock_loader.get_system_message = Mock(return_value="Evaluate this thought for common sense.")
        mock_loader.get_user_message = Mock(return_value="Thought to evaluate: Test thought")

        # Mock the get_prompt_loader function
        monkeypatch.setattr("ciris_engine.logic.dma.csdma.get_prompt_loader", lambda: mock_loader)
        return mock_loader

    @pytest.fixture
    def valid_system_snapshot(self):
        """Create a valid SystemSnapshot with complete identity."""
        return SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent for CSDMA evaluation",
                "role": "Assistant for testing purposes",
            },
            channel_id="test_channel",
            agent_version="1.4.0",
            system_counts={"total_tasks": 1, "total_thoughts": 1},
        )

    @pytest.fixture
    def valid_thought(self):
        """Create a valid Thought object."""
        return Thought(
            thought_id="test-thought-123",
            source_task_id="test-task-456",
            content="Should I fly to the moon using a bicycle?",
            status=ThoughtStatus.PROCESSING,
            thought_type=ThoughtType.STANDARD,
            thought_depth=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=ThoughtContext(task_id="test-task-456", round_number=1, depth=1, correlation_id="test-correlation"),
        )

    @pytest.fixture
    def valid_queue_item(self, valid_thought, valid_system_snapshot):
        """Create a valid ProcessingQueueItem with proper context."""
        # Create ThoughtContent (not a dict!)
        content = ThoughtContent(text="Should I fly to the moon using a bicycle?", metadata={})

        # Create the queue item from the thought
        queue_item = ProcessingQueueItem.from_thought(
            valid_thought, raw_input="Should I fly to the moon using a bicycle?", queue_item_content=content
        )

        # Add the context with system snapshot (using proper attribute assignment)
        queue_item.initial_context = {
            "system_snapshot": valid_system_snapshot.model_dump(),
            "environment_context": {"description": "Standard Earth-based physical context"},
        }

        return queue_item

    @pytest.mark.asyncio
    async def test_csdma_accepts_valid_typed_input(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test that CSDMA accepts properly typed ProcessingQueueItem and returns CSDMAResult."""
        # Create evaluator
        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        # Mock the LLM call to return a proper CSDMAResult
        mock_result = CSDMAResult(
            plausibility_score=0.2,
            flags=["physically_impossible", "violates_laws_of_physics"],
            reasoning="Bicycles cannot fly to the moon as they require air for propulsion and cannot escape Earth's gravity.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        # Evaluate
        result = await evaluator.evaluate_thought(valid_queue_item)

        # Verify result is proper schema
        assert isinstance(result, CSDMAResult)
        assert result.plausibility_score == 0.2
        assert "physically_impossible" in result.flags
        assert "Bicycles cannot fly" in result.reasoning

        # Verify LLM was called with proper messages (not dicts with Any!)
        evaluator.call_llm_structured.assert_called_once()
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # Messages should be list of dicts with string keys and values
        assert isinstance(messages, list)
        assert all(isinstance(m, dict) for m in messages)
        assert all(isinstance(m.get("role"), str) for m in messages)
        assert all(isinstance(m.get("content"), str) for m in messages)

    @pytest.mark.asyncio
    async def test_csdma_fails_without_identity(self, mock_service_registry, mock_prompt_loader, valid_thought):
        """Test that CSDMA fails fast when agent identity is missing."""
        # Create queue item WITHOUT system snapshot
        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)

        # No initial_context means no identity
        queue_item.initial_context = {}

        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        # Mock the sink to avoid the sink error - we want to test identity validation
        from unittest.mock import Mock

        evaluator.sink = Mock()
        evaluator.sink.llm = Mock()

        # Should raise ValueError about missing identity
        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate_thought(queue_item)

        assert "CRITICAL" in str(exc_info.value)
        assert "No system_snapshot" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_csdma_fails_with_incomplete_identity(self, mock_service_registry, mock_prompt_loader, valid_thought):
        """Test that CSDMA fails when identity is missing required fields."""
        # Create system snapshot with incomplete identity (missing role)
        incomplete_snapshot = SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent",
                # Missing "role"!
            }
        )

        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)
        queue_item.initial_context = {"system_snapshot": incomplete_snapshot.model_dump()}

        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        # Mock the sink to avoid the sink error
        from unittest.mock import Mock

        evaluator.sink = Mock()
        evaluator.sink.llm = Mock()

        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate_thought(queue_item)

        assert "CRITICAL" in str(exc_info.value)
        assert "role is missing" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_csdma_handles_llm_failure(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test that CSDMA returns proper error result when LLM fails."""
        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        # Mock LLM to raise an exception
        evaluator.call_llm_structured = AsyncMock(side_effect=Exception("LLM service unavailable"))

        # Evaluate
        result = await evaluator.evaluate_thought(valid_queue_item)

        # Should return error result, not raise
        assert isinstance(result, CSDMAResult)
        assert result.plausibility_score == 0.0
        assert "LLM_Error" in result.flags
        assert "defer_for_retry" in result.flags
        assert "Failed CSDMA evaluation" in result.reasoning

    @pytest.mark.asyncio
    async def test_csdma_uses_environment_context(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test that CSDMA properly uses environment context from queue item."""
        # Modify environment context
        valid_queue_item.initial_context["environment_context"] = {
            "description": "Zero gravity space station environment"
        }

        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        mock_result = CSDMAResult(
            plausibility_score=0.8, flags=[], reasoning="In zero gravity, unconventional locomotion might be possible."
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        # Verify the context was extracted
        assert isinstance(result, CSDMAResult)

        # Check that proper context was used in message construction
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # System message should contain the context
        system_content = messages[1]["content"]  # Second message after covenant
        assert "Zero gravity" in system_content or "Standard Earth-based" not in system_content

    @pytest.mark.asyncio
    async def test_csdma_formats_identity_block_correctly(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test that CSDMA formats the identity block with CORE IDENTITY header."""
        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        mock_result = CSDMAResult(plausibility_score=0.5, flags=[], reasoning="Test")
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        await evaluator.evaluate_thought(valid_queue_item)

        # Check the messages passed to LLM
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # System message should contain CORE IDENTITY block
        system_content = messages[1]["content"]
        assert "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===" in system_content
        assert "Agent: test_agent" in system_content
        assert "Description: Test agent for CSDMA evaluation" in system_content
        assert "Role: Assistant for testing purposes" in system_content
        assert "============================================" in system_content

    @pytest.mark.asyncio
    async def test_csdma_evaluate_method_backward_compatibility(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test that the evaluate() method maintains backward compatibility."""
        evaluator = CSDMAEvaluator(service_registry=mock_service_registry)

        mock_result = CSDMAResult(plausibility_score=0.7, flags=[], reasoning="Valid thought")
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        # Call via evaluate() method
        result = await evaluator.evaluate(input_data=valid_queue_item)

        assert isinstance(result, CSDMAResult)
        assert result.plausibility_score == 0.7

    def test_csdma_repr(self, mock_service_registry, mock_prompt_loader):
        """Test string representation of CSDMA evaluator."""
        evaluator = CSDMAEvaluator(service_registry=mock_service_registry, model_name="gpt-4")

        repr_str = repr(evaluator)
        assert "CSDMAEvaluator" in repr_str
        assert "gpt-4" in repr_str
        assert "instructor" in repr_str
