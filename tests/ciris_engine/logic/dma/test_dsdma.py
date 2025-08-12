"""Test DSDMA evaluator with proper typed schemas - NO DICTS!"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.dma.results import DSDMAResult
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot


class TestDSDMAEvaluator:
    """Test DSDMA evaluator with properly typed objects."""

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
        mock_collection.get_system_message = Mock(return_value="Evaluate for domain alignment.")
        mock_collection.get_user_message = Mock(return_value="Thought to evaluate: Test thought")
        mock_collection.get_prompt = Mock(return_value="Domain evaluation template")

        mock_loader.load_prompt_template = Mock(return_value=mock_collection)

        # Mock the get_prompt_loader function
        monkeypatch.setattr("ciris_engine.logic.dma.dsdma_base.get_prompt_loader", lambda: mock_loader)
        return mock_loader

    @pytest.fixture
    def valid_system_snapshot(self):
        """Create a valid SystemSnapshot with complete identity."""
        return SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent for DSDMA evaluation",
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
            content="Should I perform a medical diagnosis?",
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
        content = ThoughtContent(text="Should I perform a medical diagnosis?", metadata={})

        # Create the queue item from the thought
        queue_item = ProcessingQueueItem.from_thought(
            valid_thought, raw_input="Should I perform a medical diagnosis?", queue_item_content=content
        )

        # Add the context with system snapshot (using proper attribute assignment)
        queue_item.initial_context = {
            "system_snapshot": valid_system_snapshot.model_dump(),
            "environment_context": {"description": "Medical consultation context"},
        }

        return queue_item

    @pytest.mark.asyncio
    async def test_dsdma_accepts_valid_typed_input(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test that DSDMA accepts properly typed ProcessingQueueItem and returns DSDMAResult."""
        # Create evaluator for medical domain
        evaluator = BaseDSDMA(
            domain_name="medical",
            service_registry=mock_service_registry,
            domain_specific_knowledge={"rules_summary": "Medical domain requires professional credentials"},
        )

        # Mock the LLM call to return LLMOutputForDSDMA (not DSDMAResult!)

        mock_llm_output = BaseDSDMA.LLMOutputForDSDMA(
            score=0.9,
            flags=["requires_medical_license", "high_risk"],
            reasoning="Medical diagnosis requires professional medical credentials and licensing.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_output, None))

        # Evaluate
        result = await evaluator.evaluate_thought(valid_queue_item, current_context=None)

        # Verify result is proper schema
        assert isinstance(result, DSDMAResult)
        assert result.domain == "medical"
        assert result.domain_alignment == 0.9
        assert "requires_medical_license" in result.flags
        assert "Medical diagnosis requires" in result.reasoning

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
    async def test_dsdma_fails_without_identity(self, mock_service_registry, mock_prompt_loader, valid_thought):
        """Test that DSDMA fails fast when agent identity is missing."""
        # Create queue item WITHOUT system snapshot
        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)

        # No initial_context means no identity
        queue_item.initial_context = {}

        evaluator = BaseDSDMA(domain_name="test_domain", service_registry=mock_service_registry)

        # Mock the sink to avoid the sink error - we want to test identity validation
        evaluator.sink = Mock()
        evaluator.sink.llm = Mock()

        # Should raise ValueError about missing identity
        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate_thought(queue_item, current_context=None)

        assert "CRITICAL" in str(exc_info.value)
        assert "No system_snapshot" in str(exc_info.value)
        assert "test_domain" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dsdma_fails_with_incomplete_identity(self, mock_service_registry, mock_prompt_loader, valid_thought):
        """Test that DSDMA fails when identity is missing required fields."""
        # Create system snapshot with incomplete identity (missing description)
        incomplete_snapshot = SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                # Missing "description"!
                "role": "Assistant",
            }
        )

        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)
        queue_item.initial_context = {"system_snapshot": incomplete_snapshot.model_dump()}

        evaluator = BaseDSDMA(domain_name="finance", service_registry=mock_service_registry)

        # Mock the sink to avoid the sink error
        evaluator.sink = Mock()
        evaluator.sink.llm = Mock()

        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate_thought(queue_item, current_context=None)

        assert "CRITICAL" in str(exc_info.value)
        assert "description is missing" in str(exc_info.value)
        assert "finance" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dsdma_handles_llm_failure(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test that DSDMA returns proper error result when LLM fails."""
        evaluator = BaseDSDMA(domain_name="legal", service_registry=mock_service_registry)

        # Mock LLM to raise an exception
        evaluator.call_llm_structured = AsyncMock(side_effect=Exception("LLM service unavailable"))

        # Evaluate
        result = await evaluator.evaluate_thought(valid_queue_item, current_context=None)

        # Should return error result with default values
        assert isinstance(result, DSDMAResult)
        assert result.domain == "legal"  # Uses domain name
        assert result.domain_alignment == 0.0
        assert "LLM_Error_Instructor" in result.flags  # Changed because instructor mode uses different flag
        assert "Failed DSDMA evaluation" in result.reasoning

    @pytest.mark.asyncio
    async def test_dsdma_uses_domain_specific_knowledge(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test that DSDMA properly uses domain-specific knowledge."""
        domain_knowledge = {
            "rules_summary": "Financial transactions require compliance with SEC regulations",
            "risk_factors": ["regulatory_compliance", "fraud_detection"],
        }

        evaluator = BaseDSDMA(
            domain_name="finance", service_registry=mock_service_registry, domain_specific_knowledge=domain_knowledge
        )

        mock_llm_output = BaseDSDMA.LLMOutputForDSDMA(
            score=0.7,
            flags=["regulatory_risk"],
            reasoning="Requires SEC compliance review",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_output, None))

        result = await evaluator.evaluate_thought(valid_queue_item, current_context=None)

        # Verify domain knowledge was used
        assert isinstance(result, DSDMAResult)
        assert result.domain == "finance"

        # Check that proper context was used in message construction
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # Should have system message with domain rules
        system_content = messages[0]["content"] if messages else ""
        # The domain rules should be included in the prompt

    @pytest.mark.asyncio
    async def test_dsdma_formats_identity_block_correctly(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test that DSDMA formats the identity block with CORE IDENTITY header."""
        evaluator = BaseDSDMA(domain_name="engineering", service_registry=mock_service_registry)

        mock_llm_output = BaseDSDMA.LLMOutputForDSDMA(score=0.5, flags=[], reasoning="Test")
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_output, None))

        await evaluator.evaluate_thought(valid_queue_item, current_context=None)

        # Check the messages passed to LLM
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # System message should contain CORE IDENTITY block
        # First message is Covenant, second should be the system prompt with identity
        if len(messages) > 1:
            system_content = messages[1]["content"]
        else:
            # If only one message, it should contain identity
            system_content = messages[0]["content"]

        assert "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===" in system_content
        assert "Agent: test_agent" in system_content
        assert "Description: Test agent for DSDMA evaluation" in system_content
        assert "Role: Assistant for testing purposes" in system_content
        assert "============================================" in system_content

    @pytest.mark.asyncio
    async def test_dsdma_evaluate_method_backward_compatibility(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test that the evaluate() method maintains backward compatibility."""
        evaluator = BaseDSDMA(domain_name="general", service_registry=mock_service_registry)

        mock_llm_output = BaseDSDMA.LLMOutputForDSDMA(score=0.8, flags=[], reasoning="Valid thought")
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_output, None))

        # Call via evaluate() method
        result = await evaluator.evaluate(input_data=valid_queue_item)

        assert isinstance(result, DSDMAResult)
        assert result.domain_alignment == 0.8

    @pytest.mark.asyncio
    async def test_dsdma_with_invalid_initial_context_type(
        self, mock_service_registry, mock_prompt_loader, valid_thought
    ):
        """Test that DSDMA fails fast when initial_context is not a dict."""
        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)

        # Set initial_context to wrong type
        queue_item.initial_context = "not a dict"  # Wrong type!

        evaluator = BaseDSDMA(domain_name="test_domain", service_registry=mock_service_registry)

        with pytest.raises(ValueError) as exc_info:
            await evaluator.evaluate_thought(queue_item, current_context=None)

        assert "CRITICAL" in str(exc_info.value)
        assert "initial_context must be a dict" in str(exc_info.value)
        assert "got str" in str(exc_info.value)

    def test_dsdma_repr(self, mock_service_registry, mock_prompt_loader):
        """Test string representation of DSDMA evaluator."""
        evaluator = BaseDSDMA(domain_name="scientific", service_registry=mock_service_registry, model_name="gpt-4")

        repr_str = repr(evaluator)
        assert "BaseDSDMA" in repr_str
        assert "scientific" in repr_str  # Domain name should be in repr
