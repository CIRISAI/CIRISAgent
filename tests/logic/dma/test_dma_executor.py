"""
Integration tests for dma_executor.py.

Tests the real DMA execution flow using existing schemas.
NO NEW SCHEMAS - only what already exists in the codebase!
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the SUT
from ciris_engine.logic.dma.dma_executor import (
    DMA_RETRY_LIMIT,
    run_action_selection_pdma,
    run_csdma,
    run_dma_with_retries,
    run_dsdma,
    run_pdma,
)
from ciris_engine.logic.dma.exceptions import DMAFailure

# Import EXISTING schemas - no new ones!
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ThoughtState


@pytest.fixture
def time_service():
    """Create a real time service implementation."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    return service


@pytest.fixture
def service_registry():
    """Create a mock service registry required by DMA evaluators."""
    from ciris_engine.logic.registries.base import ServiceRegistry

    registry = Mock(spec=ServiceRegistry)
    # Add any required methods/properties that the evaluators need
    registry.get_service = Mock(return_value=None)
    registry.llm_service = AsyncMock()  # Mock LLM service
    registry.conscience_evaluator = AsyncMock()  # Mock conscience evaluator
    return registry


@pytest.fixture
def processing_queue_item():
    """Create a real ProcessingQueueItem using existing schema."""
    return ProcessingQueueItem(
        thought_id="test_thought_123",
        source_task_id="test_task_456",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text="Test thought content for DMA evaluation"),
        raw_input_string="test input",
        initial_context={"test": "context", "user": "test_user"},
    )


@pytest.fixture
def thought_state():
    """Create a real ThoughtState using existing schema."""
    return ThoughtState(
        thought_id="test_thought_123",
        task_id="test_task_456",
        content="Test thought content",
        thought_type="STANDARD",
        created_at=datetime.now(timezone.utc),
        processing_depth=0,
    )


@pytest.fixture
def ethical_evaluator(service_registry):
    """Create a real EthicalPDMAEvaluator."""
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    # Create with mock service registry
    evaluator = EthicalPDMAEvaluator(
        service_registry=service_registry,
        model_name="test-model",
        max_retries=2,
    )
    # Mock only the evaluate method to control results
    evaluator.evaluate = AsyncMock(
        return_value=EthicalDMAResult(
            decision="approve",
            reasoning="Test ethical reasoning",
            alignment_check={"aligned": True, "confidence": 0.9},
        )
    )
    return evaluator


@pytest.fixture
def csdma_evaluator(service_registry):
    """Create a real CSDMAEvaluator."""
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    evaluator = CSDMAEvaluator(
        service_registry=service_registry,
        model_name="test-model",
        max_retries=2,
    )
    # Mock only the evaluate method
    evaluator.evaluate_thought = AsyncMock(
        return_value=CSDMAResult(
            plausibility_score=0.8,
            flags=[],
            reasoning="Test common sense reasoning",
        )
    )
    return evaluator


@pytest.fixture
def action_evaluator(service_registry):
    """Create a real ActionSelectionPDMAEvaluator."""
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.actions.parameters import SpeakParams

    # ActionSelectionPDMAEvaluator takes service_registry as first argument
    evaluator = ActionSelectionPDMAEvaluator(
        service_registry=service_registry,
        model_name="test-model",
        max_retries=2,
    )
    evaluator.evaluate = AsyncMock(
        return_value=ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Test response"),
            rationale="Test rationale for action selection",
        )
    )
    return evaluator


class TestDMARetryLogic:
    """Test the retry wrapper function with real execution."""

    @pytest.mark.asyncio
    async def test_successful_execution_no_retries(self, time_service):
        """Test successful execution on first attempt."""

        async def test_func(**kwargs):
            return "success"

        result = await run_dma_with_retries(
            test_func,
            retry_limit=3,
            time_service=time_service,
        )

        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self, time_service):
        """Test retry logic with real failure then success."""
        call_count = 0

        async def test_func(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return "success after retry"

        result = await run_dma_with_retries(
            test_func,
            retry_limit=3,
            time_service=time_service,
        )

        assert result == "success after retry"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self, time_service):
        """Test timeout handling with real async delays."""

        async def slow_func(**kwargs):
            await asyncio.sleep(2)
            return "never reached"

        with pytest.raises(DMAFailure) as exc_info:
            await run_dma_with_retries(
                slow_func,
                retry_limit=2,
                timeout_seconds=0.1,
                time_service=time_service,
            )

        assert "failed after 2 attempts" in str(exc_info.value)


class TestEthicalPDMA:
    """Test the Ethical PDMA execution with real components."""

    @pytest.mark.asyncio
    async def test_run_pdma_with_context(self, ethical_evaluator, processing_queue_item, thought_state, time_service):
        """Test running PDMA with proper context."""
        # Patch only persistence to avoid DB operations
        with patch("ciris_engine.logic.dma.dma_executor.persistence") as mock_persistence:
            result = await run_pdma(
                ethical_evaluator,
                processing_queue_item,
                context=thought_state,
                time_service=time_service,
            )

            assert result.decision == "approve"
            assert result.reasoning == "Test ethical reasoning"
            assert result.alignment_check["aligned"] is True

            # Verify correlation was tracked
            assert mock_persistence.add_correlation.called
            assert mock_persistence.update_correlation.called

    @pytest.mark.asyncio
    async def test_run_pdma_without_time_service_fails(self, ethical_evaluator, processing_queue_item):
        """Test that PDMA requires time service."""
        with pytest.raises(RuntimeError) as exc_info:
            await run_pdma(
                ethical_evaluator,
                processing_queue_item,
                time_service=None,
            )

        assert "TimeService is required" in str(exc_info.value)


class TestCSDMA:
    """Test the Common Sense DMA execution."""

    @pytest.mark.asyncio
    async def test_run_csdma(self, csdma_evaluator, processing_queue_item, time_service):
        """Test running CSDMA with real components."""
        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_csdma(
                csdma_evaluator,
                processing_queue_item,
                time_service=time_service,
            )

            assert result.plausibility_score == 0.8
            assert result.flags == []
            assert result.reasoning == "Test common sense reasoning"


class TestActionSelectionPDMA:
    """Test the Action Selection PDMA execution."""

    @pytest.mark.asyncio
    async def test_run_action_selection_with_enhanced_inputs(
        self, action_evaluator, processing_queue_item, time_service
    ):
        """Test action selection with real EnhancedDMAInputs."""
        # Create real EnhancedDMAInputs using existing schema
        enhanced_inputs = EnhancedDMAInputs(
            original_thought=processing_queue_item,
            ethical_pdma_result=EthicalDMAResult(
                decision="approve",
                reasoning="Ethical approval",
                alignment_check={"aligned": True},
            ),
            csdma_result=CSDMAResult(
                plausibility_score=0.85,
                flags=[],
                reasoning="Plausible action",
            ),
            current_thought_depth=1,
            max_rounds=5,
            processing_context={"test": "context"},
            permitted_actions=[
                HandlerActionType.SPEAK,
                HandlerActionType.TASK_COMPLETE,
                HandlerActionType.DEFER,
            ],
        )

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_action_selection_pdma(
                action_evaluator,
                enhanced_inputs,
                time_service=time_service,
            )

            assert result.selected_action == HandlerActionType.SPEAK
            assert result.action_parameters.content == "Test response"
            assert result.rationale == "Test rationale for action selection"

    @pytest.mark.asyncio
    async def test_observe_action_warning(self, action_evaluator, processing_queue_item, time_service):
        """Test that OBSERVE actions generate warnings."""
        from ciris_engine.schemas.actions.parameters import ObserveParams

        # Make evaluator return OBSERVE action
        action_evaluator.evaluate.return_value = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=ObserveParams(),
            rationale="Observing",
        )

        enhanced_inputs = EnhancedDMAInputs(
            original_thought=processing_queue_item,
            ethical_pdma_result=EthicalDMAResult(
                decision="approve",
                reasoning="Approved",
                alignment_check={},
            ),
            csdma_result=CSDMAResult(
                plausibility_score=0.8,
                flags=[],
                reasoning="Plausible",
            ),
            current_thought_depth=1,
            max_rounds=5,
            processing_context={},
        )

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            with patch("ciris_engine.logic.dma.dma_executor.logger") as mock_logger:
                result = await run_action_selection_pdma(
                    action_evaluator,
                    enhanced_inputs,
                    time_service=time_service,
                )

                assert result.selected_action == HandlerActionType.OBSERVE
                # Verify warning was logged
                mock_logger.warning.assert_called_with(
                    "OBSERVE ACTION DEBUG: run_action_selection_pdma returning OBSERVE action successfully"
                )


class TestDMAIntegration:
    """Integration tests for complete DMA flow."""

    @pytest.mark.asyncio
    async def test_retry_wrapper_with_real_pdma(
        self, ethical_evaluator, processing_queue_item, thought_state, time_service
    ):
        """Test retry wrapper with actual PDMA function."""
        # Make evaluator fail once then succeed
        ethical_evaluator.evaluate.side_effect = [
            Exception("Temporary failure"),
            EthicalDMAResult(
                decision="approve",
                reasoning="Success after retry",
                alignment_check={},
            ),
        ]

        with patch("ciris_engine.logic.dma.dma_executor.persistence"):
            result = await run_dma_with_retries(
                run_pdma,
                ethical_evaluator,
                processing_queue_item,
                context=thought_state,
                retry_limit=2,
                time_service=time_service,
            )

            assert result.decision == "approve"
            assert result.reasoning == "Success after retry"
            assert ethical_evaluator.evaluate.call_count == 2
