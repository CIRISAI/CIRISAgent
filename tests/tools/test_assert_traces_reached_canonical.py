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


def test_replication_served_passes(tmp_path: Path) -> None:
    """The only passing shape: trace rows served on the REPLICATION plane."""
    r = _run(
        tmp_path,
        "\n".join([ROOTED, KEX, "[TRACE-SHIP] replication_envelopes_served_total=15"]),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_traces_landed_while_the_application_counter_is_zero(tmp_path: Path) -> None:
    """THE INVERSION, and the reason this gate was rewritten.

    `envelopes_sent_total` is incremented only from edge's application/durable
    send path. Anti-entropy replication — which is what carries `trace:*` rows to
    a canonical — touches it not at all. So this log is a run where traces
    GENUINELY LANDED and the application counter reads zero.

    The first version of this gate keyed rung 3 on `SHIP CONFIRMED —
    envelopes_sent_total=N` and would FAIL this run. That is CIRISEdge#434, and
    `harness/mesh-repro/scenarios/traceflow.sh` made the same mistake before us.
    """
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 SHIP CONFIRMED — envelopes_sent_total=0 at ~9s post-root",
                "[TRACE-SHIP] replication_envelopes_served_total=15",
            ]
        ),
    )
    assert r.returncode == 0, "traces landed; the gate must not fail on a blind counter\n" + r.stdout
    assert "PASS" in r.stdout


def test_replication_zero_fails_even_with_application_plane_traffic(tmp_path: Path) -> None:
    """The mirror image: the application plane moved, the trace plane did not."""
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 SHIP CONFIRMED — envelopes_sent_total=42 at ~9s post-root",
                "[TRACE-SHIP] replication_envelopes_served_total=0",
            ]
        ),
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "served nothing" in r.stdout


def test_missing_replication_signal_fails_without_falling_back(tmp_path: Path) -> None:
    """No plane-correct counter must FAIL, never fall back to the blind one.

    Falling back is exactly how the gate was wrong to begin with.
    """
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[DELIVERY-PROBE] canonical canonical-server-1 SHIP CONFIRMED — envelopes_sent_total=42 at ~9s post-root",
            ]
        ),
    )
    assert r.returncode == 1, "a missing signal must not be satisfied by the wrong plane\n" + r.stdout
    assert "does NOT fall back" in r.stdout


def test_kex_without_replication_fails_and_names_the_rung(tmp_path: Path) -> None:
    """Rooting and KEX are preconditions, not delivery.

    This is the shape of the trace-delivery bugs that took the 2.9.7 line months
    to close: everything green up to the last step, nothing actually moved.

    Note what is NOT asserted here: the `SHIP UNCONFIRMED` line is present in the
    input and is deliberately not the reason this fails. That line reports the
    application/durable plane, which is a different plane from the one carrying
    trace rows (CIRISEdge#434) — treating it as the failure reason is the same
    category error as treating `envelopes_sent_total` as delivery. The gate fails
    here because the REPLICATION rung was never reached, and that is what the
    assertion checks.
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
    # The missing plane-correct counter must be named, since with both transport
    # rungs green that is the actionable next step.
    assert "replication_envelopes_served_total" in r.stdout


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


def test_a_missing_instrument_is_not_a_failed_delivery(tmp_path: Path) -> None:
    """CIRISServer#518: the wheel exposes no replication counter.

    Grading that as a delivery FAILURE reports a fact we have no way to observe —
    the same error, inverted, as passing on `envelopes_sent_total` because it
    happened to be present. The agent's own probe says ABSENT in as many words,
    so the two states are distinguishable and must be distinguished.

    Exit 3, NOT 0. Zero would run the caller's SUCCESS branch, and the workflow
    would record `"traces": true` for a run whose own output says NOT COVERED —
    the check asserting the opposite of what it printed. Three states need three
    codes: 0 delivered, 1 did not, 3 could not be observed.
    """
    r = _run(
        tmp_path,
        "\n".join(
            [
                ROOTED,
                KEX,
                "[TRACE-SHIP] phase=x replication_envelopes_served_total ABSENT from delivery_status (top-level keys: [])",
            ]
        ),
    )
    assert r.returncode == 3, "unobservable must be its own code, not success\n" + r.stdout
    assert "NOT COVERED" in r.stdout
    assert "CIRISServer#518" in r.stdout
    assert "PASS" not in r.stdout, "an unobservable rung must never read as a pass"


def test_a_present_counter_at_zero_is_still_fatal(tmp_path: Path) -> None:
    """The escape hatch must not widen into 'zero is fine'.

    If the counter EXISTS and reads zero, the replication plane ran and served
    nothing — observable, and a real failure.
    """
    r = _run(
        tmp_path,
        "\n".join([ROOTED, KEX, "[TRACE-SHIP] phase=ship-confirmed replication_envelopes_served_total=0"]),
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "NOT COVERED" not in r.stdout


def test_an_unobservable_rung_does_not_burn_the_wait_window(tmp_path) -> None:
    """3 is terminal, like 0 — waiting cannot make it observable.

    `--wait-secs` exists because delivery is ASYNCHRONOUS: a rung that has not
    appeared yet may appear. But NOT COVERED says the running substrate exposes
    no replication counter at all, which no amount of re-reading changes. The
    workflow passes --wait-secs 240, so this spent four minutes per platform —
    eight per two-platform runner — reprinting the verdict the first read had.
    """
    import time

    started = time.monotonic()
    r = _run(
        tmp_path,
        "\n".join([ROOTED, KEX, "[TRACE-SHIP] replication_envelopes_served_total ABSENT from delivery_status"]),
        "--wait-secs",
        "60",
    )
    elapsed = time.monotonic() - started
    assert r.returncode == 3
    assert elapsed < 20, f"exit 3 waited {elapsed:.0f}s; it must be terminal"


def test_a_real_failure_still_retries(tmp_path) -> None:
    """The escape hatch must not turn into 'never wait'.

    A zero counter CAN become non-zero while we wait — that is the whole reason
    the wait exists, and it must keep working.
    """
    import time

    started = time.monotonic()
    r = _run(
        tmp_path,
        "\n".join([ROOTED, KEX, "[TRACE-SHIP] replication_envelopes_served_total=0"]),
        "--wait-secs",
        "12",
    )
    elapsed = time.monotonic() - started
    assert r.returncode == 1
    assert elapsed >= 10, f"a retryable failure returned after {elapsed:.0f}s without waiting"
