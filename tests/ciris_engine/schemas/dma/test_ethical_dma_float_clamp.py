"""Unit tests for EthicalDMAResult float-range clamping (CIRISAgent#894)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.dma.results import EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType


def _make(**overrides: object) -> EthicalDMAResult:
    base: dict[str, object] = {
        "action": HandlerActionType.SPEAK,
        "rationale": "Principled response.",
        "weight_alignment_score": 0.5,
        "ethical_alignment_score": 0.8,
    }
    base.update(overrides)
    return EthicalDMAResult.model_validate(base)


class TestEthicalDMAResultFloatClamp:
    def test_in_range_values_pass_through_unchanged(self) -> None:
        res = _make(weight_alignment_score=0.0, ethical_alignment_score=1.0)
        assert res.weight_alignment_score == 0.0
        assert res.ethical_alignment_score == 1.0

        mid = _make(weight_alignment_score=0.35, ethical_alignment_score=0.82)
        assert mid.weight_alignment_score == pytest.approx(0.35)
        assert mid.ethical_alignment_score == pytest.approx(0.82)

    def test_out_of_range_high_clamps_to_one(self) -> None:
        res = _make(weight_alignment_score=1.3, ethical_alignment_score=2.5)
        assert res.weight_alignment_score == 1.0
        assert res.ethical_alignment_score == 1.0

    def test_out_of_range_low_clamps_to_zero(self) -> None:
        res = _make(weight_alignment_score=-0.2, ethical_alignment_score=-10.0)
        assert res.weight_alignment_score == 0.0
        assert res.ethical_alignment_score == 0.0

    def test_numeric_string_out_of_range_clamps(self) -> None:
        res = _make(weight_alignment_score="1.15", ethical_alignment_score="-0.05")
        assert res.weight_alignment_score == 1.0
        assert res.ethical_alignment_score == 0.0

    def test_non_finite_and_invalid_values_still_raise(self) -> None:
        with pytest.raises(ValidationError):
            _make(weight_alignment_score=float("nan"))
        with pytest.raises(ValidationError):
            _make(ethical_alignment_score=float("inf"))
        with pytest.raises(ValidationError):
            _make(weight_alignment_score="not-a-number")
