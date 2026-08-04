"""#986: the #983 mode must be auditable FROM THE ARTIFACT, never from intention.

The research team's gate audit found `CIRIS_CONSCIENCE_GUIDANCE_MODE` was read
at the retry site and recorded nowhere — not the trace, not the CEG seal, not
the dump. TORQUE arm D's void condition is *"trace audit finds torque-reading
leakage into a hidden arm"*, and **an audit cannot read an environment variable
that left no trace**: arm assignment would rest on operator intention, the same
defect CAPTURE_2_9_7.md flags.

Three surfaces must therefore agree, from one source of truth:
  1. the guidance builder (behaviour),
  2. the accord-metrics component header (trace + CEG seal),
  3. the compose-dump meta line (the gate's own artifact).
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.utils.conscience_mode import VALID_MODES, conscience_guidance_mode


@pytest.mark.parametrize("mode", VALID_MODES)
def test_util_reports_each_valid_mode(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", mode)
    assert conscience_guidance_mode() == mode


def test_util_defaults_to_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", raising=False)
    assert conscience_guidance_mode() == "full"


def test_util_refuses_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", "qualatative")
    with pytest.raises(ValueError, match="CIRIS_CONSCIENCE_GUIDANCE_MODE"):
        conscience_guidance_mode()


def test_processor_and_util_are_one_source_of_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    """The builder must not carry its own copy of the env read — two readers
    drift, and a drifted pair means the trace records a mode the behaviour did
    not use, which is worse than recording nothing."""
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", "qualitative")
    tp = ThoughtProcessor.__new__(ThoughtProcessor)
    assert tp._conscience_guidance_mode() == conscience_guidance_mode() == "qualitative"


@pytest.mark.parametrize("mode", VALID_MODES)
def test_batch_component_records_the_mode(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every shipped trace component (and therefore every CEG seal built from
    one) carries the mode — this is the line an arm-D auditor reads."""
    from ciris_adapters.ciris_accord_metrics.services import _conscience_guidance_mode_for_batch

    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", mode)
    assert _conscience_guidance_mode_for_batch() == mode


def test_batch_records_invalidity_rather_than_dropping_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-open at the RECORDING site, fail-closed at the USE site.

    The guidance builder refuses an invalid mode (the run stops), so a batch
    assembled in that window still ships — carrying an INVALID: marker, which
    is strictly more auditable than a dropped batch or a silent default.
    """
    from ciris_adapters.ciris_accord_metrics.services import _conscience_guidance_mode_for_batch

    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", "nonsense")
    assert _conscience_guidance_mode_for_batch() == "INVALID:nonsense"


@pytest.mark.parametrize("mode", VALID_MODES)
def test_dump_meta_pins_the_mode(mode: str, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The gate's own artifact records which side of CC 3.4.5 it composed under,
    so a regime's dumps cannot be attributed to the wrong arm after the fact."""
    from ciris_engine.logic.utils.compose_dump import _conscience_mode_for_dump

    monkeypatch.setenv("CIRIS_CONSCIENCE_GUIDANCE_MODE", mode)
    assert _conscience_mode_for_dump() == mode


def test_dump_meta_schema_carries_the_field() -> None:
    from ciris_engine.schemas.dma.compose import ComposeDumpMeta

    assert "conscience_guidance_mode" in ComposeDumpMeta.model_fields
