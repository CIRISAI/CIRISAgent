"""A full_traces adapter must not be registered against a substrate that rejects it.

WHAT THIS CAUGHT. Staged QA on 2.9.18, 82/82 tests passing and still exit 1:

    RuntimeError: engine.receive_and_persist:
      ValueError: ('scrub_treatment_mismatch', 'label=full_traces ...')   x10

The agent builds persist's Engine with `scrubber=None`; persist substitutes
`NullScrubber`, which redacts nothing and reports `ner_ran: false`. From persist
v32.1.0 that pairing is a hard rejection at `full_traces` — every batch refused,
ZERO traces persisted (CIRISServer#418). `detailed`, production's level, still
passes, which is why this is scoped to one level.

WHY THE EXISTING GUARD MISSED IT. `PATCH /v1/my-data/accord-settings` was already
guarded, but staged QA never uses it: it boots at `detailed` and then explicitly
REGISTERS a second full_traces adapter after auth, by design, to collect raw
prompts+completions for the fine-tuning corpus. That path reads config/env and
never touches the route.

WHY DOWNGRADE HERE BUT REFUSE THERE. This is bootstrap config, not an interactive
request. Refusing would fail adapter registration and take the run down over a
level nobody asked for at runtime. It also mirrors what the substrate does on its
own supported path — persist's `EgressScrubber` downgrades FullTraces -> Detailed
when `!ner::is_configured()`. On the interactive route a silent downgrade would
show the user a level the agent is not actually using, so that one still refuses.
"""

from __future__ import annotations

import pytest

from ciris_adapters.ciris_accord_metrics.services import TraceDetailLevel


@pytest.fixture
def levels(monkeypatch: pytest.MonkeyPatch):
    """Drive the resolver directly: (requested, can_scrub) -> effective."""
    import ciris_adapters.ciris_accord_metrics.services as svc

    def resolve(requested: str, can_scrub: bool) -> TraceDetailLevel:
        monkeypatch.setattr(svc, "substrate_can_scrub", lambda: can_scrub, raising=True)
        level = TraceDetailLevel(requested)
        if level == TraceDetailLevel.FULL_TRACES and not svc.substrate_can_scrub():
            return TraceDetailLevel.DETAILED
        return level

    return resolve


def test_full_traces_downgrades_when_the_substrate_cannot_scrub(levels) -> None:
    """The bug: this combination persisted nothing at all."""
    assert levels("full_traces", False) == TraceDetailLevel.DETAILED


def test_full_traces_is_honoured_once_the_substrate_can_scrub(levels) -> None:
    """Lifts itself on 0.5.174 — no second edit needed."""
    assert levels("full_traces", True) == TraceDetailLevel.FULL_TRACES


@pytest.mark.parametrize("level", ["generic", "detailed"])
@pytest.mark.parametrize("can_scrub", [True, False])
def test_the_other_levels_are_never_touched(levels, level: str, can_scrub: bool) -> None:
    """`detailed` is what production runs; it passes persist's check unchanged."""
    assert levels(level, can_scrub).value == level


def test_the_probe_fails_closed() -> None:
    """An unimportable substrate is not evidence that scrubbing works."""
    import sys

    import ciris_engine.logic.utils.substrate_caps as caps

    real = sys.modules.get("ciris_server")
    sys.modules["ciris_server"] = None  # type: ignore[assignment]
    try:
        assert caps.substrate_can_scrub() is False
    finally:
        if real is not None:
            sys.modules["ciris_server"] = real
        else:
            sys.modules.pop("ciris_server", None)


def test_the_downgrade_is_announced_not_silent() -> None:
    """An operator who asked for full_traces must be told they are not getting it.

    Silence here would look exactly like the bug it replaces: traces arriving at
    a lower detail than configured, with nothing in the log to explain why.
    """
    import inspect

    import ciris_adapters.ciris_accord_metrics.services as svc

    src = inspect.getsource(svc.AccordMetricsService.__init__)
    guard = src[src.index("FULL_TRACES and not substrate_can_scrub") :][:900]
    assert "logger.warning" in guard, "the downgrade must be logged at WARNING"
    assert "CIRISServer#418" in guard, "the message must name the upstream cause"
