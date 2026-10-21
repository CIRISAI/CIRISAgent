"""#983 — the conscience score-feedback gate (CC 3.4.5 / TORQUE arm D).

The CC read-model review found the retry loop feeds the agent's own numeric
self-scores back into its next action selection: `[IRIS-E] entropy=…`,
`[IRIS-C] coherence=… PASS/FAIL`, thresholds — "use as pivot targets if you
re-SPEAK". For TORQUE's hidden arms that channel must be closable; under a
literal CC 3.4.5 reading it is a self-subject score in the selection loop.

The gate is a MODE, not a removal: `qualitative` drops every number, band,
threshold and judged verdict while keeping the reflection that makes a retry
better (justification, alternatives, uncertainties). Default `full` is
unchanged until the CC 3.4.5 scoping question is settled — the distinction
between within-thought reflection (the safety mechanism working) and a
farmable reputation number is the substrate team's, recorded on #984.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

# Numeric self-score signatures that must never appear in qualitative mode.
_SCORE_RE = re.compile(
    r"entropy=|coherence=|certainty=|threshold=|ratio=|\bPASS\b|\bFAIL\b|representative="
)


def _full_conscience_result() -> MagicMock:
    """A conscience result exercising every shard, scores and reflection both."""
    r = MagicMock()
    r.optimization_veto_check = MagicMock(
        decision="abort",
        entropy_reduction_ratio=3.7,
        affected_values=["autonomy", "dignity"],
        justification="The reply optimises engagement over the user's stated goal.",
    )
    r.entropy_check = MagicMock(
        entropy_score=0.85,
        threshold=0.4,
        actual_is_representative=False,
        alternative_meanings=["Acknowledge the constraint", "Name the tradeoff plainly"],
    )
    r.coherence_check = MagicMock(coherence_score=0.25, threshold=0.6, passed=False)
    r.epistemic_humility_check = MagicMock(
        epistemic_certainty=0.9,
        recommended_action="ponder",
        identified_uncertainties=["user intent ambiguous", "timeline unstated"],
    )
    return r


def _detail(mode: str | None, monkeypatch: pytest.MonkeyPatch) -> str:
    if mode is None:
        monkeypatch.delenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", raising=False)
    else:
        monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", mode)
    tp = ThoughtProcessor.__new__(ThoughtProcessor)  # detail builder needs no init
    return tp._build_structured_shard_detail(_full_conscience_result())


def test_default_mode_is_full_and_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """No env → current behaviour byte-for-byte in shape: scores present.

    Default MUST stay `full` until CC 3.4.5's scoping is settled — silently
    flipping it would change production reasoning behaviour on a research
    question that is still open.
    """
    out = _detail(None, monkeypatch)
    assert "entropy=0.85" in out
    assert "coherence=0.25" in out and "FAIL" in out
    assert "certainty=0.90" in out
    assert "ratio=3.7" in out
    assert "threshold=" in out


def test_qualitative_mode_carries_no_self_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """The arm-D property: zero numeric self-scores, bands, thresholds or
    judged verdicts anywhere in the guidance — checked by pattern over the
    whole output, not by field, so a new score field added to `full` later
    fails THIS test rather than silently leaking."""
    out = _detail("qualitative", monkeypatch)
    hits = _SCORE_RE.findall(out)
    assert not hits, f"self-score signatures leaked into qualitative guidance: {hits}"


def test_qualitative_mode_keeps_the_reflection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate must not lobotomise the conscience loop: justification,
    alternatives, uncertainties and affected values — the content that makes
    a retry materially better — all survive."""
    out = _detail("qualitative", monkeypatch)
    assert "optimises engagement" in out  # veto justification
    assert "Acknowledge the constraint" in out  # entropy alternatives
    assert "user intent ambiguous" in out  # humility uncertainties
    assert "autonomy" in out  # affected values
    assert "recommended=ponder" in out  # a recommendation is not a score


def test_unknown_mode_refuses_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pinned-manifest discipline: a regime that believes it closed this
    channel and typo'd the mode must not run at all."""
    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", "qualatative")  # typo
    tp = ThoughtProcessor.__new__(ThoughtProcessor)
    with pytest.raises(ValueError, match="CIRIS_CONSCIENCE_GUIDANCE_MODE"):
        tp._build_structured_shard_detail(_full_conscience_result())
