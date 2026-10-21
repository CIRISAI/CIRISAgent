"""Lock the H3ERE step-point set as citable evidence (CIRISAgent#911).

`StepPoint` is referenced by the CC evidence registry and, once minted, by a
Constitution claim. A claim is only worth as much as the thing it points at, so
this asserts the two properties a citation actually depends on:

1. **Every member is emitted in production.** A step point with no
   ``@streaming_step`` decorator site is an aspiration, not an observable —
   citing it would be the "declared but zero callers" pattern the registry
   exists to catch.
2. **The docstring does not restate a count that can drift.** The previous
   comment claimed "10 step points" while the enum defined 11, and nothing
   caught it because nothing asserted it. That is the whole failure mode.

Deliberately NOT asserted: the exact number. Pinning 11 here would just move
the hardcoded count from a comment into a test, and adding a legitimate step
point would then read as a regression. What must hold is the *correspondence*
between the enum and the decorated call sites — that is what makes the enum the
source of truth rather than one more place to keep in sync.
"""

from __future__ import annotations

import re
from pathlib import Path

from ciris_engine.schemas.services.runtime_control import StepPoint

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENGINE = _REPO_ROOT / "ciris_engine"


def _decorated_step_points() -> set[str]:
    """Member names appearing as ``@streaming_step(StepPoint.X)`` in production."""
    found: set[str] = set()
    pattern = re.compile(r"@streaming_step\(\s*StepPoint\.([A-Z_]+)")
    for path in _ENGINE.rglob("*.py"):
        try:
            found.update(pattern.findall(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable file
            continue
    return found


def test_every_step_point_has_a_production_emitter() -> None:
    """No member may be citable-but-unemitted."""
    declared = {member.name for member in StepPoint}
    decorated = _decorated_step_points()

    undecorated = declared - decorated
    assert not undecorated, (
        "StepPoint members with no @streaming_step site in ciris_engine/: "
        f"{sorted(undecorated)}. Either wire the emitter or remove the member — "
        "an unemitted step point cannot be cited as evidence."
    )


def test_no_decorator_references_an_unknown_step_point() -> None:
    """The reverse direction: a decorator naming a member that no longer exists."""
    declared = {member.name for member in StepPoint}
    unknown = _decorated_step_points() - declared
    assert not unknown, f"@streaming_step references non-existent StepPoint members: {sorted(unknown)}"


def test_docstring_does_not_hardcode_a_step_point_count() -> None:
    """Guard the specific rot this test was written for.

    A prose count in the docstring drifts silently the moment a member is added.
    The enum itself is the source of truth; the docstring must not compete
    with it by restating a number of step points.
    """
    doc = StepPoint.__doc__ or ""
    offenders = re.findall(r"\b(\d+)\s+step\s+points\b", doc, flags=re.IGNORECASE)
    assert not offenders, (
        f"StepPoint docstring hardcodes a step-point count ({offenders}). "
        "Describe the set and let the enum be the source of truth — a restated "
        "count is what previously read '10' while the enum defined 11."
    )


def test_step_values_are_stable_snake_case_tags() -> None:
    """Values are the on-the-wire tags; they must stay predictable to consumers."""
    for member in StepPoint:
        assert member.value == member.name.lower(), (
            f"{member.name} has wire tag {member.value!r}; consumers (clients, lens "
            "traces, Constitution citations) rely on the lowercase-name convention."
        )
