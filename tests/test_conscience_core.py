"""
Comprehensive tests for conscience/core.py

Tests all four conscience types:
- EntropyConscience
- CoherenceConscience
- OptimizationVetoConscience
- EpistemicHumilityConscience

Target: 80%+ coverage (currently 20.5%)
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from ciris_engine.logic.conscience.core import (
    CoherenceConscience,
    ConscienceConfig,
    CoherenceResult,
    EntropyConscience,
    EntropyResult,
    EpistemicHumilityConscience,
    OptimizationVetoConscience,
    _BaseConscience,
)
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.conscience.core import (
    ConscienceCheckResult,
    ConscienceStatus,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_time_service():
    """Mock time service"""
    service = Mock()
    service.now.return_value = datetime(2025, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
    return service


@pytest.fixture
def mock_service_registry(mock_time_service):
    """Mock service registry"""
    registry = Mock(spec=ServiceRegistry)
    registry.get_services_by_type.return_value = [mock_time_service]
    return registry


@pytest.fixture
def conscience_config():
    """Default conscience config"""
    return ConscienceConfig(
        enabled=True,
        optimization_veto_ratio=10.0,
        coherence_threshold=0.60,
        entropy_threshold=0.40,
    )


@pytest.fixture
def mock_sink_with_llm():
    """Mock sink (BusManager) with LLM service"""
    sink = Mock()
    sink.llm = Mock()
    sink.llm.call_llm_structured = AsyncMock()
    return sink


@pytest.fixture
def action_speak():
    """SPEAK action with content"""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Hello, how can I help you?"),
        rationale="Test rationale",
        reasoning="Test reasoning",
    )


@pytest.fixture
def action_non_speak():
    """Non-SPEAK action (PONDER)"""
    from ciris_engine.schemas.actions.parameters import PonderParams

    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["What should I do?"]),
        rationale="Test rationale",
        reasoning="Test reasoning",
    )


@pytest.fixture
def context_with_thought():
    """Context dict with thought"""
    thought = Mock()
    thought.thought_id = "thought_123"
    thought.source_task_id = "task_456"
    return {"thought": thought}


# ============================================================================
# BASE CONSCIENCE TESTS
# ============================================================================


class TestBaseConscience:
    """Tests for _BaseConscience base class"""

    def test_init_without_time_service_raises(self, mock_service_registry, conscience_config):
        """Test that init without time service raises RuntimeError"""
        with pytest.raises(RuntimeError, match="TimeService is required"):
            _BaseConscience(
                service_registry=mock_service_registry,
                config=conscience_config,
                time_service=None,
            )

    def test_init_with_time_service_succeeds(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test successful initialization with time service"""
        conscience = _BaseConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )
        assert conscience._time_service == mock_time_service
        assert conscience.config == conscience_config

    @pytest.mark.asyncio
    async def test_get_sink_without_sink_raises(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _get_sink() raises when sink is None"""
        conscience = _BaseConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=None,
        )
        with pytest.raises(RuntimeError, match="No sink"):
            await conscience._get_sink()

    @pytest.mark.asyncio
    async def test_get_sink_with_sink_returns(
        self, mock_service_registry, conscience_config, mock_time_service, mock_sink_with_llm
    ):
        """Test _get_sink() returns sink when available"""
        conscience = _BaseConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )
        sink = await conscience._get_sink()
        assert sink == mock_sink_with_llm

    @patch("ciris_engine.logic.conscience.core.persistence")
    def test_create_trace_correlation(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        context_with_thought,
    ):
        """Test _create_trace_correlation creates proper correlation"""
        conscience = _BaseConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )
        start_time = datetime(2025, 10, 7, 12, 0, 0, tzinfo=timezone.utc)

        correlation = conscience._create_trace_correlation("entropy", context_with_thought, start_time)

        assert correlation.correlation_type.value == "trace_span"
        assert correlation.service_type == "guardrail"
        assert correlation.tags["guardrail_type"] == "entropy"
        mock_persistence.add_correlation.assert_called_once()

    @patch("ciris_engine.logic.conscience.core.persistence")
    def test_update_trace_correlation(
        self, mock_persistence, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _update_trace_correlation updates correlation"""
        conscience = _BaseConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )
        correlation = Mock()
        correlation.correlation_id = "test_corr_id"
        start_time = datetime(2025, 10, 7, 12, 0, 0, tzinfo=timezone.utc)

        conscience._update_trace_correlation(correlation, True, "Test result", start_time)

        mock_persistence.update_correlation.assert_called_once()
        update_req = mock_persistence.update_correlation.call_args[0][0]
        assert update_req.correlation_id == "test_corr_id"
        assert update_req.response_data["success"] == "true"


# ============================================================================
# ENTROPY CONSCIENCE TESTS
# ============================================================================


class TestEntropyConscience:
    """Tests for EntropyConscience"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_non_speak_action_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        action_non_speak,
        context_with_thought,
    ):
        """Test that non-SPEAK actions pass immediately"""
        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        result = await conscience.check(action_non_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_sink_unavailable_warning(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        action_speak,
        context_with_thought,
    ):
        """Test that unavailable sink returns WARNING"""
        # Create mock sink that returns None (simulating unavailable)
        mock_sink = Mock()
        mock_sink_manager = Mock()

        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_manager,
        )

        # Mock _get_sink to return None
        conscience._get_sink = AsyncMock(return_value=None)

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.WARNING
        assert "unavailable" in result.reason.lower()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_no_content_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        context_with_thought,
    ):
        """Test that action with no content passes"""
        action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.SPEAK,
            action_parameters=SpeakParams(content=""),
            rationale="Test rationale",
            reasoning="Test",
        )

        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_low_entropy_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that low entropy content passes"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            EntropyResult(entropy=0.2),
            None,
        )

        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.entropy_score == 0.2

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_high_entropy_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that high entropy content fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            EntropyResult(entropy=0.8),
            None,
        )

        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert "0.80" in result.reason

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_llm_error_uses_default(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that LLM errors use default safe entropy value"""
        mock_sink_with_llm.llm.call_llm_structured.side_effect = Exception("LLM error")

        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        # Default entropy is 0.1, which is below threshold 0.4
        assert result.passed is True
        assert result.entropy_score == 0.1

    def test_create_entropy_messages(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _create_entropy_messages generates proper messages"""
        conscience = EntropyConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        messages = conscience._create_entropy_messages("Hello world")

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "IRIS-E" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Hello world" in messages[2]["content"]


# ============================================================================
# COHERENCE CONSCIENCE TESTS
# ============================================================================


class TestCoherenceConscience:
    """Tests for CoherenceConscience"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_non_speak_action_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        action_non_speak,
        context_with_thought,
    ):
        """Test that non-SPEAK actions pass immediately"""
        conscience = CoherenceConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        result = await conscience.check(action_non_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_high_coherence_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that high coherence content passes"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            CoherenceResult(coherence=0.9),
            None,
        )

        conscience = CoherenceConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED
        assert result.coherence_score == 0.9

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_low_coherence_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that low coherence content fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            CoherenceResult(coherence=0.3),
            None,
        )

        conscience = CoherenceConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert "0.30" in result.reason

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_llm_error_uses_default(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that LLM errors use default safe coherence value"""
        mock_sink_with_llm.llm.call_llm_structured.side_effect = Exception("LLM error")

        conscience = CoherenceConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        # Default coherence is 0.9, which is above threshold 0.6
        assert result.passed is True
        assert result.coherence_score == 0.9

    def test_create_coherence_messages(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _create_coherence_messages generates proper messages"""
        conscience = CoherenceConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        messages = conscience._create_coherence_messages("Hello world")

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "IRIS-C" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Hello world" in messages[2]["content"]


# ============================================================================
# OPTIMIZATION VETO CONSCIENCE TESTS
# ============================================================================


class TestOptimizationVetoConscience:
    """Tests for OptimizationVetoConscience"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_proceed_decision_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that 'proceed' decision with low ratio passes"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            OptimizationVetoResult(
                decision="proceed",
                justification="Safe action",
                entropy_reduction_ratio=2.0,
                affected_values=["efficiency"],
            ),
            None,
        )

        conscience = OptimizationVetoConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_abort_decision_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that 'abort' decision fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            OptimizationVetoResult(
                decision="abort",
                justification="Too risky",
                entropy_reduction_ratio=15.0,
                affected_values=["safety"],
            ),
            None,
        )

        conscience = OptimizationVetoConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert "Too risky" in result.reason

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_high_entropy_ratio_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that high entropy reduction ratio fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            OptimizationVetoResult(
                decision="proceed",
                justification="Test",
                entropy_reduction_ratio=20.0,  # > threshold of 10.0
                affected_values=["test"],
            ),
            None,
        )

        conscience = OptimizationVetoConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_llm_error_fails_safe(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that LLM errors fail safe (abort)"""
        mock_sink_with_llm.llm.call_llm_structured.side_effect = Exception("LLM error")

        conscience = OptimizationVetoConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.optimization_veto_check.decision == "abort"

    def test_create_optimization_veto_messages(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _create_optimization_veto_messages generates proper messages"""
        conscience = OptimizationVetoConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        messages = conscience._create_optimization_veto_messages("test action")

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "CIRIS-EOV" in messages[1]["content"]
        assert messages[2]["role"] == "user"


# ============================================================================
# EPISTEMIC HUMILITY CONSCIENCE TESTS
# ============================================================================


class TestEpistemicHumilityConscience:
    """Tests for EpistemicHumilityConscience"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_proceed_recommendation_passes(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that 'proceed' recommendation passes"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            EpistemicHumilityResult(
                epistemic_certainty=0.9,
                identified_uncertainties=[],
                reflective_justification="High confidence",
                recommended_action="proceed",
            ),
            None,
        )

        conscience = EpistemicHumilityConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is True
        assert result.status == ConscienceStatus.PASSED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_ponder_recommendation_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that 'ponder' recommendation fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            EpistemicHumilityResult(
                epistemic_certainty=0.5,
                identified_uncertainties=["Uncertain claim"],
                reflective_justification="Need more reflection",
                recommended_action="ponder",
            ),
            None,
        )

        conscience = EpistemicHumilityConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED
        assert "ponder" in result.reason

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_defer_recommendation_fails(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that 'defer' recommendation fails"""
        mock_sink_with_llm.llm.call_llm_structured.return_value = (
            EpistemicHumilityResult(
                epistemic_certainty=0.3,
                identified_uncertainties=["Unverified claim", "Negative characterization"],
                reflective_justification="Defer to avoid harm",
                recommended_action="defer",
            ),
            None,
        )

        conscience = EpistemicHumilityConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.status == ConscienceStatus.FAILED

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.conscience.core.persistence")
    async def test_check_llm_error_fails_safe(
        self,
        mock_persistence,
        mock_service_registry,
        conscience_config,
        mock_time_service,
        mock_sink_with_llm,
        action_speak,
        context_with_thought,
    ):
        """Test that LLM errors fail safe (abort)"""
        mock_sink_with_llm.llm.call_llm_structured.side_effect = Exception("LLM error")

        conscience = EpistemicHumilityConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
            sink=mock_sink_with_llm,
        )

        result = await conscience.check(action_speak, context_with_thought)

        assert result.passed is False
        assert result.epistemic_humility_check.recommended_action == "abort"

    def test_create_epistemic_humility_messages(
        self, mock_service_registry, conscience_config, mock_time_service
    ):
        """Test _create_epistemic_humility_messages generates proper messages"""
        conscience = EpistemicHumilityConscience(
            service_registry=mock_service_registry,
            config=conscience_config,
            time_service=mock_time_service,
        )

        messages = conscience._create_epistemic_humility_messages("test action")

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "system"
        assert "CIRIS-EH" in messages[1]["content"]
        assert messages[2]["role"] == "user"
