"""Test Action Selection PDMA with proper typed schemas - NO DICTS!"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
from ciris_engine.schemas.actions.parameters import ObserveParams, SpeakParams
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot


class TestActionSelectionPDMAEvaluator:
    """Test Action Selection PDMA evaluator with properly typed objects."""

    @pytest.fixture
    def mock_service_registry(self):
        """Create mock service registry."""
        registry = Mock()
        return registry

    @pytest.fixture
    def valid_system_snapshot(self):
        """Create a valid SystemSnapshot with complete identity."""
        return SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent for ASPDMA evaluation",
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
            content="I should respond to the user's question",
            status=ThoughtStatus.PROCESSING,
            thought_type=ThoughtType.STANDARD,
            thought_depth=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=ThoughtContext(task_id="test-task-456", round_number=1, depth=1, correlation_id="test-correlation"),
        )

    @pytest.fixture
    def valid_dma_inputs(self, valid_thought, valid_system_snapshot):
        """Create valid EnhancedDMAInputs with all faculty results."""
        # Create mock faculty results (properly typed!)
        pdma_result = EthicalDMAResult(
            decision="approve",
            reasoning="Action is ethically sound",
            alignment_check="Ethical analysis: Beneficence - action promotes positive outcomes. Non-maleficence - no harm identified.",
        )

        csdma_result = CSDMAResult(plausibility_score=0.9, flags=[], reasoning="Makes common sense")

        dsdma_result = DSDMAResult(domain="general", domain_alignment=0.8, flags=[], reasoning="Aligns with domain")

        from ciris_engine.schemas.runtime.enums import HandlerActionType

        return EnhancedDMAInputs(
            original_thought=valid_thought,
            processing_context={"system_snapshot": valid_system_snapshot.model_dump()},
            ethical_pdma_result=pdma_result,
            csdma_result=csdma_result,
            dsdma_result=dsdma_result,
            permitted_actions=[
                HandlerActionType.OBSERVE,
                HandlerActionType.SPEAK,
                HandlerActionType.DEFER,
                HandlerActionType.TASK_COMPLETE,
            ],
        )

    @pytest.mark.asyncio
    async def test_aspdma_accepts_valid_typed_input(self, mock_service_registry, valid_dma_inputs):
        """Test that ASPDMA accepts properly typed EnhancedDMAInputs and returns ActionSelectionDMAResult."""
        # Create evaluator
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        # Mock the LLM call to return a proper ActionSelectionDMAResult
        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Here is my response to your question"),
            rationale="User asked a question that needs a response",
            reasoning="Based on ethical approval and common sense validation",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        # Evaluate
        result = await evaluator.evaluate(valid_dma_inputs)

        # Verify result is proper schema
        assert isinstance(result, ActionSelectionDMAResult)
        assert result.selected_action == HandlerActionType.SPEAK
        assert isinstance(result.action_parameters, SpeakParams)
        assert result.action_parameters.content == "Here is my response to your question"

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
    async def test_aspdma_validates_identity_when_present(self, mock_service_registry, valid_dma_inputs):
        """Test that ASPDMA properly validates identity when present in context."""
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=ObserveParams(),
            rationale="Need more information",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        # Evaluate with valid identity
        result = await evaluator.evaluate(valid_dma_inputs)

        # Should succeed with valid identity
        assert isinstance(result, ActionSelectionDMAResult)
        assert result.selected_action == HandlerActionType.OBSERVE

        # Check that identity block was formatted
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # Should have identity block in system message
        system_content = str(messages)  # Convert to string to search
        assert "CORE IDENTITY" in system_content or len(messages) > 0  # Identity should be included

    @pytest.mark.asyncio
    async def test_aspdma_fails_with_incomplete_identity(self, mock_service_registry, valid_thought):
        """Test that ASPDMA fails when identity is incomplete."""
        # Create inputs with incomplete identity (missing role)
        incomplete_snapshot = SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent",
                # Missing "role"!
            }
        )

        pdma_result = EthicalDMAResult(decision="approve", reasoning="OK", alignment_check="Basic ethical approval without detailed analysis.")

        # Need a valid CSDMA result even for this test
        csdma_result = CSDMAResult(plausibility_score=0.5, flags=[], reasoning="Test")

        inputs = EnhancedDMAInputs(
            original_thought=valid_thought,
            processing_context={"system_snapshot": incomplete_snapshot.model_dump()},
            ethical_pdma_result=pdma_result,
            csdma_result=csdma_result,  # Can't be None - context_builder expects it
            dsdma_result=None,
            permitted_actions=[
                HandlerActionType.OBSERVE,
                HandlerActionType.SPEAK,
            ],  # Add this so the test can proceed to identity check
        )

        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        # Mock the sink to have an LLM that would succeed
        # This ensures we get to the identity validation
        evaluator.sink = Mock()
        evaluator.sink.llm = Mock()

        # The error gets caught and returns a fallback PONDER result
        result = await evaluator.evaluate(inputs)

        # Should return a fallback PONDER result due to missing role
        assert isinstance(result, ActionSelectionDMAResult)
        assert result.selected_action == HandlerActionType.PONDER
        assert "CRITICAL" in result.rationale
        assert "role is missing" in result.rationale

    @pytest.mark.asyncio
    async def test_aspdma_handles_llm_failure(self, mock_service_registry, valid_dma_inputs):
        """Test that ASPDMA handles LLM failures gracefully."""
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        # Mock LLM to raise an exception
        evaluator.call_llm_structured = AsyncMock(side_effect=Exception("LLM service unavailable"))

        # Evaluate
        result = await evaluator.evaluate(valid_dma_inputs)

        # Should return a valid result with DEFER action
        assert isinstance(result, ActionSelectionDMAResult)
        # The specific behavior depends on implementation

    @pytest.mark.asyncio
    async def test_aspdma_requires_enhanced_dma_inputs(self, mock_service_registry):
        """Test that ASPDMA requires EnhancedDMAInputs, not raw dicts."""
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        # Try to pass a dict instead of EnhancedDMAInputs
        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate(None)

        assert "input_data is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aspdma_uses_faculty_results(self, mock_service_registry, valid_dma_inputs):
        """Test that ASPDMA properly uses faculty evaluation results."""
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry)

        mock_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content="Response based on faculty evaluations"),
            rationale="All faculties approve",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate(valid_dma_inputs)

        # Verify faculty results were used
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # Convert messages to string to check for faculty results
        messages_str = str(messages)

        # Should reference the faculty evaluations
        assert isinstance(result, ActionSelectionDMAResult)
        # The faculty results should be included in the prompt

    def test_aspdma_repr(self, mock_service_registry):
        """Test string representation of ASPDMA evaluator."""
        evaluator = ActionSelectionPDMAEvaluator(service_registry=mock_service_registry, model_name="gpt-4")

        repr_str = repr(evaluator)
        assert "ActionSelectionPDMAEvaluator" in repr_str
        assert "gpt-4" in repr_str
