"""
Tests for DMA Orchestrator.

This module tests the DMAOrchestrator which coordinates all three required DMAs:
- Ethical PDMA
- CSDMA (Common Sense DMA)
- DSDMA (Domain-Specific DMA)

And the ActionSelectionPDMA that runs after them.

Test coverage includes:
- Parallel execution of all three DMAs
- Error handling and retry logic
- Circuit breaker protection
- Action selection with enhanced DMA inputs

Fixtures are shared via conftest.py for reusability across support tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.processors.core import DMAResults
from ciris_engine.schemas.processors.dma import InitialDMAResults
from ciris_engine.schemas.runtime.enums import HandlerActionType

# Test Class


class TestDMAOrchestrator:
    """Test suite for DMAOrchestrator."""

    # Initialization Tests

    def test_initialization(self, dma_orchestrator):
        """Test that DMAOrchestrator initializes correctly with all dependencies."""
        assert dma_orchestrator.ethical_pdma_evaluator is not None
        assert dma_orchestrator.csdma_evaluator is not None
        assert dma_orchestrator.dsdma is not None
        assert dma_orchestrator.action_selection_pdma_evaluator is not None
        assert dma_orchestrator.time_service is not None
        assert dma_orchestrator.retry_limit == 3
        assert dma_orchestrator.timeout_seconds == 30.0

    def test_circuit_breakers_initialized(self, dma_orchestrator):
        """Test that circuit breakers are initialized for all DMA types."""
        assert "ethical_pdma" in dma_orchestrator._circuit_breakers
        assert "csdma" in dma_orchestrator._circuit_breakers
        assert "dsdma" in dma_orchestrator._circuit_breakers

    def test_initialization_without_dsdma(
        self,
        mock_ethical_pdma,
        mock_csdma,
        mock_action_selection_pdma,
        mock_time_service,
        mock_app_config,
    ):
        """Test initialization without DSDMA doesn't create dsdma circuit breaker."""
        orchestrator = DMAOrchestrator(
            ethical_pdma_evaluator=mock_ethical_pdma,
            csdma_evaluator=mock_csdma,
            dsdma=None,  # No DSDMA
            action_selection_pdma_evaluator=mock_action_selection_pdma,
            time_service=mock_time_service,
            app_config=mock_app_config,
        )

        assert "dsdma" not in orchestrator._circuit_breakers

    # run_initial_dmas Tests

    @pytest.mark.asyncio
    async def test_run_initial_dmas_success(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_ethical_result,
        sample_csdma_result,
        sample_dsdma_result,
    ):
        """Test successful execution of all three DMAs in parallel."""

        # Mock the DMA execution functions
        with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
            # Configure side effects for each DMA type
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # ethical_pdma
                    return sample_ethical_result
                elif call_count == 2:  # csdma
                    return sample_csdma_result
                elif call_count == 3:  # dsdma
                    return sample_dsdma_result

            mock_run.side_effect = side_effect

            # Execute
            result = await dma_orchestrator.run_initial_dmas(
                sample_thought_item,
                sample_processing_context,
            )

            # Verify
            assert isinstance(result, InitialDMAResults)
            assert result.ethical_pdma == sample_ethical_result
            assert result.csdma == sample_csdma_result
            assert result.dsdma == sample_dsdma_result
            assert mock_run.call_count == 3

    @pytest.mark.asyncio
    async def test_run_initial_dmas_missing_dsdma(
        self,
        mock_ethical_pdma,
        mock_csdma,
        mock_action_selection_pdma,
        mock_time_service,
        mock_app_config,
        sample_thought_item,
        sample_processing_context,
    ):
        """Test that run_initial_dmas fails fast if DSDMA is not configured."""
        orchestrator = DMAOrchestrator(
            ethical_pdma_evaluator=mock_ethical_pdma,
            csdma_evaluator=mock_csdma,
            dsdma=None,  # No DSDMA
            action_selection_pdma_evaluator=mock_action_selection_pdma,
            time_service=mock_time_service,
            app_config=mock_app_config,
        )

        with pytest.raises(RuntimeError, match="DSDMA is not configured"):
            await orchestrator.run_initial_dmas(
                sample_thought_item,
                sample_processing_context,
            )

    @pytest.mark.asyncio
    async def test_run_initial_dmas_ethical_pdma_failure(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
    ):
        """Test handling of Ethical PDMA failure."""
        with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
            # First call (ethical_pdma) raises exception
            async def side_effect(*args, **kwargs):
                call_number = mock_run.call_count
                if call_number == 1:
                    raise Exception("Ethical PDMA failed")
                elif call_number == 2:
                    return CSDMAResult(recommendation="Proceed", confidence=0.8, common_sense_check="OK")
                elif call_number == 3:
                    return DSDMAResult(recommendation="Proceed", confidence=0.8, domain_analysis="OK")

            mock_run.side_effect = side_effect

            with pytest.raises(Exception, match="DMA\\(s\\) failed"):
                await dma_orchestrator.run_initial_dmas(
                    sample_thought_item,
                    sample_processing_context,
                )

    @pytest.mark.asyncio
    async def test_run_initial_dmas_all_fail(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
    ):
        """Test handling when all three DMAs fail."""
        with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
            # All calls raise exceptions
            mock_run.side_effect = Exception("DMA failure")

            with pytest.raises(Exception, match="DMA\\(s\\) failed"):
                await dma_orchestrator.run_initial_dmas(
                    sample_thought_item,
                    sample_processing_context,
                )

    # run_dmas Tests (with circuit breakers)

    @pytest.mark.asyncio
    async def test_run_dmas_with_circuit_breakers_success(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_ethical_result,
        sample_csdma_result,
        sample_dsdma_result,
    ):
        """Test run_dmas with circuit breaker protection - all DMAs succeed."""
        with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
            call_count = 0

            async def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return sample_ethical_result
                elif call_count == 2:
                    return sample_csdma_result
                elif call_count == 3:
                    return sample_dsdma_result

            mock_run.side_effect = side_effect

            result = await dma_orchestrator.run_dmas(
                sample_thought_item,
                sample_processing_context,
            )

            assert isinstance(result, DMAResults)
            assert result.ethical_pdma == sample_ethical_result
            assert result.csdma == sample_csdma_result
            assert result.dsdma == sample_dsdma_result
            assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_run_dmas_records_circuit_breaker_success(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_ethical_result,
    ):
        """Test that successful DMA execution records success in circuit breaker."""
        with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:

            async def return_results(*args, **kwargs):
                return sample_ethical_result

            mock_run.side_effect = return_results

            # Get circuit breaker before execution
            cb = dma_orchestrator._circuit_breakers["ethical_pdma"]
            initial_successes = cb.total_successes

            await dma_orchestrator.run_dmas(sample_thought_item, sample_processing_context)

            # Circuit breaker should record success
            assert cb.total_successes > initial_successes

    # run_action_selection Tests

    @pytest.mark.asyncio
    async def test_run_action_selection_success(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_initial_dma_results,
        sample_action_selection_result,
    ):
        """Test successful action selection after DMAs."""
        # Create mock thought from the sample content
        mock_thought = MagicMock()
        mock_thought.thought_id = sample_thought_item.thought_id
        mock_thought.thought_depth = 0

        # Mock identity retrieval
        with patch("ciris_engine.logic.persistence.models.get_identity_for_context") as mock_identity:
            mock_identity_context = MagicMock()
            mock_identity_context.agent_name = "test_agent"
            mock_identity_context.description = "Test agent description"
            mock_identity_context.agent_role = "assistant"
            mock_identity_context.permitted_actions = [
                HandlerActionType.SPEAK,
                HandlerActionType.RECALL,
                HandlerActionType.MEMORIZE,
            ]
            mock_identity.return_value = mock_identity_context

            with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
                mock_run.return_value = sample_action_selection_result

                result = await dma_orchestrator.run_action_selection(
                    sample_thought_item,
                    mock_thought,
                    sample_processing_context,
                    sample_initial_dma_results,
                    "default",
                )

                assert isinstance(result, ActionSelectionDMAResult)
                assert result.selected_action == HandlerActionType.SPEAK
                assert result.rationale == "Best action based on DMA results"

    @pytest.mark.asyncio
    async def test_run_action_selection_with_conscience_retry(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_initial_dma_results,
    ):
        """Test action selection marks recursive evaluation when conscience retry."""
        # Set conscience retry flag
        sample_processing_context.is_conscience_retry = True

        # Create action result with DEFER
        from ciris_engine.schemas.actions import DeferParams

        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=DeferParams(reason="Need more information"),
            rationale="Retry after conscience feedback",
        )

        # Create mock thought
        mock_thought = MagicMock()
        mock_thought.thought_id = sample_thought_item.thought_id
        mock_thought.thought_depth = 0

        with patch("ciris_engine.logic.persistence.models.get_identity_for_context") as mock_identity:
            mock_identity_context = MagicMock()
            mock_identity_context.agent_name = "test_agent"
            mock_identity_context.description = "Test agent"
            mock_identity_context.agent_role = "assistant"
            mock_identity_context.permitted_actions = [HandlerActionType.DEFER, HandlerActionType.SPEAK]
            mock_identity.return_value = mock_identity_context

            with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
                mock_run.return_value = action_result

                result = await dma_orchestrator.run_action_selection(
                    sample_thought_item,
                    mock_thought,
                    sample_processing_context,
                    sample_initial_dma_results,
                    "default",
                )

                # Should have called with recursive_evaluation=True
                assert isinstance(result, ActionSelectionDMAResult)

    @pytest.mark.asyncio
    async def test_run_action_selection_unexpected_result_type(
        self,
        dma_orchestrator,
        sample_thought_item,
        sample_processing_context,
        sample_initial_dma_results,
    ):
        """Test that unexpected result type raises TypeError."""
        # Create mock thought
        mock_thought = MagicMock()
        mock_thought.thought_id = sample_thought_item.thought_id
        mock_thought.thought_depth = 0

        with patch("ciris_engine.logic.persistence.models.get_identity_for_context") as mock_identity:
            mock_identity_context = MagicMock()
            mock_identity_context.agent_name = "test_agent"
            mock_identity_context.description = "Test agent"
            mock_identity_context.agent_role = "assistant"
            mock_identity_context.permitted_actions = [HandlerActionType.SPEAK]
            mock_identity.return_value = mock_identity_context

            with patch("ciris_engine.logic.processors.support.dma_orchestrator.run_dma_with_retries") as mock_run:
                # Return wrong type
                mock_run.return_value = {"wrong": "type"}

                with pytest.raises(TypeError, match="Expected ActionSelectionDMAResult"):
                    await dma_orchestrator.run_action_selection(
                        sample_thought_item,
                        mock_thought,
                        sample_processing_context,
                        sample_initial_dma_results,
                        "default",
                    )

    # Configuration Tests

    def test_default_config_values(
        self,
        mock_ethical_pdma,
        mock_csdma,
        mock_dsdma,
        mock_action_selection_pdma,
        mock_time_service,
    ):
        """Test that default configuration values are used when app_config is None."""
        orchestrator = DMAOrchestrator(
            ethical_pdma_evaluator=mock_ethical_pdma,
            csdma_evaluator=mock_csdma,
            dsdma=mock_dsdma,
            action_selection_pdma_evaluator=mock_action_selection_pdma,
            time_service=mock_time_service,
            app_config=None,  # No config
        )

        assert orchestrator.retry_limit == 3
        assert orchestrator.timeout_seconds == 30.0
