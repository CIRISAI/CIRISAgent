"""`full_traces` must refuse loudly rather than persist nothing.

THE BUG IT GUARDS (CIRISServer#418). The agent constructs persist's Engine from
Python with `scrubber=None`, which persist fills in with `NullScrubber` — it
redacts nothing and honestly reports `ner_ran: false`. persist v32.1.0 turned
that combination into a hard rejection at `full_traces`:

    ValueError: ('scrub_treatment_mismatch', 'label=full_traces treated_as=full_traces')

Every batch refused. Zero traces persisted. `detailed` — what production runs —
still passes with a warning, which is why this is scoped to one opt-in setting
rather than being a release blocker.

WHY REFUSE INSTEAD OF DOWNGRADE. Silently applying `detailed` when the user
asked for `full_traces` would leave the UI showing a level the agent is not
using. Refusing is the only option that cannot be misread.

WHY PROBE, NOT VERSION-COMPARE. `egress_scrub` existing is precisely the
condition that makes `full_traces` safe. Pinning a version number would mean
editing this guard again on the exact release that fixes the problem, and
getting that edit wrong reintroduces silent total trace loss.
"""

from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes import my_data


class _Metrics:
    _trace_level = None


class _Adapter:
    metrics_service = _Metrics()


@pytest.fixture
def adapter() -> _Adapter:
    return _Adapter()


def _fake_substrate(monkeypatch: pytest.MonkeyPatch, *, has_scrub: bool) -> None:
    mod = types.ModuleType("ciris_server")
    if has_scrub:
        mod.egress_scrub = lambda *a, **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", mod)


def test_full_traces_is_refused_without_a_scrubber(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter
) -> None:
    _fake_substrate(monkeypatch, has_scrub=False)

    with pytest.raises(HTTPException) as exc:
        my_data._apply_trace_level_change(adapter, "full_traces")

    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    # The message must say what happens if we DIDN'T refuse, or the user will
    # read it as an arbitrary restriction and go looking for a flag.
    assert "stop trace persistence" in detail
    assert "detailed" in detail
    assert "CIRISServer#418" in detail


def test_the_refusal_does_not_half_apply_the_change(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter
) -> None:
    """A rejected request must leave the adapter exactly as it was."""
    _fake_substrate(monkeypatch, has_scrub=False)
    adapter.metrics_service._trace_level = "detailed"

    with pytest.raises(HTTPException):
        my_data._apply_trace_level_change(adapter, "full_traces")

    assert adapter.metrics_service._trace_level == "detailed"


def test_full_traces_is_allowed_once_the_agent_INSTALLS_a_scrubber(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter
) -> None:
    """The gate is what the AGENT wires, not what the substrate offers.

    This test used to fake a `ciris_server` module carrying `egress_scrub` and
    expect the guard to lift. That encoded the bug: from 0.5.174 the binding
    exists on every supported pin, so a substrate-capability probe answers True
    while the agent still builds `Engine(scrubber=None)` — persist installs
    NullScrubber and full_traces is refused. A dependency bump would have
    silently disabled the guard.

    So the seam is now `substrate_can_scrub()`, which reports whether WE install
    a scrubber, and this patches that.
    """
    import ciris_engine.logic.utils.substrate_caps as caps

    monkeypatch.setattr(caps, "_AGENT_INSTALLS_SCRUBBER", True, raising=True)

    my_data._apply_trace_level_change(adapter, "full_traces")

    assert adapter.metrics_service._trace_level.value == "full_traces"


def test_a_substrate_binding_alone_does_NOT_lift_the_guard(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter
) -> None:
    """The regression this file now exists to prevent.

    A `ciris_server` exposing `egress_scrub` must NOT be enough. Until the agent
    passes it to the Engine, nothing is redacted, and full_traces would be
    refused by persist with scrub_treatment_mismatch.
    """
    import sys
    import types

    mod = types.ModuleType("ciris_server")
    mod.egress_scrub = lambda *a, **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", mod)

    with pytest.raises(HTTPException) as exc:
        my_data._apply_trace_level_change(adapter, "full_traces")

    assert exc.value.status_code == 400


@pytest.mark.parametrize("level", ["generic", "detailed"])
def test_the_unaffected_levels_are_untouched(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter, level: str
) -> None:
    """`detailed` is what production runs; it passes persist's check unchanged."""
    _fake_substrate(monkeypatch, has_scrub=False)

    my_data._apply_trace_level_change(adapter, level)

    assert adapter.metrics_service._trace_level.value == level


def test_an_unknown_level_still_400s(monkeypatch: pytest.MonkeyPatch, adapter: _Adapter) -> None:
    """The pre-existing validation must survive the new branch above it."""
    _fake_substrate(monkeypatch, has_scrub=False)

    with pytest.raises(HTTPException) as exc:
        my_data._apply_trace_level_change(adapter, "sideways")

    assert exc.value.status_code == 400
    assert "Invalid trace_level" in str(exc.value.detail)


def test_an_unimportable_substrate_is_treated_as_cannot_scrub(
    monkeypatch: pytest.MonkeyPatch, adapter: _Adapter
) -> None:
    """Fail closed. An import error is not evidence that scrubbing works."""
    monkeypatch.setitem(sys.modules, "ciris_server", None)  # import raises

    assert my_data._substrate_can_scrub() is False
