"""Tests for DMA bounce in DMAOrchestrator.

The bounce gate sits inside DMAOrchestrator.run_initial_dmas: after the
three initial DMAs complete, any DMA that scored below threshold gets
re-run BOUNCE_PARALLELISM times in parallel with a composite preamble that
mentions all low scores in priority order. The highest-scoring alternative
replaces the original result if it clears threshold; otherwise the original
is preserved and a difficulty rationale is attached for ASPDMA.

These tests cover:
- no-trigger: every DMA above threshold → no bounce, no summary
- single-DMA trigger (CSDMA only): one alternative passes → swap
- single-DMA trigger (CSDMA only): all alternatives fail → exhausted
- composite trigger (CSDMA + DSDMA): preamble lists both, both bounce
- selection: highest of 3 alternatives wins
- preamble priority order: CSDMA listed before DSDMA per BOUNCE_PRIORITY
- the bounced thought item still carries the original thought_id/depth
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
from ciris_engine.schemas.dma.bounce import (
    BOUNCE_FIELD,
    BOUNCE_PARALLELISM,
    BOUNCE_PRIORITY,
    BOUNCE_THRESHOLD,
)
from ciris_engine.schemas.dma.results import CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.processors.dma import DMAMetadata


def _csdma(score: float, reasoning: str = "rsn") -> CSDMAResult:
    return CSDMAResult(plausibility_score=score, flags=[], reasoning=reasoning)


def _dsdma(score: float, reasoning: str = "rsn") -> DSDMAResult:
    return DSDMAResult(domain="general", domain_alignment=score, flags=[], reasoning=reasoning)


def _ethical() -> EthicalDMAResult:
    return EthicalDMAResult(stakeholders="user", conflicts="none", reasoning="ok", alignment_check="ok")


# ───────────────────────────── pure helpers ──────────────────────────────


class TestBounceablesScore:
    def test_csdma_score_extracted(self, dma_orchestrator):
        assert DMAOrchestrator._bounceable_score("csdma", _csdma(0.42)) == 0.42

    def test_dsdma_score_extracted(self, dma_orchestrator):
        assert DMAOrchestrator._bounceable_score("dsdma", _dsdma(0.91)) == 0.91

    def test_ethical_pdma_returns_none_until_alignment_score_lands(self, dma_orchestrator):
        # PDMA bounce is gated on EthicalDMAResult.alignment_score being added.
        # Until then the score must read as None so the bounce gate skips PDMA.
        assert DMAOrchestrator._bounceable_score("ethical_pdma", _ethical()) is None

    def test_unknown_dma_returns_none(self, dma_orchestrator):
        assert DMAOrchestrator._bounceable_score("idma", MagicMock()) is None


class TestComposePreamble:
    def test_single_trigger_mentions_score_and_threshold(self):
        preamble = DMAOrchestrator._build_composite_preamble(
            [("csdma", 0.10, 0.5)]
        )
        assert "CSDMA plausibility_score = 0.10" in preamble
        assert "threshold 0.50" in preamble
        assert "[ORIGINAL THOUGHT FOLLOWS]" in preamble
        # Must invite a "no alternative exists" out so the model can produce a
        # difficulty rationale rather than a fake substantive answer.
        assert "no principled alternative" in preamble

    def test_composite_lists_in_priority_order(self):
        # If both CSDMA and DSDMA trigger, CSDMA appears before DSDMA per
        # BOUNCE_PRIORITY (PDMA > CSDMA > DSDMA).
        preamble = DMAOrchestrator._build_composite_preamble(
            [("csdma", 0.10, 0.5), ("dsdma", 0.20, 0.5)]
        )
        csdma_idx = preamble.index("CSDMA")
        dsdma_idx = preamble.index("DSDMA")
        assert csdma_idx < dsdma_idx

    def test_preamble_localizes_per_lang_code(self):
        # The bounce preamble must localize to the agent's working language.
        # DMA names, field names, scores, and threshold values stay literal
        # (they're inside `{}` placeholders the model needs to parse).
        en_preamble = DMAOrchestrator._build_composite_preamble(
            [("csdma", 0.10, 0.5)], lang="en"
        )
        zh_preamble = DMAOrchestrator._build_composite_preamble(
            [("csdma", 0.10, 0.5)], lang="zh"
        )
        # Different languages must produce different headers …
        assert en_preamble != zh_preamble
        # … but technical fields stay identical (DMA name + score + threshold).
        for must_appear in ("CSDMA", "plausibility_score", "0.10", "0.50"):
            assert must_appear in en_preamble, must_appear
            assert must_appear in zh_preamble, must_appear


class TestMakeBounceThoughtItem:
    def test_preamble_prepended_to_content(self, sample_thought_item):
        bounced = DMAOrchestrator._make_bounce_thought_item(
            sample_thought_item, preamble="[BOUNCE PREAMBLE]"
        )
        assert bounced.content.text.startswith("[BOUNCE PREAMBLE]")
        # Original content must still appear in the bounced thought.
        assert sample_thought_item.content.text in bounced.content.text

    def test_identity_fields_preserved(self, sample_thought_item):
        bounced = DMAOrchestrator._make_bounce_thought_item(
            sample_thought_item, preamble="[BOUNCE]"
        )
        # thought_id, source_task_id, thought_depth must NOT change — the bounce
        # is the same logical thought with augmented prompt context. Downstream
        # instrumentation (tracing, telemetry) must report the same identity.
        assert bounced.thought_id == sample_thought_item.thought_id
        assert bounced.source_task_id == sample_thought_item.source_task_id
        assert bounced.thought_depth == sample_thought_item.thought_depth


# ───────────────────────── _maybe_bounce_dmas integration ────────────────


@pytest.mark.asyncio
class TestMaybeBounceDmas:
    async def test_no_trigger_when_all_scores_above_threshold(
        self, dma_orchestrator, sample_thought_item, sample_processing_context
    ):
        results = {
            "ethical_pdma": _ethical(),
            "csdma": _csdma(0.95),
            "dsdma": _dsdma(0.85),
        }
        summary = await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert summary is None
        # Original results must be untouched.
        assert results["csdma"].plausibility_score == 0.95
        assert results["dsdma"].domain_alignment == 0.85

    async def test_csdma_only_resolves_when_alternative_passes(
        self, dma_orchestrator, sample_thought_item, sample_processing_context, monkeypatch
    ):
        # Original CSDMA scored 0.10 (below 0.5). Three alternatives score
        # 0.30, 0.65, 0.55. Best (0.65) must replace the original.
        alt_scores = iter([0.30, 0.65, 0.55])

        async def fake_csdma_call(*args, **kwargs):
            return _csdma(next(alt_scores))

        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_csdma",
            AsyncMock(side_effect=fake_csdma_call),
        )

        results = {
            "ethical_pdma": _ethical(),
            "csdma": _csdma(0.10),
            "dsdma": _dsdma(0.85),
        }
        summary = await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert summary is not None
        assert summary.triggered_dmas == ["csdma"]
        assert len(summary.records) == 1
        rec = summary.records[0]
        assert rec.dma == "csdma"
        assert rec.original_score == 0.10
        assert rec.exhausted is False
        assert rec.final_score == 0.65
        # The orchestrator swapped the alternative into dma_results in place.
        assert results["csdma"].plausibility_score == 0.65
        # difficulty rationale should be empty when nothing exhausted.
        assert summary.difficulty_rationale is None
        assert summary.fully_resolved is True

    async def test_csdma_exhausted_passes_highest_alternative_with_advisory(
        self, dma_orchestrator, sample_thought_item, sample_processing_context, monkeypatch
    ):
        # All three alternatives stay below 0.5 (0.10, 0.30, 0.20). The
        # exhausted flag must fire AND the highest alternative (0.30) must
        # flow forward — bounce never downgrades to the original.
        alt_scores = iter([0.10, 0.30, 0.20])

        async def fake_csdma_call(*args, **kwargs):
            return _csdma(next(alt_scores), reasoning="model is uncertain because X is hard")

        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_csdma",
            AsyncMock(side_effect=fake_csdma_call),
        )

        original = _csdma(0.05)
        results = {
            "ethical_pdma": _ethical(),
            "csdma": original,
            "dsdma": _dsdma(0.85),
        }
        summary = await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert summary is not None
        rec = summary.records[0]
        assert rec.exhausted is True
        # Highest alternative (0.30) replaces original (0.05) even though it
        # didn't clear threshold. ASPDMA gets the better attempt + advisory.
        assert results["csdma"] is not original
        assert results["csdma"].plausibility_score == 0.30
        assert rec.final_score == 0.30
        # Difficulty rationale must be populated from the alternative reasoning.
        assert summary.difficulty_rationale is not None
        assert "csdma" in summary.difficulty_rationale
        assert summary.any_exhausted is True
        assert summary.fully_resolved is False

    async def test_all_alternatives_error_keeps_original(
        self, dma_orchestrator, sample_thought_item, sample_processing_context, monkeypatch
    ):
        # If every alternative raises, the original must be preserved as a
        # last-resort fallback so the pipeline always has a result.
        async def fake_csdma_call(*args, **kwargs):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_csdma",
            AsyncMock(side_effect=fake_csdma_call),
        )

        original = _csdma(0.05)
        results = {
            "ethical_pdma": _ethical(),
            "csdma": original,
            "dsdma": _dsdma(0.85),
        }
        summary = await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert results["csdma"] is original
        rec = summary.records[0]
        assert rec.exhausted is True
        assert rec.chosen_attempt_index is None
        assert rec.attempts == []

    async def test_composite_bounce_runs_both_csdma_and_dsdma(
        self, dma_orchestrator, sample_thought_item, sample_processing_context, monkeypatch
    ):
        # Both DMAs trigger. CSDMA alternatives pass, DSDMA exhausts.
        csdma_scores = iter([0.60, 0.70, 0.55])
        dsdma_scores = iter([0.10, 0.20, 0.15])

        async def fake_csdma_call(*args, **kwargs):
            return _csdma(next(csdma_scores))

        async def fake_dsdma_call(*args, **kwargs):
            return _dsdma(next(dsdma_scores), reasoning="domain mismatch")

        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_csdma",
            AsyncMock(side_effect=fake_csdma_call),
        )
        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_dsdma",
            AsyncMock(side_effect=fake_dsdma_call),
        )

        original_dsdma = _dsdma(0.20)
        results = {
            "ethical_pdma": _ethical(),
            "csdma": _csdma(0.10),
            "dsdma": original_dsdma,
        }
        summary = await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert summary is not None
        assert summary.triggered_dmas == ["csdma", "dsdma"]
        # Composite preamble lists both DMAs in priority order.
        assert "CSDMA" in summary.composite_preamble
        assert "DSDMA" in summary.composite_preamble
        assert summary.composite_preamble.index("CSDMA") < summary.composite_preamble.index("DSDMA")

        # CSDMA: best alternative (0.70) replaces original.
        csdma_rec = next(r for r in summary.records if r.dma == "csdma")
        assert csdma_rec.exhausted is False
        assert csdma_rec.final_score == 0.70
        assert results["csdma"].plausibility_score == 0.70

        # DSDMA: all alternatives below threshold → exhausted, but the highest
        # alternative (0.20) still replaces the original. Advisory fires.
        dsdma_rec = next(r for r in summary.records if r.dma == "dsdma")
        assert dsdma_rec.exhausted is True
        assert results["dsdma"] is not original_dsdma
        assert results["dsdma"].domain_alignment == 0.20
        assert dsdma_rec.final_score == 0.20
        assert "dsdma" in summary.difficulty_rationale

    async def test_each_bounce_runs_exactly_BOUNCE_PARALLELISM_alternatives(
        self, dma_orchestrator, sample_thought_item, sample_processing_context, monkeypatch
    ):
        call_count = {"csdma": 0}

        async def fake_csdma_call(*args, **kwargs):
            call_count["csdma"] += 1
            return _csdma(0.10)

        monkeypatch.setattr(
            "ciris_engine.logic.processors.support.dma_orchestrator.run_csdma",
            AsyncMock(side_effect=fake_csdma_call),
        )

        results = {
            "ethical_pdma": _ethical(),
            "csdma": _csdma(0.10),
            "dsdma": _dsdma(0.85),
        }
        await dma_orchestrator._maybe_bounce_dmas(
            thought_item=sample_thought_item,
            processing_context=sample_processing_context,
            dsdma_context=DMAMetadata(),
            dma_results=results,
        )
        assert call_count["csdma"] == BOUNCE_PARALLELISM


# ───────────────────────── module-level constants ────────────────────────


class TestBounceConstants:
    def test_priority_is_pdma_csdma_dsdma(self):
        # Priority order matters for composite preamble framing.
        # PDMA (ethics) leads, then CSDMA (common sense), then DSDMA (domain).
        assert BOUNCE_PRIORITY == ("ethical_pdma", "csdma", "dsdma")

    def test_thresholds_are_half(self):
        # 0.5 is the principled split between filter-engaged (~0) and
        # substantive (~0.95+) DMA self-ratings observed in production traces.
        assert BOUNCE_THRESHOLD["csdma"] == 0.5
        assert BOUNCE_THRESHOLD["dsdma"] == 0.5
        assert BOUNCE_THRESHOLD["ethical_pdma"] == 0.5

    def test_field_per_dma(self):
        assert BOUNCE_FIELD["csdma"] == "plausibility_score"
        assert BOUNCE_FIELD["dsdma"] == "domain_alignment"
        # PDMA field is reserved for the future EthicalDMAResult.alignment_score
        # field; until that lands, the bounce gate skips PDMA via the score
        # extractor returning None.
        assert BOUNCE_FIELD["ethical_pdma"] == "alignment_score"

    def test_parallelism_is_three(self):
        assert BOUNCE_PARALLELISM == 3
