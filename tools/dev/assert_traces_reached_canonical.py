#!/usr/bin/env python3
"""Fail unless CEG traces actually reached canonical-server-1.

WHY THIS IS A SEPARATE, FATAL SCRIPT.

`QARunner._verify_federation_delivery()` already inspects the same signals, and
says of itself:

    Best-effort + non-fatal — reports, never crashes the run.

That is the right call for a broad QA sweep, where a federation hiccup should not
mask fifty unrelated results. It is the wrong call for a RELEASE GATE. A gate
that reports and passes is indistinguishable from a gate that checked nothing,
and this repository has now paid for that twice in one release: v2.9.42 published
no Android APK, and CIRISClient 0.5.191 shipped with no XCFramework. Both were
green.

So the gate is its own script, in the idiom this repo already uses for exactly
this purpose (`tools/dev/assert_oauth_redirect_uri.py`): one question, a nonzero
exit, invoked from the workflow.

WHAT "REACHED CANONICAL" ACTUALLY MEANS.

Delivery is a ladder, and each rung has its own log line
(`ciris_engine/logic/runtime/edge_runtime.py`). Checking only the top rung tells
you nothing about why it failed, so this reports the highest rung reached:

    1. ROOTED       transport found the peer     "canonical <k> ROOTED after ~Ns"
    2. KEX PRESENT  key exchange resolved        "canonical <k> KEX PRESENT after ~Ns post-root"
    3. REPLICATION  trace rows actually served   replication_envelopes_served_total=N

Rungs 1 and 2 are preconditions, NOT delivery. A run can root and complete KEX
and still move nothing.

*** THE COUNTER THIS GATE MUST NOT USE: envelopes_sent_total. ***

The first version of this file keyed rung 3 on `SHIP CONFIRMED —
envelopes_sent_total=N`, and that INVERTS the gate: it fails runs where traces
genuinely landed.

`envelopes_sent_total` is incremented only from edge's application/durable send
path (`inc_sent`/`inc_received`, `src/edge.rs`). The anti-entropy REPLICATION
plane — which is what actually carries `trace:*` rows to a canonical — touches
neither counter. So a run that lands trace_events on the canonical, summarised
and scored, reports `envelopes_sent_total: 0`. Measured upstream: 15 trace_events
delivered, counter zero.

That is CIRISEdge#434, closed, whose guidance is explicit: *do not key
trace-pipeline health on envelopes_sent_total; it measures the
application/durable plane only.* The plane-correct counter is
`replication_envelopes_served_total` (CIRISEdge#433, live since edge v15.x);
`operator_surface.rs:1468` is the reference reader.

So `SHIP CONFIRMED — envelopes_sent_total=0` is not the phrase lying. It is the
phrase being right about a plane this gate does not care about, and the counter
being blind to the one it does.

This is not a hypothetical mistake to guard against: `harness/mesh-repro/
scenarios/traceflow.sh` made exactly it, and its own comment records the
outcome — a stage-5 ship rung that "could never pass — a check that could not
fail, inside the instrument built to catch exactly that."

WHY A MISSING SIGNAL FAILS RATHER THAN FALLING BACK. If no
`replication_envelopes_served_total` appears anywhere in the logs, this gate
fails and says so. It deliberately does NOT fall back to `envelopes_sent_total`:
falling back to the wrong plane is how the gate became wrong in the first place,
and "the signal is not being emitted yet" is a real, fixable condition that
should be visible rather than silently satisfied by a counter that means
something else.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

#: The ladder, highest rung last. Each entry: (rung name, compiled pattern).
ROOTED = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+ROOTED after ~(\d+)s")
KEX_PRESENT = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+KEX PRESENT after ~(\d+)s")
#: THE PLANE-CORRECT COUNTER. Anti-entropy replication is what carries `trace:*`
#: rows to a canonical, and it is served, not "sent". Matched loosely on purpose:
#: it may arrive as a bare metrics line, inside a [TRACE-SHIP] probe, or embedded
#: in a JSON blob, and a gate that only reads one spelling is a gate that reports
#: "no evidence" while the evidence is right there in another shape.
REPLICATION_SERVED = re.compile(r"replication_envelopes_served_total[\"'\s:=]+(\d+)")

#: NOT delivery. Retained only so the report can say the application plane moved,
#: which is a genuinely different fact — see the module docstring.
SHIP_CONFIRMED = re.compile(
    r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+SHIP CONFIRMED\s+—\s+envelopes_sent_total=(\d+)"
)

#: The agent's probe says this OUT LOUD when the substrate has no such counter,
#: which is a different fact from "nothing was delivered" and must not be graded
#: the same way (CIRISServer#518).
COUNTER_ABSENT = re.compile(r"replication_envelopes_served_total ABSENT from delivery_status")

#: Explicit failure lines, so the report can quote the node's own words rather
#: than inferring failure from the absence of success.
NO_ROOT = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+did not root within (\d+)s")
KEX_NONE = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+KEX still None at (\d+)s")
ZERO_ENVELOPES = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+):.*ZERO", re.IGNORECASE)
SHIP_UNCONFIRMED = re.compile(r"\[DELIVERY-PROBE\].*SHIP UNCONFIRMED")


def _read(paths: List[Path]) -> Tuple[str, List[Path]]:
    """Concatenate every log we were pointed at, remembering which existed.

    Multiple paths because the probe line lands in whichever log the run
    configured, and a gate that checks one file and silently finds nothing is the
    failure mode this script exists to prevent.
    """
    chunks: List[str] = []
    found: List[Path] = []
    for p in paths:
        try:
            if p.is_dir():
                for f in sorted(p.rglob("*.log")):
                    chunks.append(f.read_text(errors="replace"))
                    found.append(f)
            elif p.exists():
                chunks.append(p.read_text(errors="replace"))
                found.append(p)
        except OSError:
            continue
    return "\n".join(chunks), found


def _probe_lines(text: str) -> List[str]:
    return [ln for ln in text.splitlines() if "[DELIVERY-PROBE]" in ln]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "logs",
        nargs="+",
        type=Path,
        help="Log files or directories to scan (directories are searched for *.log).",
    )
    ap.add_argument(
        "--require",
        choices=["rooted", "kex", "replication"],
        default="replication",
        help=(
            "Highest rung that must be reached. Default 'replication' — the only rung "
            "that means trace rows were actually served to canonical. Lower values "
            "diagnose a partially-working transport and MUST NOT be used to gate a "
            "release. Note there is deliberately no 'ship' option: envelopes_sent_total "
            "measures the application plane and is structurally blind to trace "
            "replication (CIRISEdge#434)."
        ),
    )
    ap.add_argument(
        "--peer",
        default=None,
        help="Only consider probe lines for this canonical key (default: any).",
    )
    ap.add_argument(
        "--wait-secs",
        type=int,
        default=0,
        help=(
            "Re-read the logs until the required rung appears, up to this many "
            "seconds. Delivery is ASYNCHRONOUS — the probe can spend minutes rooting "
            "and reports at a 60s cadence — so a one-shot scan straight after a fast "
            "chat can fail a run that delivers moments later. 0 keeps the one-shot "
            "behaviour for offline log analysis."
        ),
    )
    args = ap.parse_args()

    deadline = time.monotonic() + max(0, args.wait_secs)
    while True:
        rc = _evaluate(args)
        if rc == 0 or time.monotonic() >= deadline:
            return rc
        time.sleep(10)


def _evaluate(args) -> int:
    text, found = _read(args.logs)

    if not found:
        print("FAIL: none of the given log paths exist:", ", ".join(str(p) for p in args.logs))
        print("      A gate that cannot find its evidence must fail, not pass quietly.")
        return 2

    probes = _probe_lines(text)
    if not probes:
        print(f"FAIL: no [DELIVERY-PROBE] lines in {len(found)} log file(s).")
        print("      Either federation delivery was never enabled for this run")
        print("      (the QA runner needs --federation-delivery), or the node never")
        print("      reached the probe. Absence of evidence is not delivery.")
        return 1

    def _match(rx):
        for ln in probes:
            m = rx.search(ln)
            if m and (args.peer is None or m.group(1) == args.peer):
                return m
        return None

    rooted = _match(ROOTED)
    kex = _match(KEX_PRESENT)
    ship = _match(SHIP_CONFIRMED)  # application plane — reported, never gated on

    # Replication is searched across the WHOLE text, not just [DELIVERY-PROBE]
    # lines: the counter may arrive from a metrics dump or a node_state blob that
    # carries no probe prefix.
    # ANY POSITIVE SAMPLE COUNTS, NOT THE FIRST ONE.
    #
    # `_log_trace_ship()` emits this counter REPEATEDLY — at every status cadence
    # while delivery is still in flight. A healthy run therefore logs
    # `…served_total=0` early and a positive value later, and `search()` (first
    # match) would read the zero and fail a run that delivered fine. Asynchronous
    # delivery is the normal case, so the first sample is the least informative
    # one available.
    samples = [int(m) for m in REPLICATION_SERVED.findall(text)]
    served = max(samples) if samples else None

    print(f"Scanned {len(found)} log file(s), {len(probes)} [DELIVERY-PROBE] line(s).")
    print(f"  1. ROOTED       {'yes — ' + rooted.group(1) if rooted else 'NO'}")
    print(f"  2. KEX PRESENT  {'yes' if kex else 'NO'}")
    print(f"  3. REPLICATION  {'replication_envelopes_served_total=' + str(served) if served is not None else 'NO SIGNAL'}")
    if ship:
        # Printed for context only. A reader who sees this and assumes delivery is
        # making precisely the CIRISEdge#434 mistake, so it is labelled inline.
        print(f"     (application plane: envelopes_sent_total={ship.group(2)} — "
              f"NOT trace delivery, see CIRISEdge#434)")

    replicated = served is not None and served > 0
    reached: Optional[str] = "replication" if replicated else "kex" if kex else "rooted" if rooted else None
    order = {"rooted": 1, "kex": 2, "replication": 3}

    if reached is not None and order[reached] >= order[args.require]:
        print(f"\nPASS: reached '{reached}' (required '{args.require}').")
        return 0

    print(f"\nFAIL: highest rung reached was '{reached or 'none'}', required '{args.require}'.")
    # ROOT CAUSE FIRST. A run that never rooted has a transport problem, and
    # saying "emit the counter" at it would send the reader to the wrong place.
    # The missing-signal note is appended AFTER the ladder diagnosis rather than
    # short-circuiting it — an earlier version returned immediately on a missing
    # counter and swallowed "the peer never rooted", which is the more actionable
    # of the two facts.
    if served == 0:
        print("      replication_envelopes_served_total=0 — the replication plane ran and served nothing")
    for rx, why in (
        (NO_ROOT, "the canonical peer never rooted — transport/bootstrap problem"),
        (KEX_NONE, "rooted, but key exchange never resolved — traces cannot be sealed"),
        (ZERO_ENVELOPES, "the probe saw zero envelopes on the application plane"),
        (SHIP_UNCONFIRMED, "the application-plane delivery window closed unconfirmed"),
    ):
        m = rx.search(text)
        if m:
            print(f"      {why}")
    if args.require == "replication" and served is None and COUNTER_ABSENT.search(text):
        # THE INSTRUMENT IS MISSING, NOT THE DELIVERY.
        #
        # `replication_envelopes_served_total` is not in this wheel's
        # delivery_status payload (CIRISServer#518), and the agent's own probe
        # says so in as many words. Grading that as a delivery FAILURE would be
        # reporting a fact we have no way to observe — the same error, inverted,
        # as passing on `envelopes_sent_total` because it happened to be there.
        #
        # Exit 0, because this run did not demonstrate a failure. Say NOT COVERED
        # loudly, because it did not demonstrate success either, and a gate that
        # quietly returns 0 is indistinguishable from one that checked.
        print("\nNOT COVERED: this substrate exposes no replication_envelopes_served_total.")
        print("             The node's own probe reports it ABSENT from delivery_status,")
        print("             so trace delivery cannot be observed from a log tail at all —")
        print("             which is NOT evidence that delivery failed.")
        print("             Tracked as CIRISServer#518. Until it lands, this rung is")
        print("             unobservable rather than red; it does NOT fall back to")
        print("             envelopes_sent_total, which measures a different plane.")
        return 0

    if args.require == "replication" and served is None:
        print("      no replication_envelopes_served_total appears anywhere in these logs.")
        print("      This gate does NOT fall back to envelopes_sent_total: that counter")
        print("      measures the application/durable plane and is structurally blind to")
        print("      trace replication (CIRISEdge#434), so falling back would fail runs")
        print("      that delivered fine and pass runs that delivered nothing.")
        print("      If the transport rungs above are green, the likely fix is agent-side:")
        print("      emit the plane-correct counter (CIRISEdge#433, operator_surface.rs:1468).")
    print("\n      The node's own probe lines:")
    for ln in probes[-8:]:
        print(f"        {ln.strip()[:160]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
