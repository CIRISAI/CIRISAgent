"""Unit tests for recursive processing retry logic."""

from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.processors.core.thought_processor.recursive_processing import RecursiveProcessingPhase
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType


class ConcreteRecursiveProcessor(RecursiveProcessingPhase):
    """Concrete implementation for testing RecursiveProcessingPhase."""

    def __init__(self):
        """Initialize with mocked dependencies."""
        self.dma_orchestrator = Mock()
        self.dma_orchestrator.run_action_selection = AsyncMock()

    def _get_profile_name(self, thought):
        """Mock profile name getter."""
        return "test_profile"


@pytest.fixture
def processor():
    """Create a concrete processor instance."""
    return ConcreteRecursiveProcessor()


@pytest.fixture
def mock_thought():
    """Create a mock thought."""
    thought = Mock()
    thought.thought_id = "test_thought_123"
    return thought


@pytest.fixture
def mock_action_result():
    """Create a properly typed ActionSelectionDMAResult."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Test response"),
        rationale="Test rationale",
        raw_llm_response="Test LLM response",
        reasoning=None,
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


@pytest.fixture
def mock_conscience_result(mock_action_result):
    """Create a properly typed ConscienceApplicationResult."""
    override_action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["Reflect on epistemic coherence"]),
        rationale="Failed epistemic check",
        raw_llm_response=None,
        reasoning=None,
        evaluation_time_ms=50.0,
        resource_usage=None,
    )

    return ConscienceApplicationResult(
        original_action=mock_action_result,
        final_action=override_action,
        overridden=True,
        override_reason="Action failed epistemic coherence check",
        epistemic_data={"coherence_score": "0.3", "entropy_level": "0.8"},
    )


class TestPerformAspdmaWithGuidanceRetryLogic:
    """Test retry logic in _perform_aspdma_with_guidance."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, processor, mock_thought, mock_conscience_result):
        """Test successful action selection on first attempt."""
        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.return_value = expected_result

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=3,
        )

        assert result == expected_result
        # Should only call once if successful
        assert processor.dma_orchestrator.run_action_selection.call_count == 1

        # Verify guidance context in call
        call_args = processor.dma_orchestrator.run_action_selection.call_args
        processing_context = call_args.kwargs["processing_context"]
        assert "conscience_guidance" in processing_context
        assert processing_context["conscience_guidance"]["retry_attempt"] == 1
        assert processing_context["conscience_guidance"]["max_retries"] == 3
        assert processing_context["conscience_guidance"]["original_action_failed_because"] == "Action failed epistemic coherence check"

    @pytest.mark.asyncio
    async def test_success_on_second_attempt(self, processor, mock_thought, mock_conscience_result):
        """Test successful action selection on second retry."""
        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.side_effect = [
            RuntimeError("First attempt failed"),
            expected_result,
        ]

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=3,
        )

        assert result == expected_result
        assert processor.dma_orchestrator.run_action_selection.call_count == 2

        # Verify second attempt has retry history
        second_call_args = processor.dma_orchestrator.run_action_selection.call_args_list[1]
        processing_context = second_call_args.kwargs["processing_context"]
        guidance = processing_context["conscience_guidance"]

        assert guidance["retry_attempt"] == 2
        assert len(guidance["retry_history"]) == 1
        assert guidance["retry_history"][0]["attempt"] == 1
        assert guidance["retry_history"][0]["error_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_success_on_third_attempt(self, processor, mock_thought, mock_conscience_result):
        """Test successful action selection on final retry."""
        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.side_effect = [
            RuntimeError("First attempt failed"),
            ValueError("Second attempt failed"),
            expected_result,
        ]

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=3,
        )

        assert result == expected_result
        assert processor.dma_orchestrator.run_action_selection.call_count == 3

        # Verify third attempt has full retry history
        third_call_args = processor.dma_orchestrator.run_action_selection.call_args_list[2]
        processing_context = third_call_args.kwargs["processing_context"]
        guidance = processing_context["conscience_guidance"]

        assert guidance["retry_attempt"] == 3
        assert len(guidance["retry_history"]) == 2
        assert guidance["retry_history"][0]["error_type"] == "RuntimeError"
        assert guidance["retry_history"][1]["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self, processor, mock_thought, mock_conscience_result):
        """Test failure when all retry attempts are exhausted."""
        processor.dma_orchestrator.run_action_selection.side_effect = RuntimeError("Persistent failure")

        with pytest.raises(RuntimeError, match="Persistent failure"):
            await processor._perform_aspdma_with_guidance(
                thought=mock_thought,
                thought_context={},
                dma_results=Mock(),
                conscience_result=mock_conscience_result,
                max_retries=3,
            )

        # Should have tried all 3 times
        assert processor.dma_orchestrator.run_action_selection.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_max_retries(self, processor, mock_thought, mock_conscience_result):
        """Test retry logic with custom max_retries value."""
        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.side_effect = [
            RuntimeError("Attempt 1 failed"),
            RuntimeError("Attempt 2 failed"),
            RuntimeError("Attempt 3 failed"),
            RuntimeError("Attempt 4 failed"),
            expected_result,
        ]

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=5,
        )

        assert result == expected_result
        assert processor.dma_orchestrator.run_action_selection.call_count == 5

    @pytest.mark.asyncio
    async def test_dict_conscience_result(self, processor, mock_thought):
        """Test with dict-style conscience result instead of Pydantic model."""
        dict_conscience = {
            "override_reason": "Dict-based override",
            "epistemic_data": {"test": "data"},
        }

        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.return_value = expected_result

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=dict_conscience,
            max_retries=3,
        )

        assert result == expected_result

        # Verify dict data was extracted correctly
        call_args = processor.dma_orchestrator.run_action_selection.call_args
        processing_context = call_args.kwargs["processing_context"]
        guidance = processing_context["conscience_guidance"]
        assert guidance["original_action_failed_because"] == "Dict-based override"
        assert guidance["conscience_feedback"]["epistemic_data"] == {"test": "data"}

    @pytest.mark.asyncio
    async def test_pydantic_thought_context(self, processor, mock_thought, mock_conscience_result):
        """Test with Pydantic model thought context (has model_dump method)."""
        mock_context = Mock()
        mock_context.model_dump.return_value = {"existing": "context"}

        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.return_value = expected_result

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context=mock_context,
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=3,
        )

        assert result == expected_result
        mock_context.model_dump.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_history_cumulative(self, processor, mock_thought, mock_conscience_result):
        """Test that retry history accumulates across attempts."""
        expected_result = Mock()
        processor.dma_orchestrator.run_action_selection.side_effect = [
            RuntimeError("Error 1"),
            ValueError("Error 2"),
            TypeError("Error 3"),
            expected_result,
        ]

        result = await processor._perform_aspdma_with_guidance(
            thought=mock_thought,
            thought_context={},
            dma_results=Mock(),
            conscience_result=mock_conscience_result,
            max_retries=4,
        )

        assert result == expected_result

        # Check that final attempt had all 3 previous errors in history
        final_call = processor.dma_orchestrator.run_action_selection.call_args_list[3]
        guidance = final_call.kwargs["processing_context"]["conscience_guidance"]
        history = guidance["retry_history"]

        assert len(history) == 3
        assert history[0]["error"] == "Error 1"
        assert history[1]["error"] == "Error 2"
        assert history[2]["error"] == "Error 3"
        assert history[0]["attempt"] == 1
        assert history[1]["attempt"] == 2
        assert history[2]["attempt"] == 3

    @pytest.mark.asyncio
    async def test_single_retry_only(self, processor, mock_thought, mock_conscience_result):
        """Test with max_retries=1 (no actual retries, just one attempt)."""
        processor.dma_orchestrator.run_action_selection.side_effect = RuntimeError("Failed")

        with pytest.raises(RuntimeError, match="Failed"):
            await processor._perform_aspdma_with_guidance(
                thought=mock_thought,
                thought_context={},
                dma_results=Mock(),
                conscience_result=mock_conscience_result,
                max_retries=1,
            )

        # Should only try once
        assert processor.dma_orchestrator.run_action_selection.call_count == 1
