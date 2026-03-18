"""Tests for EthicalDMAResult field validators and _coerce_to_string helper.

Tests the validators that handle LLMs returning null/None or arrays
instead of strings (e.g., Kimi K2.5 behavior).
"""

import pytest

from ciris_engine.schemas.dma.results import EthicalDMAResult, _coerce_to_string


class TestCoerceToString:
    """Tests for _coerce_to_string helper function."""

    def test_coerce_none_returns_empty_string(self):
        """None values should be coerced to empty string."""
        assert _coerce_to_string(None) == ""

    def test_coerce_string_unchanged(self):
        """String values should pass through unchanged."""
        assert _coerce_to_string("test value") == "test value"

    def test_coerce_empty_string_unchanged(self):
        """Empty string should remain unchanged."""
        assert _coerce_to_string("") == ""

    def test_coerce_list_joins_with_comma(self):
        """List values should be joined with comma-space separator."""
        result = _coerce_to_string(["item1", "item2", "item3"])
        assert result == "item1, item2, item3"

    def test_coerce_empty_list_returns_empty_string(self):
        """Empty list should return empty string."""
        assert _coerce_to_string([]) == ""

    def test_coerce_list_with_non_strings(self):
        """List with non-string items should be converted to strings."""
        result = _coerce_to_string([1, 2, 3])
        assert result == "1, 2, 3"

    def test_coerce_list_with_mixed_types(self):
        """List with mixed types should be converted properly."""
        result = _coerce_to_string(["hello", 42, True, None])
        assert result == "hello, 42, True, None"

    def test_coerce_integer_to_string(self):
        """Integer values should be converted to string."""
        assert _coerce_to_string(42) == "42"

    def test_coerce_float_to_string(self):
        """Float values should be converted to string."""
        assert _coerce_to_string(3.14) == "3.14"

    def test_coerce_boolean_to_string(self):
        """Boolean values should be converted to string."""
        assert _coerce_to_string(True) == "True"
        assert _coerce_to_string(False) == "False"


class TestEthicalDMAResultValidators:
    """Tests for EthicalDMAResult field validators handling Kimi K2.5 quirks."""

    def test_null_subject_of_evaluation(self):
        """Model should handle null subject_of_evaluation from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation=None,  # type: ignore
            stakeholders="user, system",
            conflicts="none",
            proportionality_assessment="not applicable",
            reasoning="Test reasoning",
            alignment_check="Aligned",
        )
        assert result.subject_of_evaluation == ""

    def test_array_stakeholders(self):
        """Model should handle array stakeholders from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders=["user", "community", "system"],  # type: ignore
            conflicts="none",
            proportionality_assessment="not applicable",
            reasoning="Test reasoning",
            alignment_check="Aligned",
        )
        assert result.stakeholders == "user, community, system"

    def test_array_conflicts(self):
        """Model should handle array conflicts from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders="user, system",
            conflicts=["privacy vs learning", "autonomy vs safety"],  # type: ignore
            proportionality_assessment="not applicable",
            reasoning="Test reasoning",
            alignment_check="Aligned",
        )
        assert result.conflicts == "privacy vs learning, autonomy vs safety"

    def test_null_reasoning(self):
        """Model should handle null reasoning from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders="user",
            conflicts="none",
            proportionality_assessment="not applicable",
            reasoning=None,  # type: ignore
            alignment_check="Aligned",
        )
        assert result.reasoning == ""

    def test_null_alignment_check(self):
        """Model should handle null alignment_check from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders="user",
            conflicts="none",
            proportionality_assessment="not applicable",
            reasoning="Test",
            alignment_check=None,  # type: ignore
        )
        assert result.alignment_check == ""

    def test_null_proportionality_assessment(self):
        """Model should handle null proportionality_assessment from LLM."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders="user",
            conflicts="none",
            proportionality_assessment=None,  # type: ignore
            reasoning="Test",
            alignment_check="Aligned",
        )
        assert result.proportionality_assessment == ""

    def test_all_null_fields(self):
        """Model should handle all fields being null."""
        result = EthicalDMAResult(
            subject_of_evaluation=None,  # type: ignore
            stakeholders=None,  # type: ignore
            conflicts=None,  # type: ignore
            proportionality_assessment=None,  # type: ignore
            reasoning=None,  # type: ignore
            alignment_check=None,  # type: ignore
        )
        assert result.subject_of_evaluation == ""
        assert result.stakeholders == ""
        assert result.conflicts == ""
        assert result.proportionality_assessment == ""
        assert result.reasoning == ""
        assert result.alignment_check == ""

    def test_all_array_fields(self):
        """Model should handle all applicable fields being arrays."""
        result = EthicalDMAResult(
            subject_of_evaluation="OP",
            stakeholders=["user", "admin", "system"],  # type: ignore
            conflicts=["privacy vs learning"],  # type: ignore
            proportionality_assessment="appropriate",
            reasoning=["reason 1", "reason 2"],  # type: ignore
            alignment_check=["check 1", "check 2"],  # type: ignore
        )
        assert result.stakeholders == "user, admin, system"
        assert result.conflicts == "privacy vs learning"
        assert result.reasoning == "reason 1, reason 2"
        assert result.alignment_check == "check 1, check 2"

    def test_normal_string_values_unchanged(self):
        """Normal string values should pass through unchanged."""
        result = EthicalDMAResult(
            subject_of_evaluation="the user asking the question",
            stakeholders="user, community, system",
            conflicts="none",
            proportionality_assessment="not applicable",
            reasoning="This is ethical reasoning",
            alignment_check="Fully aligned with CIRIS principles",
        )
        assert result.subject_of_evaluation == "the user asking the question"
        assert result.stakeholders == "user, community, system"
        assert result.conflicts == "none"
        assert result.proportionality_assessment == "not applicable"
        assert result.reasoning == "This is ethical reasoning"
        assert result.alignment_check == "Fully aligned with CIRIS principles"

    def test_default_values(self):
        """Test that fields with defaults work properly."""
        result = EthicalDMAResult(subject_of_evaluation="OP")
        assert result.subject_of_evaluation == "OP"
        # Check defaults are applied
        assert result.stakeholders == ""
        assert result.conflicts == "none"
        assert result.proportionality_assessment == "not applicable"
        assert result.reasoning == ""
        assert result.alignment_check == ""
