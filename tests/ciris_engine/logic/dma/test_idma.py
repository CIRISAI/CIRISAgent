"""Test IDMA (Intuition DMA) evaluator - Coherence Collapse Analysis implementation.

Tests the semantic CCA implementation which evaluates:
- k_eff (effective independent sources): k / (1 + ρ(k-1))
- correlation_risk (ρ): How correlated are the sources
- phase: chaos / healthy / rigidity
- fragility_flag: k_eff < 2 or rigidity phase
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma.idma import IDMAEvaluator
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.dma.results import CSDMAResult, DSDMAResult, EthicalDMAResult, IDMAResult
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot


class TestIDMAEvaluator:
    """Test IDMA evaluator for Coherence Collapse Analysis."""

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
        mock_collection.get_system_message = Mock(return_value="Evaluate epistemic diversity.")
        mock_collection.get_user_message = Mock(return_value="Prior DMA context to analyze")

        mock_loader.load_prompt_template = Mock(return_value=mock_collection)
        mock_loader.uses_covenant_header = Mock(return_value=True)
        mock_loader.get_system_message = Mock(return_value="Evaluate epistemic diversity.")
        mock_loader.get_user_message = Mock(return_value="Prior DMA context to analyze")

        monkeypatch.setattr("ciris_engine.logic.dma.idma.get_prompt_loader", lambda: mock_loader)
        return mock_loader

    @pytest.fixture
    def valid_system_snapshot(self):
        """Create a valid SystemSnapshot."""
        return SystemSnapshot(
            agent_identity={
                "agent_id": "test_agent",
                "description": "Test agent for IDMA evaluation",
                "role": "Assistant for testing purposes",
            },
            channel_id="test_channel",
            agent_version="1.8.0",
            system_counts={"total_tasks": 1, "total_thoughts": 1},
        )

    @pytest.fixture
    def valid_thought(self):
        """Create a valid Thought object."""
        return Thought(
            thought_id="test-thought-123",
            source_task_id="test-task-456",
            content="Should I recommend this investment strategy?",
            status=ThoughtStatus.PROCESSING,
            thought_type=ThoughtType.STANDARD,
            thought_depth=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=ThoughtContext(task_id="test-task-456", round_number=1, depth=1, correlation_id="test-correlation"),
        )

    @pytest.fixture
    def valid_queue_item(self, valid_thought, valid_system_snapshot):
        """Create a valid ProcessingQueueItem."""
        content = ThoughtContent(text="Should I recommend this investment strategy?", metadata={})
        queue_item = ProcessingQueueItem.from_thought(
            valid_thought, raw_input="Should I recommend this investment strategy?", queue_item_content=content
        )
        queue_item.initial_context = {
            "system_snapshot": valid_system_snapshot.model_dump(),
        }
        return queue_item

    @pytest.fixture
    def mock_csdma_result(self):
        """Create mock CSDMA result for prior context."""
        return CSDMAResult(
            plausibility_score=0.8,
            flags=["financial_advice"],
            reasoning="The thought involves financial recommendations which require careful consideration.",
        )

    @pytest.fixture
    def mock_dsdma_result(self):
        """Create mock DSDMA result for prior context."""
        return DSDMAResult(
            domain_alignment=0.7,
            domain="financial",
            flags=["requires_expertise"],
            reasoning="Financial domain requires specialized knowledge.",
        )

    @pytest.fixture
    def mock_ethical_result(self):
        """Create mock PDMA result for prior context."""
        return EthicalDMAResult(
            stakeholders="user, financial_advisors, regulatory_bodies",
            conflicts="user_benefit vs risk_of_loss, advice_quality vs liability",
            reasoning="Multiple stakeholders with potentially conflicting interests.",
            alignment_check="Beneficence: supports user goals; Non-maleficence: financial risk exists",
        )

    # ==================== Core Functionality Tests ====================

    @pytest.mark.asyncio
    async def test_idma_healthy_reasoning_multiple_sources(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test IDMA detects healthy reasoning with multiple independent sources."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        # Healthy result: k_eff >= 2, low correlation, healthy phase
        mock_result = IDMAResult(
            k_eff=2.5,
            correlation_risk=0.2,
            phase="healthy",
            fragility_flag=False,
            sources_identified=["academic_research", "industry_practice", "regulatory_guidance"],
            correlation_factors=["minor_overlap_in_methodology"],
            reasoning="Multiple independent sources with diverse perspectives provide robust reasoning.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        assert isinstance(result, IDMAResult)
        assert result.k_eff >= 2.0
        assert result.fragility_flag is False
        assert result.phase == "healthy"
        assert len(result.sources_identified) >= 2

    @pytest.mark.asyncio
    async def test_idma_fragile_reasoning_single_source(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test IDMA detects fragile reasoning with single source dependence."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        # Fragile result: k_eff < 2, high correlation, rigidity phase
        mock_result = IDMAResult(
            k_eff=1.0,
            correlation_risk=0.9,
            phase="rigidity",
            fragility_flag=True,
            sources_identified=["single_blog_post"],
            correlation_factors=["echo_chamber", "no_independent_verification"],
            reasoning="Single source with no independent verification indicates fragile reasoning.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        assert isinstance(result, IDMAResult)
        assert result.k_eff < 2.0
        assert result.fragility_flag is True
        assert result.phase == "rigidity"

    @pytest.mark.asyncio
    async def test_idma_chaos_phase_contradictory_sources(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test IDMA detects chaos phase with contradictory sources."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=3.0,
            correlation_risk=0.1,
            phase="chaos",
            fragility_flag=True,  # Chaos is also fragile
            sources_identified=["source_a", "source_b", "source_c"],
            correlation_factors=["contradictory_conclusions"],
            reasoning="Sources provide contradictory information, unable to synthesize coherent position.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        assert isinstance(result, IDMAResult)
        assert result.phase == "chaos"
        # Chaos phase should trigger fragility even with high k_eff
        assert result.fragility_flag is True

    # ==================== k_eff Formula Edge Cases ====================

    @pytest.mark.asyncio
    async def test_idma_keff_approaches_one_high_correlation(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test k_eff approaches 1 as correlation approaches 1 (echo chamber collapse)."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        # k_eff = k / (1 + ρ(k-1))
        # With k=5, ρ=0.95: k_eff = 5 / (1 + 0.95*4) = 5 / 4.8 = 1.04
        mock_result = IDMAResult(
            k_eff=1.04,
            correlation_risk=0.95,
            phase="rigidity",
            fragility_flag=True,
            sources_identified=["news_a", "news_b", "news_c", "news_d", "news_e"],
            correlation_factors=["same_press_release", "shared_ownership", "identical_framing"],
            reasoning="Five sources that all derive from the same press release - effectively one voice.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        assert result.k_eff < 2.0  # Despite 5 nominal sources
        assert result.correlation_risk > 0.9
        assert result.fragility_flag is True

    @pytest.mark.asyncio
    async def test_idma_nascent_agent_expected_low_keff(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test nascent agents have expected low k_eff (~1.0)."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        # Nascent agent relying primarily on training data
        mock_result = IDMAResult(
            k_eff=1.0,
            correlation_risk=0.0,
            phase="rigidity",
            fragility_flag=True,
            sources_identified=["llm_training_data"],
            correlation_factors=["nascent_agent", "no_external_sources"],
            reasoning="Nascent agent with no external sources - expected initial state.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(valid_queue_item)

        assert result.k_eff == 1.0
        assert result.fragility_flag is True
        # This is expected for nascent agents, not an error

    # ==================== Prior DMA Context Tests ====================

    @pytest.mark.asyncio
    async def test_idma_uses_prior_dma_results(
        self,
        mock_service_registry,
        mock_prompt_loader,
        valid_queue_item,
        mock_csdma_result,
        mock_dsdma_result,
        mock_ethical_result,
    ):
        """Test IDMA uses prior DMA results for context."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=2.0,
            correlation_risk=0.3,
            phase="healthy",
            fragility_flag=False,
            sources_identified=["csdma_analysis", "dsdma_analysis", "ethical_analysis"],
            correlation_factors=[],
            reasoning="Prior DMA analyses provide diverse perspectives.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(
            valid_queue_item,
            ethical_result=mock_ethical_result,
            csdma_result=mock_csdma_result,
            dsdma_result=mock_dsdma_result,
        )

        assert isinstance(result, IDMAResult)

        # Verify LLM was called
        evaluator.call_llm_structured.assert_called_once()
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]

        # Should have multiple messages (covenant, system, user)
        assert len(messages) >= 2
        # Response model should be IDMAResult
        assert call_args.kwargs["response_model"] == IDMAResult

    @pytest.mark.asyncio
    async def test_idma_works_without_prior_dma(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test IDMA works without prior DMA results."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=1.5,
            correlation_risk=0.4,
            phase="healthy",
            fragility_flag=True,
            sources_identified=["thought_content_only"],
            correlation_factors=[],
            reasoning="Evaluated based on thought content alone.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        # Call without any prior DMA results
        result = await evaluator.evaluate_thought(valid_queue_item)

        assert isinstance(result, IDMAResult)
        assert result.k_eff == 1.5

    # ==================== Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_idma_raises_on_llm_failure(self, mock_service_registry, mock_prompt_loader, valid_queue_item):
        """Test IDMA raises exception on LLM failure (no fallback - per CIRIS principles)."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        evaluator.call_llm_structured = AsyncMock(side_effect=Exception("LLM service unavailable"))

        # IDMA should raise, not return fallback (per CIRIS no-bypass principles)
        with pytest.raises(Exception, match="LLM service unavailable"):
            await evaluator.evaluate_thought(valid_queue_item)

    @pytest.mark.asyncio
    async def test_idma_requires_input_data(self, mock_service_registry, mock_prompt_loader):
        """Test IDMA raises on missing input data."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        with pytest.raises(ValueError, match="input_data is required"):
            await evaluator.evaluate(input_data=None)

    # ==================== Context Extraction Tests ====================

    @pytest.mark.asyncio
    async def test_idma_extracts_agent_identity(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item, valid_system_snapshot
    ):
        """Test IDMA extracts agent identity from context."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=2.0,
            correlation_risk=0.2,
            phase="healthy",
            fragility_flag=False,
            sources_identified=["source1", "source2"],
            correlation_factors=[],
            reasoning="Test",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        context = Mock()
        context.system_snapshot = valid_system_snapshot

        await evaluator.evaluate_thought(valid_queue_item, context=context)

        # Verify LLM was called with messages
        call_args = evaluator.call_llm_structured.call_args
        messages = call_args.kwargs["messages"]
        # IDMA should have system and user messages
        assert len(messages) >= 2
        assert any(m.get("role") == "system" for m in messages)
        assert any(m.get("role") == "user" for m in messages)

    @pytest.mark.asyncio
    async def test_idma_handles_missing_context(self, mock_service_registry, mock_prompt_loader, valid_thought):
        """Test IDMA handles missing context gracefully."""
        content = ThoughtContent(text="Test thought", metadata={})
        queue_item = ProcessingQueueItem.from_thought(valid_thought, queue_item_content=content)
        queue_item.initial_context = {}

        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=1.0,
            correlation_risk=0.0,
            phase="rigidity",
            fragility_flag=True,
            sources_identified=["thought_only"],
            correlation_factors=[],
            reasoning="Evaluated without system context.",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate_thought(queue_item)
        assert isinstance(result, IDMAResult)

    # ==================== Backward Compatibility Tests ====================

    @pytest.mark.asyncio
    async def test_idma_evaluate_method_compatibility(
        self, mock_service_registry, mock_prompt_loader, valid_queue_item
    ):
        """Test evaluate() method backward compatibility."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry)

        mock_result = IDMAResult(
            k_eff=2.0,
            correlation_risk=0.2,
            phase="healthy",
            fragility_flag=False,
            sources_identified=["s1", "s2"],
            correlation_factors=[],
            reasoning="Test",
        )

        evaluator.call_llm_structured = AsyncMock(return_value=(mock_result, None))

        result = await evaluator.evaluate(input_data=valid_queue_item)

        assert isinstance(result, IDMAResult)
        assert result.k_eff == 2.0

    def test_idma_repr(self, mock_service_registry, mock_prompt_loader):
        """Test string representation of IDMA evaluator."""
        evaluator = IDMAEvaluator(service_registry=mock_service_registry, model_name="gpt-4")

        repr_str = repr(evaluator)
        assert "IDMAEvaluator" in repr_str
        assert "gpt-4" in repr_str


class TestIDMAResultSchema:
    """Test IDMAResult schema validation."""

    def test_valid_idma_result(self):
        """Test creating a valid IDMAResult."""
        result = IDMAResult(
            k_eff=2.5,
            correlation_risk=0.3,
            phase="healthy",
            fragility_flag=False,
            sources_identified=["source1", "source2", "source3"],
            correlation_factors=["minor_overlap"],
            reasoning="Multiple independent sources provide robust reasoning.",
        )

        assert result.k_eff == 2.5
        assert result.correlation_risk == 0.3
        assert result.phase == "healthy"
        assert result.fragility_flag is False
        assert len(result.sources_identified) == 3

    def test_idma_result_correlation_risk_bounds(self):
        """Test correlation_risk must be between 0 and 1."""
        # Valid at boundaries
        result_low = IDMAResult(
            k_eff=1.0, correlation_risk=0.0, phase="healthy", fragility_flag=False, reasoning="test"
        )
        result_high = IDMAResult(
            k_eff=1.0, correlation_risk=1.0, phase="rigidity", fragility_flag=True, reasoning="test"
        )
        assert result_low.correlation_risk == 0.0
        assert result_high.correlation_risk == 1.0

        # Invalid - out of bounds
        with pytest.raises(ValueError):
            IDMAResult(k_eff=1.0, correlation_risk=-0.1, phase="healthy", fragility_flag=False, reasoning="test")

        with pytest.raises(ValueError):
            IDMAResult(k_eff=1.0, correlation_risk=1.1, phase="healthy", fragility_flag=False, reasoning="test")

    def test_idma_result_keff_non_negative(self):
        """Test k_eff must be non-negative."""
        # Valid at 0
        result = IDMAResult(k_eff=0.0, correlation_risk=0.0, phase="chaos", fragility_flag=True, reasoning="No sources")
        assert result.k_eff == 0.0

        # Invalid - negative
        with pytest.raises(ValueError):
            IDMAResult(k_eff=-1.0, correlation_risk=0.0, phase="healthy", fragility_flag=False, reasoning="test")

    def test_idma_result_required_fields(self):
        """Test required fields raise on missing."""
        with pytest.raises(ValueError):
            IDMAResult(correlation_risk=0.5, phase="healthy", fragility_flag=False, reasoning="test")  # missing k_eff

        with pytest.raises(ValueError):
            IDMAResult(k_eff=2.0, phase="healthy", fragility_flag=False, reasoning="test")  # missing correlation_risk

        with pytest.raises(ValueError):
            IDMAResult(k_eff=2.0, correlation_risk=0.5, fragility_flag=False, reasoning="test")  # missing phase

    def test_idma_result_optional_fields_default(self):
        """Test optional fields have correct defaults."""
        result = IDMAResult(
            k_eff=2.0,
            correlation_risk=0.3,
            phase="healthy",
            fragility_flag=False,
            reasoning="Test reasoning",
        )

        # Optional fields should default to empty lists
        assert result.sources_identified == []
        assert result.correlation_factors == []

    def test_idma_result_forbids_extra_fields(self):
        """Test IDMAResult forbids extra fields."""
        with pytest.raises(ValueError):
            IDMAResult(
                k_eff=2.0,
                correlation_risk=0.3,
                phase="healthy",
                fragility_flag=False,
                reasoning="test",
                extra_field="not_allowed",  # This should fail
            )
