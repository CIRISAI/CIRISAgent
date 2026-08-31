"""The trace gate must fail on every way delivery can not-happen.

This gate exists because the QA runner's own federation check is, by its own
docstring, "best-effort + non-fatal — reports, never crashes the run". That is
correct for a broad sweep and wrong for a release gate, and this repository has
paid for the difference: v2.9.42 published no Android APK and CIRISClient 0.5.191
shipped with no XCFramework, both behind green ticks.

So the cases below are all failure cases but one. A gate is only worth having if
it can fail, and the interesting rungs are the ones that LOOK like success:
`SHIP CONFIRMED` with a zero envelope count, and a log file that simply has no
probe lines in it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[2] / "tools" / "dev" / "assert_traces_reached_canonical.py"

ROOTED = "[DELIVERY-PROBE] canonical canonical-server-1 ROOTED after ~12s"
KEX = "[DELIVERY-PROBE] canonical canonical-server-1 KEX PRESENT after ~3s post-root — sealing enabled"


def _run(tmp_path: Path, body: str, *extra: str) -> subprocess.CompletedProcess:
    log = tmp_path / "agent.log"
    log.write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(GATE), str(log), *extra],
        capture_output=True,
        text=True,
    )


def test_ship_confirmed_with_envelopes_passes(tmp_path: Path) -> None:
    """The only passing shape: envelopes actually left for canonical."""
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 SHIP CONFIRMED — envelopes_sent_total=7 at ~9s post-root",
            ]
        ),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_ship_confirmed_with_zero_envelopes_fails(tmp_path: Path) -> None:
    """THE TRAP. The phrase is present and nothing was sent.

    Matching on `SHIP CONFIRMED` alone would pass this, and it is not a
    hypothetical: the probe logs a separate ZERO-envelopes branch, so this state
    is one the node genuinely reaches.
    """
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 SHIP CONFIRMED — envelopes_sent_total=0 at ~9s post-root",
            ]
        ),
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "envelopes_sent_total=0" in r.stdout


def test_kex_without_ship_fails_and_names_the_rung(tmp_path: Path) -> None:
    """Rooting and KEX are preconditions, not delivery.

    This is the shape of the trace-delivery bugs that took the 2.9.7 line months
    to close: everything green up to the last step, nothing actually shipped.
    """
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 window closed after 60s post-root with SHIP UNCONFIRMED",
            ]
        ),
    )
    assert r.returncode == 1
    assert "reached was 'kex'" in r.stdout
    assert "shipping unconfirmed" in r.stdout.lower()


def test_never_rooted_fails(tmp_path: Path) -> None:
    r = _run(tmp_path, "[DELIVERY-PROBE] canonical canonical-server-1 did not root within 90s")
    assert r.returncode == 1
    assert "never rooted" in r.stdout.lower()


def test_a_log_with_no_probe_lines_fails(tmp_path: Path) -> None:
    """Absence of evidence is not delivery.

    The likeliest cause is that the run never enabled federation delivery at all,
    which would otherwise present as a silent pass — the exact class of hole this
    gate exists to close.
    """
    r = _run(tmp_path, "INFO booting\nINFO ready\n")
    assert r.returncode == 1
    assert "no [DELIVERY-PROBE] lines" in r.stdout


def test_a_missing_log_fails_rather_than_passing_quietly(tmp_path: Path) -> None:
    """A gate that cannot find its evidence must say so."""
    r = subprocess.run(
        [sys.executable, str(GATE), str(tmp_path / "nope.log")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "cannot find its evidence" in r.stdout or "do not exist" in r.stdout or "none of the given" in r.stdout


@pytest.mark.parametrize("require", ["rooted", "kex"])
def test_lower_rungs_are_available_for_diagnosis(tmp_path: Path, require: str) -> None:
    """`--require rooted/kex` exists to diagnose a partial transport.

    Kept explicitly non-default so nobody gates a release on a precondition and
    believes they gated it on delivery.
    """
    r = _run(tmp_path, "\n".join([ROOTED, KEX]), "--require", require)
    assert r.returncode == 0, r.stdout + r.stderr
