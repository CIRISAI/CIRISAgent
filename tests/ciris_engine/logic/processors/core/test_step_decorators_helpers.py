"""
Comprehensive tests for step_decorators.py helper functions.

Tests the helper functions created to reduce complexity:
- _validate_aspdma_result
- _extract_dma_results_from_args
- _create_entropy_check
- _create_coherence_check
- _create_optimization_veto_check
- _create_epistemic_humility_check
- _extract_follow_up_thought_id
- _extract_lightweight_system_snapshot
- Integration tests for refactored functions
"""

from unittest.mock import MagicMock, Mock

import pytest

from ciris_engine.logic.processors.core.step_decorators import (
    _create_action_complete_data,
    _create_coherence_check,
    _create_comprehensive_conscience_result,
    _create_entropy_check,
    _create_epistemic_humility_check,
    _create_finalize_action_data,
    _create_optimization_veto_check,
    _create_perform_action_data,
    _create_perform_aspdma_data,
    _create_recursive_aspdma_data,
    _create_recursive_conscience_data,
    _extract_dma_results_from_args,
    _extract_follow_up_thought_id,
    _extract_lightweight_system_snapshot,
    _validate_aspdma_result,
)
from ciris_engine.schemas.services.runtime_control import BaseStepData

# ============================================================================
# Shared Fixtures
# ============================================================================


@pytest.fixture
def base_step_data():
    """Common base step data for integration tests."""
    return BaseStepData(
        thought_id="thought_123",
        task_id="task_456",
        timestamp="2025-01-01T12:00:00Z",
        processing_time_ms=50.0,
        success=True,
    )


@pytest.fixture
def mock_aspdma_result():
    """Mock ASPDMA result with proper attributes."""
    result = Mock()
    result.selected_action = "PONDER"
    result.rationale = "Need more context"
    return result


@pytest.fixture
def mock_conscience_result_passed():
    """Mock conscience result for passed checks."""
    # Create nested structure for final_action
    final_action_mock = Mock()
    final_action_mock.selected_action = "SPEAK"

    result = Mock(spec=["overridden", "final_action", "selected_action", "override_reason", "epistemic_data", "__str__"])
    result.overridden = False
    result.final_action = final_action_mock
    result.selected_action = "SPEAK"
    result.override_reason = None
    result.epistemic_data = {}
    result.__str__ = Mock(return_value="passed")
    return result


@pytest.fixture
def mock_action_result():
    """Mock action execution result - ActionResponse with audit data."""
    from ciris_engine.schemas.services.runtime_control import ActionResponse
    from ciris_engine.schemas.audit.hash_chain import AuditEntryResult

    audit_data = AuditEntryResult(
        entry_id="test_123",
        sequence_number=1,
        entry_hash="hash_123",
        signature="sig_123"
    )
    # For tests that need ActionResponse
    result = ActionResponse(
        action_type="SPEAK",
        success=True,
        handler="TestHandler",
        audit_data=audit_data,
        execution_time_ms=125.0
    )
    return result


# ============================================================================
# Test Classes
# ============================================================================


class TestASPDMAHelpers:
    """Test ASPDMA-related helper functions."""

    def test_validate_aspdma_result_success(self):
        """Test successful ASPDMA result validation."""
        result = Mock()
        result.selected_action = "speak"
        result.rationale = "User needs help"

        # Should not raise
        _validate_aspdma_result(result)

    def test_validate_aspdma_result_none(self):
        """Test validation fails for None result."""
        with pytest.raises(ValueError, match="PERFORM_ASPDMA step result is None"):
            _validate_aspdma_result(None)

    def test_validate_aspdma_result_missing_selected_action(self):
        """Test validation fails when selected_action is missing."""
        result = Mock(spec=["rationale"])

        with pytest.raises(AttributeError, match="missing 'selected_action' attribute"):
            _validate_aspdma_result(result)

    def test_validate_aspdma_result_missing_rationale(self):
        """Test validation fails when rationale is missing."""
        result = Mock(spec=["selected_action"])

        with pytest.raises(AttributeError, match="missing 'rationale' attribute"):
            _validate_aspdma_result(result)

    def test_extract_dma_results_from_args_with_initial_dma_results(self):
        """Test extracting DMA results from InitialDMAResults object."""
        dma_results_obj = Mock()
        dma_results_obj.csdma = "common sense: proceed"
        dma_results_obj.dsdma = "domain: safe"

        args = ("context", dma_results_obj)

        result = _extract_dma_results_from_args(args)

        # Now returns the concrete object, not a string
        assert result == dma_results_obj

    def test_extract_dma_results_from_args_with_csdma_only(self):
        """Test extracting when only CSDMA is present."""
        dma_results_obj = Mock()
        dma_results_obj.csdma = "common sense: proceed"
        dma_results_obj.dsdma = None

        args = ("context", dma_results_obj)

        result = _extract_dma_results_from_args(args)

        # Now returns the concrete object, not a string
        assert result == dma_results_obj

    def test_extract_dma_results_from_args_string_format(self):
        """Test extracting DMA results from string object."""
        args = ("context", "some_dma_results_string")

        result = _extract_dma_results_from_args(args)

        assert result == "some_dma_results_string"

    def test_extract_dma_results_from_args_no_args(self):
        """Test extraction returns None when args are insufficient."""
        args = ("context_only",)

        result = _extract_dma_results_from_args(args)

        assert result is None

    def test_extract_dma_results_from_args_none_obj(self):
        """Test extraction returns None when dma_results_obj is None."""
        args = ("context", None)

        result = _extract_dma_results_from_args(args)

        assert result is None


class TestConscienceHelpers:
    """Test conscience evaluation helper functions."""

    def test_create_entropy_check_passed(self):
        """Test creating entropy check when passed."""
        result = _create_entropy_check(passed=True)

        assert result.passed is True
        assert result.entropy_score == 0.3
        assert result.threshold == 0.5
        assert "maintains appropriate information uncertainty" in result.message

    def test_create_entropy_check_failed(self):
        """Test creating entropy check when failed."""
        result = _create_entropy_check(passed=False)

        assert result.passed is False
        assert result.entropy_score == 0.3
        assert result.threshold == 0.5
        assert "Entropy check failed" in result.message

    def test_create_coherence_check_passed(self):
        """Test creating coherence check when passed."""
        result = _create_coherence_check(passed=True)

        assert result.passed is True
        assert result.coherence_score == 0.8
        assert result.threshold == 0.6
        assert "maintains internal consistency" in result.message

    def test_create_coherence_check_failed(self):
        """Test creating coherence check when failed."""
        result = _create_coherence_check(passed=False)

        assert result.passed is False
        assert "Coherence check failed" in result.message

    def test_create_optimization_veto_check_passed(self):
        """Test creating optimization veto check when passed."""
        result = _create_optimization_veto_check(passed=True)

        assert result.decision == "proceed"
        assert "preservation of human values" in result.justification
        assert result.affected_values == []

    def test_create_optimization_veto_check_failed(self):
        """Test creating optimization veto check when failed."""
        result = _create_optimization_veto_check(passed=False)

        assert result.decision == "abort"
        assert "optimization vetoed" in result.justification
        assert "human_autonomy" in result.affected_values
        assert "epistemic_humility" in result.affected_values

    def test_create_epistemic_humility_check_passed(self):
        """Test creating epistemic humility check when passed."""
        result = _create_epistemic_humility_check(passed=True)

        assert result.epistemic_certainty == 0.7
        assert result.identified_uncertainties == []
        assert "appropriate uncertainty" in result.reflective_justification
        assert result.recommended_action == "proceed"

    def test_create_epistemic_humility_check_failed(self):
        """Test creating epistemic humility check when failed."""
        result = _create_epistemic_humility_check(passed=False)

        assert result.epistemic_certainty == 0.7
        assert "action_outcome_variance" in result.identified_uncertainties
        assert "context_completeness" in result.identified_uncertainties
        assert "overconfidence" in result.reflective_justification
        assert result.recommended_action == "ponder"


class TestFollowUpThoughtHelpers:
    """Test follow-up thought ID extraction helpers (already tested in previous session)."""

    def test_extract_follow_up_thought_id_from_dict(self):
        """Test extracting follow-up thought ID from dict."""
        result = {
            "action_type": "SPEAK",
            "follow_up_thought_id": "thought_123",
        }

        thought_id = _extract_follow_up_thought_id(result)

        assert thought_id == "thought_123"

    def test_extract_follow_up_thought_id_terminal_action(self):
        """Test terminal actions return None."""
        result = {
            "action_type": "TASK_COMPLETE",
            "follow_up_thought_id": "should_be_ignored",
        }

        thought_id = _extract_follow_up_thought_id(result)

        assert thought_id is None


class TestSystemSnapshotHelpers:
    """Test system snapshot extraction helpers (already tested in previous session)."""

    def test_extract_lightweight_system_snapshot_structure(self):
        """Test snapshot returns SystemSnapshot object with current_time_utc."""
        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        snapshot = _extract_lightweight_system_snapshot()

        # Should return a SystemSnapshot object
        assert isinstance(snapshot, SystemSnapshot)
        # Should have current_time_utc set
        assert snapshot.current_time_utc is not None

    def test_extract_lightweight_system_snapshot_optional_metrics(self):
        """Test snapshot is a proper SystemSnapshot object."""
        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        snapshot = _extract_lightweight_system_snapshot()

        # Should be a SystemSnapshot with proper structure
        assert isinstance(snapshot, SystemSnapshot)
        # Should have the expected fields (even if None/empty)
        assert hasattr(snapshot, "channel_id")
        assert hasattr(snapshot, "channel_context")
        assert hasattr(snapshot, "system_counts")


class TestBroadcastEventHelpers:
    """Test broadcast reasoning event creation helpers."""

    def test_create_snapshot_and_context_event(self):
        """Test creating SNAPSHOT_AND_CONTEXT event."""
        from ciris_engine.logic.processors.core.step_decorators import _create_snapshot_and_context_event

        # Mock step_data
        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.context = "User asked: Hello"

        # Mock create_reasoning_event function
        mock_create = Mock(return_value="event_created")

        result = _create_snapshot_and_context_event(step_data, "2025-01-01T12:00:00Z", mock_create)

        assert result == "event_created"
        # Verify create_reasoning_event was called with correct args
        assert mock_create.called
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["thought_id"] == "thought_123"
        assert call_kwargs["task_id"] == "task_456"
        assert call_kwargs["context"] == "User asked: Hello"
        assert call_kwargs["context_size"] == len("User asked: Hello")
        assert "system_snapshot" in call_kwargs

    def test_create_dma_results_event(self):
        """Test creating DMA_RESULTS event."""
        from ciris_engine.logic.processors.core.step_decorators import _create_dma_results_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"

        # Mock InitialDMAResults with the 3 DMA results
        dma_results = Mock()
        csdma_obj = Mock()
        dsdma_obj = Mock()
        pdma_obj = Mock()

        dma_results.csdma = csdma_obj
        dma_results.dsdma = dsdma_obj
        dma_results.ethical_pdma = pdma_obj

        mock_create = Mock(return_value="dma_event")

        result = _create_dma_results_event(step_data, "2025-01-01T12:00:00Z", dma_results, mock_create)

        assert result == "dma_event"
        call_kwargs = mock_create.call_args[1]
        # Now passes the objects directly, not model_dump() results
        assert call_kwargs["csdma"] == csdma_obj
        assert call_kwargs["dsdma"] == dsdma_obj
        assert call_kwargs["pdma"] == pdma_obj

    def test_create_aspdma_result_event_non_recursive(self):
        """Test creating ASPDMA_RESULT event (non-recursive)."""
        from ciris_engine.logic.processors.core.step_decorators import _create_aspdma_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.selected_action = "SPEAK"
        step_data.action_rationale = "User needs help"

        mock_create = Mock(return_value="aspdma_event")

        result = _create_aspdma_result_event(step_data, "2025-01-01T12:00:00Z", False, mock_create)

        assert result == "aspdma_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["is_recursive"] is False
        assert call_kwargs["selected_action"] == "SPEAK"
        assert call_kwargs["action_rationale"] == "User needs help"

    def test_create_aspdma_result_event_recursive(self):
        """Test creating ASPDMA_RESULT event (recursive)."""
        from ciris_engine.logic.processors.core.step_decorators import _create_aspdma_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.selected_action = "PONDER"
        step_data.action_rationale = "Need more context"

        mock_create = Mock(return_value="recursive_event")

        result = _create_aspdma_result_event(step_data, "2025-01-01T12:00:00Z", True, mock_create)

        assert result == "recursive_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["is_recursive"] is True

    def test_create_conscience_result_event_passed(self):
        """Test creating CONSCIENCE_RESULT event when passed."""
        from ciris_engine.logic.processors.core.step_decorators import _create_conscience_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.conscience_passed = True
        step_data.conscience_override_reason = None
        step_data.epistemic_data = {"entropy": 0.3}
        step_data.selected_action = "SPEAK"

        mock_create = Mock(return_value="conscience_event")

        result = _create_conscience_result_event(step_data, "2025-01-01T12:00:00Z", mock_create)

        assert result == "conscience_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["is_recursive"] is False  # FINALIZE_ACTION never recursive
        assert call_kwargs["conscience_passed"] is True
        assert call_kwargs["action_was_overridden"] is False

    def test_create_conscience_result_event_failed(self):
        """Test creating CONSCIENCE_RESULT event when failed."""
        from ciris_engine.logic.processors.core.step_decorators import _create_conscience_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.conscience_passed = False
        step_data.conscience_override_reason = "Safety concern"
        step_data.epistemic_data = {"entropy": 0.8}
        step_data.selected_action = "DEFER"

        mock_create = Mock(return_value="failed_event")

        result = _create_conscience_result_event(step_data, "2025-01-01T12:00:00Z", mock_create)

        assert result == "failed_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["conscience_passed"] is False
        assert call_kwargs["action_was_overridden"] is True
        assert call_kwargs["conscience_override_reason"] == "Safety concern"

    def test_create_action_result_event_with_follow_up(self):
        """Test creating ACTION_RESULT event with follow-up."""
        from ciris_engine.logic.processors.core.step_decorators import _create_action_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.action_executed = "SPEAK"
        step_data.dispatch_success = True
        step_data.execution_time_ms = 125.5
        step_data.follow_up_thought_id = "thought_next"  # Now on step_data
        step_data.audit_entry_id = "audit_789"
        step_data.audit_sequence_number = 42
        step_data.audit_entry_hash = "hash_abc"
        step_data.audit_signature = "sig_xyz"

        # Result dict (no longer used for follow_up_thought_id)
        result = {"action_type": "SPEAK"}

        mock_create = Mock(return_value="action_event")

        event = _create_action_result_event(step_data, "2025-01-01T12:00:00Z", mock_create)

        assert event == "action_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["action_executed"] == "SPEAK"
        assert call_kwargs["execution_success"] is True
        assert call_kwargs["follow_up_thought_id"] == "thought_next"
        assert call_kwargs["audit_entry_id"] == "audit_789"

    def test_create_action_result_event_terminal_action(self):
        """Test creating ACTION_RESULT event for terminal action (no follow-up)."""
        from ciris_engine.logic.processors.core.step_decorators import _create_action_result_event

        step_data = Mock()
        step_data.thought_id = "thought_123"
        step_data.task_id = "task_456"
        step_data.action_executed = "TASK_COMPLETE"
        step_data.dispatch_success = True
        step_data.execution_time_ms = 50.0
        step_data.follow_up_thought_id = None  # Terminal action = no follow-up
        step_data.audit_entry_id = None
        step_data.audit_sequence_number = None
        step_data.audit_entry_hash = None
        step_data.audit_signature = None

        # Terminal action - result dict
        result = {"action_type": "TASK_COMPLETE"}

        mock_create = Mock(return_value="terminal_event")

        event = _create_action_result_event(step_data, "2025-01-01T12:00:00Z", mock_create)

        assert event == "terminal_event"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["follow_up_thought_id"] is None  # Terminal action = no follow-up


class TestIntegrationRefactoredFunctions:
    """Integration tests for refactored high-complexity functions."""

    def test_create_perform_aspdma_data_integration(self):
        """Test _create_perform_aspdma_data with real data."""
        base_data = BaseStepData(
            thought_id="thought_123",
            task_id="task_456",
            timestamp="2025-01-01T12:00:00Z",
            processing_time_ms=100.0,
            success=True,
        )

        result = Mock()
        result.selected_action = "SPEAK"
        result.rationale = "User needs information"

        dma_results = Mock()
        dma_results.csdma = "common_sense_ok"
        dma_results.dsdma = "domain_ok"

        args = ("context", dma_results)

        step_data = _create_perform_aspdma_data(base_data, result, args)

        assert step_data.thought_id == "thought_123"
        assert step_data.selected_action == "SPEAK"
        assert step_data.action_rationale == "User needs information"
        assert "csdma: common_sense_ok" in step_data.dma_results
        assert "dsdma: domain_ok" in step_data.dma_results

    def test_create_comprehensive_conscience_result_integration_passed(self):
        """Test _create_comprehensive_conscience_result when conscience passes."""
        result = Mock()
        result.overridden = False
        result.override_reason = None
        result.original_action = Mock()
        result.original_action.model_dump = Mock(return_value={"selected_action": "SPEAK"})
        result.final_action = Mock()
        result.final_action.model_dump = Mock(return_value={"selected_action": "SPEAK"})
        result.thought_depth_triggered = None
        result.updated_status_detected = None

        conscience_result = _create_comprehensive_conscience_result(result)

        assert conscience_result.passed is True
        assert conscience_result.reason is None
        assert conscience_result.entropy_check.passed is True
        assert conscience_result.coherence_check.passed is True
        assert conscience_result.optimization_veto_check.decision == "proceed"
        assert conscience_result.epistemic_humility_check.recommended_action == "proceed"
        assert conscience_result.original_action == {"selected_action": "SPEAK"}
        assert conscience_result.replacement_action is None
        assert conscience_result.thought_depth_triggered is None
        assert conscience_result.updated_status_detected is None

    def test_create_comprehensive_conscience_result_integration_failed(self):
        """Test _create_comprehensive_conscience_result when conscience fails."""
        result = Mock()
        result.overridden = True
        result.override_reason = "Safety violation detected"
        result.original_action = Mock()
        result.original_action.model_dump = Mock(return_value={"selected_action": "SPEAK"})
        result.final_action = Mock()
        result.final_action.model_dump = Mock(return_value={"selected_action": "DEFER"})
        result.thought_depth_triggered = True
        result.updated_status_detected = False

        conscience_result = _create_comprehensive_conscience_result(result)

        assert conscience_result.passed is False
        assert conscience_result.reason == "Safety violation detected"
        assert conscience_result.entropy_check.passed is False
        assert conscience_result.coherence_check.passed is False
        assert conscience_result.optimization_veto_check.decision == "abort"
        assert conscience_result.epistemic_humility_check.recommended_action == "ponder"
        assert conscience_result.original_action == {"selected_action": "SPEAK"}
        assert conscience_result.replacement_action == {"selected_action": "DEFER"}
        assert conscience_result.thought_depth_triggered is True
        assert conscience_result.updated_status_detected is False

    def test_create_recursive_aspdma_data_integration(self, base_step_data, mock_aspdma_result):
        """Test _create_recursive_aspdma_data with retry reason."""
        args = ("Need to gather more information",)
        step_data = _create_recursive_aspdma_data(base_step_data, mock_aspdma_result, args)

        assert step_data.thought_id == "thought_123"
        assert step_data.original_action == "PONDER"
        assert step_data.retry_reason == "Need to gather more information"

    def test_create_recursive_conscience_data_integration(self, base_step_data, mock_conscience_result_passed):
        """Test _create_recursive_conscience_data."""
        step_data = _create_recursive_conscience_data(base_step_data, mock_conscience_result_passed)

        assert step_data.thought_id == "thought_123"
        assert step_data.retry_action == "SPEAK"
        assert step_data.retry_result == "passed"

    def test_create_finalize_action_data_integration(self, base_step_data, mock_conscience_result_passed):
        """Test _create_finalize_action_data."""
        step_data = _create_finalize_action_data(base_step_data, mock_conscience_result_passed)

        assert step_data.thought_id == "thought_123"
        assert step_data.conscience_passed is True
        assert step_data.selected_action == "SPEAK"

    def test_create_perform_action_data_integration(self, base_step_data):
        """Test _create_perform_action_data."""
        # Create mock with selected_action for PERFORM_ACTION step
        mock_result = Mock()
        mock_result.selected_action = "SPEAK"

        step_data = _create_perform_action_data(base_step_data, mock_result, args=(), kwargs={})

        assert step_data.thought_id == "thought_123"
        assert step_data.selected_action == "SPEAK"

    def test_create_action_complete_data_integration_dict(self, base_step_data):
        """Test _create_action_complete_data expects ActionResponse, not dict."""
        from ciris_engine.schemas.services.runtime_control import ActionResponse
        from ciris_engine.schemas.audit.hash_chain import AuditEntryResult

        # Create ActionResponse with audit data
        audit_data = AuditEntryResult(
            entry_id="test_123",
            sequence_number=1,
            entry_hash="hash_123",
            signature="sig_123"
        )
        result = ActionResponse(
            action_type="SPEAK",
            success=True,
            handler="speak_handler",
            audit_data=audit_data
        )

        step_data = _create_action_complete_data(base_step_data, result)

        assert step_data.thought_id == "thought_123"
        assert step_data.action_executed == "SPEAK"
        assert step_data.dispatch_success is True
        assert step_data.handler_completed is True

    def test_create_action_complete_data_integration_object(self, base_step_data, mock_action_result):
        """Test _create_action_complete_data with object result."""
        step_data = _create_action_complete_data(base_step_data, mock_action_result)

        assert step_data.thought_id == "thought_123"
        assert step_data.action_executed == "SPEAK"
        assert step_data.dispatch_success is True
