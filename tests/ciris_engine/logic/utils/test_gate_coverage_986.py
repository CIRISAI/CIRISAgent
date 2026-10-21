"""The ablation gate's REACH is itself a regression target (#986).

``compose_dump gate`` compares two dumps block-by-block. Its verdict only
constrains an override key if replacing that key MOVES a block — a key that
moves nothing can be varied by a regime while the gate still prints
``GATE: PASS``. ``tools/research/probe_gate_coverage`` measures that reach per
key; the floors it carries (``GATED_FLOOR``) are the lock.

Where the lock actually runs
----------------------------
The full sweep composes the whole pipeline once per override key — 100+
subprocesses. That does not belong inside the sharded unit-test run (60s
per-test timeout, four xdist workers already competing for the box), so the
enforcing run lives in the **compose-gate CI job**, which is this instrument's
own workflow and has the budget::

    python3 -m tools.research.probe_gate_coverage --assert-floors

What lives HERE is (a) the cheap structural guarantees, which must hold on every
commit, and (b) the same sweep behind an opt-in for local work::

    CIRIS_RUN_GATE_COVERAGE_PROBE=1 pytest tests/ciris_engine/logic/utils/test_gate_coverage_986.py

Floors are deliberately NOT duplicated here — they are imported, so the CI gate
and this test can never disagree about the number being defended.
"""

from __future__ import annotations

import os

import pytest

from tools.research.probe_gate_coverage import (
    EXPECTED_KEY_COUNTS,
    GATED_FLOOR,
    NAMESPACES,
    SUBSPLIT_GATED_FLOOR,
    check_floors,
    namespace_keys,
    probe,
    probe_units,
)

_RUN_PROBE = os.getenv("CIRIS_RUN_GATE_COVERAGE_PROBE", "").strip().lower() in ("1", "true", "yes")

requires_probe = pytest.mark.skipif(
    not _RUN_PROBE,
    reason=(
        "full compose sweep (100+ subprocesses) — enforced by the compose-gate CI job via "
        "`probe_gate_coverage --assert-floors`; set CIRIS_RUN_GATE_COVERAGE_PROBE=1 to run it here"
    ),
)


def test_probe_enumerates_the_whole_key_space() -> None:
    """The probe must measure the facility's real key space, not a copy of it.

    This is the cheap half of the lock and the reason the expensive half can be
    trusted: if the key space drifts, the floors are being defended against the
    wrong denominator, and that is caught on every commit rather than only when
    the sweep runs.
    """
    counts = {namespace: len(keys) for namespace, keys in namespace_keys().items()}
    assert counts == EXPECTED_KEY_COUNTS
    assert set(NAMESPACES) == set(EXPECTED_KEY_COUNTS)


def test_every_key_belongs_to_exactly_one_probe_unit() -> None:
    """No key may go unmeasured, and none may be double-counted.

    A key silently missing from the unit list would never be REPORTED dark — it
    would simply not be looked at, which is precisely the failure mode this
    module exists to prevent.
    """
    units = probe_units()
    covered = [key for unit in units for key in unit.keys]
    assert sorted(covered) == sorted(key for keys in namespace_keys().values() for key in keys)
    assert len(covered) == len(set(covered)), "a key appears in more than one probe unit"


def test_floors_are_consistent_with_the_key_space() -> None:
    """A floor may never exceed the number of keys it is stated over.

    Cheap, but it catches the specific mistake of raising a floor past what the
    namespace can supply — which would make the lock unsatisfiable and get it
    quietly lowered again.
    """
    for namespace, floor in GATED_FLOOR.items():
        assert floor <= EXPECTED_KEY_COUNTS[namespace], namespace
    assert set(GATED_FLOOR) == set(EXPECTED_KEY_COUNTS)
    for label, floor in SUBSPLIT_GATED_FLOOR.items():
        namespace = label.split(":", 1)[0]
        assert floor <= EXPECTED_KEY_COUNTS[namespace], label


@requires_probe
@pytest.mark.slow
@pytest.mark.timeout(1800)
def test_gate_coverage_does_not_regress() -> None:
    """No namespace may lose gated keys. Gaining them is always fine.

    Runs the real sweep: one composition subprocess per override key, each
    diffed against an un-overridden baseline dump. Slow on purpose — nothing
    cheaper actually proves a key reaches a composed block.
    """
    problems = check_floors(probe(locales=("en",), jobs=8))
    assert not problems, "gate coverage regressed:\n  " + "\n  ".join(problems)


@requires_probe
@pytest.mark.slow
@pytest.mark.timeout(1800)
def test_the_three_dark_namespaces_are_reachable() -> None:
    """#986's headline: template, conscience_prompt and the conscience.* strings.

    Asserted as "not zero" rather than against a count, because this test owns
    the qualitative claim — the dump reaches these namespaces at all — while
    :func:`test_gate_coverage_does_not_regress` owns the quantities.
    """
    report = probe(locales=("en",), namespaces=("template", "conscience_prompt", "string"), jobs=8)
    rows = {row.namespace: row for row in report.namespaces}
    subsplits = {row.namespace: row for row in report.subsplits}

    assert rows["conscience_prompt"].keys_gated > 0, "conscience faculty prompts compose nothing"
    assert rows["template"].keys_gated > 0, "AgentTemplate prose reaches no composed block"
    assert subsplits["string:conscience.*"].keys_gated > 0, "the retry envelope composes nothing"
