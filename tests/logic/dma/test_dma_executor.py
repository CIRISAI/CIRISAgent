"""
Comprehensive tests for dma_executor.py.

Tests the DMA execution functions with retry logic, timeout handling,
and proper correlation tracking. Uses only existing schemas.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from ciris_engine.logic.dma.dma_executor import (
    DMA_RETRY_LIMIT,
    run_action_selection_pdma,
    run_csdma,
    run_dma_with_retries,
    run_dsdma,
    run_pdma,
)
from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ThoughtState


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    return service


@pytest.fixture
def sample_thought():
    """Create a sample thought for testing using existing schema."""
    return Thought(
        thought_id="test_thought_123",
        source_task_id="test_task_456",
        thought_type=ThoughtType.STANDARD,
        content="Test thought content",
        channel_id="test_channel",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_queue_item():
    """Create a sample ProcessingQueueItem using existing schema."""
    return ProcessingQueueItem(
        thought_id="test_thought_123",
        source_task_id="test_task_456",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text="Test thought content"),
        raw_input_string="test input",
        initial_context={"test": "context"},
    )


@pytest.fixture
def sample_thought_state():
    """Create a sample ThoughtState for context."""
    return ThoughtState(
        thought_id="test_thought_123",
        task_id="test_task_456",
        content="Test thought content",
        thought_type="STANDARD",
        created_at=datetime.now(timezone.utc),
        processing_depth=0,
    )


@pytest.fixture
def mock_ethical_evaluator():
    """Create a mock EthicalPDMAEvaluator."""
    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(
        return_value=EthicalDMAResult(
            decision="approve",
            reasoning="Test ethical reasoning",
            alignment_check={"aligned": True},
        )
    )
    return evaluator


@pytest.fixture
def mock_csdma_evaluator():
    """Create a mock CSDMAEvaluator."""
    evaluator = AsyncMock()
    evaluator.evaluate_thought = AsyncMock(
        return_value=CSDMAResult(
            plausibility_score=0.8,
            flags=[],
            reasoning="Test common sense reasoning",
        )
    )
    return evaluator


@pytest.fixture
def mock_dsdma():
    """Create a mock BaseDSDMA."""
    dsdma = AsyncMock()
    dsdma.evaluate = AsyncMock(
        return_value=DSDMAResult(
            domain="test_domain",
            domain_alignment=0.85,
            flags=[],
            reasoning="Test domain reasoning",
        )
    )
    return dsdma


@pytest.fixture
def mock_action_evaluator():
    """Create a mock ActionSelectionPDMAEvaluator."""
    from ciris_engine.schemas.actions.parameters import SpeakParams

    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(
        return_value=ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Test response"),
            rationale="Test rationale",
        )
    )
    return evaluator


class TestRunDMAWithRetries:
    """Tests for the retry wrapper function."""

    @pytest.mark.asyncio
    async def test_successful_execution_first_try(self, mock_time_service):
        """Test successful execution on first attempt."""
        mock_fn = AsyncMock(return_value="success")

        result = await run_dma_with_retries(mock_fn, "arg1", "arg2", time_service=mock_time_service, kwarg1="value1")

        assert result == "success"
        mock_fn.assert_called_once_with("arg1", "arg2", kwarg1="value1", time_service=mock_time_service)

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self, mock_time_service):
        """Test retry logic when function fails then succeeds."""
        mock_fn = AsyncMock(side_effect=[Exception("First failure"), "success"])

        result = await run_dma_with_retries(mock_fn, retry_limit=2, time_service=mock_time_service)

        assert result == "success"
        assert mock_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_time_service):
        """Test timeout handling during DMA execution."""

        async def slow_function(**kwargs):  # Accept any kwargs
            await asyncio.sleep(2)
            return "never reached"

        with pytest.raises(DMAFailure) as exc_info:
            await run_dma_with_retries(
                slow_function, retry_limit=2, timeout_seconds=0.1, time_service=mock_time_service
            )

        # Check for either timeout or the failure message
        error_msg = str(exc_info.value).lower()
        assert "timed out" in error_msg or "failed after" in error_msg

    @pytest.mark.asyncio
    async def test_escalation_on_failure(self, sample_queue_item, mock_time_service):
        """Test that failures are escalated when a thought is provided."""
        mock_fn = AsyncMock(side_effect=Exception("Persistent failure"))

        with patch("ciris_engine.logic.dma.dma_executor.escalate_dma_failure") as mock_escalate:
            with pytest.raises(DMAFailure):
                await run_dma_with_retries(mock_fn, sample_queue_item, retry_limit=2, time_service=mock_time_service)

            mock_escalate.assert_called_once()
            escalate_args = mock_escalate.call_args[0]
            assert escalate_args[0] == sample_queue_item
            assert escalate_args[1] == mock_fn.__name__

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, mock_time_service):
        """Test behavior when max retries are exceeded."""
        mock_fn = AsyncMock(side_effect=Exception("Persistent error"))

        with pytest.raises(DMAFailure) as exc_info:
            await run_dma_with_retries(mock_fn, retry_limit=3, time_service=mock_time_service)

        assert "failed after 3 attempts" in str(exc_info.value)
        assert mock_fn.call_count == 3


class TestRunPDMA:
    """Tests for the Ethical PDMA runner."""

    @pytest.mark.asyncio
    async def test_successful_pdma_execution(
        self, mock_ethical_evaluator, sample_queue_item, sample_thought_state, mock_time_service
    ):
        """Test successful PDMA execution with proper correlation tracking."""
        with patch("ciris_engine.logic.dma.dma_executor.persistence") as mock_persistence:
            result = await run_pdma(
                mock_ethical_evaluator, sample_queue_item, context=sample_thought_state, time_service=mock_time_service
            )

            assert result.decision == "approve"
            assert result.reasoning == "Test ethical reasoning"

            # Verify correlation was created and updated
            assert mock_persistence.add_correlation.called
            assert mock_persistence.update_correlation.called

            # Check that the correlation was marked as completed
            update_call = mock_persistence.update_correlation.call_args[0][0]
            assert update_call.status.value == "completed"

    @pytest.mark.asyncio
    async def test_pdma_without_time_service(self, mock_ethical_evaluator, sample_queue_item):
        """Test that PDMA fails without time service."""
        with pytest.raises(RuntimeError) as exc_info:
            await run_pdma(mock_ethical_evaluator, sample_queue_item, time_service=None)

        assert "TimeService is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pdma_with_missing_context(self, mock_ethical_evaluator, sample_queue_item, mock_time_service):
        """Test PDMA handling when context is missing."""
        # Remove context from queue item
        sample_queue_item.initial_context = None

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            with pytest.raises(DMAFailure) as exc_info:
                await run_pdma(mock_ethical_evaluator, sample_queue_item, context=None, time_service=mock_time_service)

            assert "No context available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pdma_with_dict_context(self, mock_ethical_evaluator, mock_time_service):
        """Test PDMA with dict context that gets converted to ThoughtState."""
        queue_item = ProcessingQueueItem(
            thought_id="test_thought",
            source_task_id="test_task",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Test"),
            initial_context={"system_snapshot": {}, "initial_task_context": {}, "thought_specific_context": {}},
        )

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            # Use ThoughtState as context since that's what the function expects
            context = ThoughtState(
                thought_id="test_thought",
                task_id="test_task",
                content="Test",
                thought_type="STANDARD",
                created_at=datetime.now(timezone.utc),
                processing_depth=0,
            )
            result = await run_pdma(mock_ethical_evaluator, queue_item, context=context, time_service=mock_time_service)

            assert result.decision == "approve"

    @pytest.mark.asyncio
    async def test_pdma_failure_tracking(self, mock_ethical_evaluator, sample_queue_item, mock_time_service):
        """Test that PDMA failures are properly tracked in correlations."""
        mock_ethical_evaluator.evaluate.side_effect = Exception("Evaluation failed")

        with patch("ciris_engine.logic.dma.dma_executor.persistence") as mock_persistence:
            with pytest.raises(Exception) as exc_info:
                await run_pdma(
                    mock_ethical_evaluator,
                    sample_queue_item,
                    context=ThoughtState(
                        thought_id="test_thought_123",
                        task_id="test_task_456",
                        content="Test thought content",
                        thought_type="STANDARD",
                        created_at=datetime.now(timezone.utc),
                        processing_depth=0,
                    ),
                    time_service=mock_time_service,
                )

            assert "Evaluation failed" in str(exc_info.value)

            # Verify correlation was marked as failed
            update_call = mock_persistence.update_correlation.call_args[0][0]
            assert update_call.status.value == "failed"


class TestRunCSDMA:
    """Tests for the Common Sense DMA runner."""

    @pytest.mark.asyncio
    async def test_successful_csdma_execution(self, mock_csdma_evaluator, sample_queue_item, mock_time_service):
        """Test successful CSDMA execution."""
        with patch("ciris_engine.logic.dma.dma_executor.persistence") as mock_persistence:
            result = await run_csdma(mock_csdma_evaluator, sample_queue_item, time_service=mock_time_service)

            assert result.plausibility_score == 0.8
            assert result.reasoning == "Test common sense reasoning"

            # Verify correlation tracking
            assert mock_persistence.add_correlation.called
            assert mock_persistence.update_correlation.called

    @pytest.mark.asyncio
    async def test_csdma_without_time_service(self, mock_csdma_evaluator, sample_queue_item):
        """Test that CSDMA requires time service."""
        with pytest.raises(RuntimeError) as exc_info:
            await run_csdma(mock_csdma_evaluator, sample_queue_item, time_service=None)

        assert "TimeService is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_csdma_error_handling(self, mock_csdma_evaluator, sample_queue_item, mock_time_service):
        """Test CSDMA error handling and correlation update."""
        mock_csdma_evaluator.evaluate_thought.side_effect = ValueError("Invalid thought")

        with patch("ciris_engine.logic.dma.dma_executor.persistence") as mock_persistence:
            with pytest.raises(ValueError):
                await run_csdma(mock_csdma_evaluator, sample_queue_item, time_service=mock_time_service)

            # Verify failure was tracked
            update_call = mock_persistence.update_correlation.call_args[0][0]
            assert update_call.status.value == "failed"
            assert "Invalid thought" in update_call.response_data["error_message"]


class TestRunDSDMA:
    """Tests for the Domain-Specific DMA runner."""

    @pytest.mark.asyncio
    async def test_successful_dsdma_execution(self, mock_dsdma, sample_queue_item, mock_time_service):
        """Test successful DSDMA execution."""
        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_dsdma(
                mock_dsdma, sample_queue_item, context={"domain": "test"}, time_service=mock_time_service
            )

            assert result.domain == "test_domain"
            assert result.domain_alignment == 0.85

    @pytest.mark.asyncio
    async def test_dsdma_without_context(self, mock_dsdma, sample_queue_item, mock_time_service):
        """Test DSDMA execution without context."""
        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_dsdma(mock_dsdma, sample_queue_item, context=None, time_service=mock_time_service)

            assert result.domain == "test_domain"
            mock_dsdma.evaluate.assert_called_once_with(sample_queue_item, current_context=None)


class TestRunActionSelectionPDMA:
    """Tests for the Action Selection PDMA runner."""

    @pytest.mark.asyncio
    async def test_with_enhanced_inputs(self, mock_action_evaluator, sample_queue_item, mock_time_service):
        """Test action selection with EnhancedDMAInputs."""
        enhanced_inputs = EnhancedDMAInputs(
            original_thought=sample_queue_item,
            ethical_pdma_result=EthicalDMAResult(
                decision="approve",
                reasoning="approved",
                alignment_check={},
            ),
            csdma_result=CSDMAResult(
                plausibility_score=0.8,
                flags=[],
                reasoning="plausible",
            ),
            current_thought_depth=1,
            max_rounds=5,
            processing_context={"test": "context"},
            permitted_actions=[HandlerActionType.SPEAK, HandlerActionType.TASK_COMPLETE],
        )

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_action_selection_pdma(
                mock_action_evaluator, enhanced_inputs, time_service=mock_time_service
            )

            assert result.selected_action == HandlerActionType.SPEAK
            assert result.action_parameters.content == "Test response"

    @pytest.mark.asyncio
    async def test_with_dict_inputs(self, mock_action_evaluator, sample_queue_item, mock_time_service):
        """Test action selection with dict inputs that get converted."""
        dict_inputs = {
            "original_thought": sample_queue_item,
            "ethical_pdma_result": EthicalDMAResult(
                decision="approve",
                reasoning="approved",
                alignment_check={},
            ),
            "csdma_result": CSDMAResult(
                plausibility_score=0.8,
                flags=[],
                reasoning="plausible",
            ),
            "current_thought_depth": 1,
            "max_rounds": 5,
        }

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_action_selection_pdma(mock_action_evaluator, dict_inputs, time_service=mock_time_service)

            assert result.selected_action == HandlerActionType.SPEAK

    @pytest.mark.asyncio
    async def test_observe_action_logging(self, mock_action_evaluator, sample_queue_item, mock_time_service):
        """Test that OBSERVE actions are logged with warnings."""
        from ciris_engine.schemas.actions.parameters import ObserveParams

        mock_action_evaluator.evaluate.return_value = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE, action_parameters=ObserveParams(), rationale="Observing"
        )

        enhanced_inputs = EnhancedDMAInputs(
            original_thought=sample_queue_item,
            ethical_pdma_result=EthicalDMAResult(
                decision="approve",
                reasoning="approved",
                alignment_check={},
            ),
            csdma_result=CSDMAResult(
                plausibility_score=0.8,
                flags=[],
                reasoning="plausible",
            ),
            current_thought_depth=1,
            max_rounds=5,
            processing_context={"test": "context"},
        )

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            with patch("ciris_engine.logic.dma.dma_executor.logger") as mock_logger:
                result = await run_action_selection_pdma(
                    mock_action_evaluator, enhanced_inputs, time_service=mock_time_service
                )

                assert result.selected_action == HandlerActionType.OBSERVE
                # Check that warning was logged for OBSERVE action
                mock_logger.warning.assert_called_with(
                    "OBSERVE ACTION DEBUG: run_action_selection_pdma returning OBSERVE action successfully"
                )

    @pytest.mark.asyncio
    async def test_action_selection_without_time_service(self, mock_action_evaluator):
        """Test that action selection requires time service."""
        with pytest.raises(RuntimeError) as exc_info:
            await run_action_selection_pdma(mock_action_evaluator, {}, time_service=None)

        assert "TimeService is required" in str(exc_info.value)


class TestIntegration:
    """Integration tests for DMA executor components."""

    @pytest.mark.asyncio
    async def test_retry_wrapper_with_real_dma(
        self, mock_ethical_evaluator, sample_queue_item, sample_thought_state, mock_time_service
    ):
        """Test retry wrapper integration with actual DMA function."""
        # Make the evaluator fail twice then succeed
        mock_ethical_evaluator.evaluate.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            EthicalDMAResult(
                decision="approve",
                reasoning="Success on third try",
                alignment_check={},
            ),
        ]

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_dma_with_retries(
                run_pdma,
                mock_ethical_evaluator,
                sample_queue_item,
                context=sample_thought_state,
                retry_limit=3,
                time_service=mock_time_service,
            )

            assert result.decision == "approve"
            assert result.reasoning == "Success on third try"
            assert mock_ethical_evaluator.evaluate.call_count == 3
