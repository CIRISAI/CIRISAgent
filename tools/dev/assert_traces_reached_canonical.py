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

    1. ROOTED         transport found the peer          "canonical <k> ROOTED after ~Ns"
    2. KEX PRESENT    key exchange resolved             "canonical <k> KEX PRESENT after ~Ns post-root"
    3. SHIP CONFIRMED envelopes actually left           "canonical <k> SHIP CONFIRMED — envelopes_sent_total=N"

Rungs 1 and 2 are preconditions, NOT delivery. A run can root and complete KEX
and still ship nothing — that is the `SHIP UNCONFIRMED` case, and it is the exact
shape of the trace-delivery bugs that took the 2.9.7 line months to close. Only
rung 3, with a NONZERO envelope count, means a trace left this node for
canonical-server-1.

WHY THE ENVELOPE COUNT IS CHECKED AND NOT JUST THE PHRASE. `SHIP CONFIRMED` is
logged with `envelopes_sent_total=%s`. Accepting the phrase alone would pass on
`envelopes_sent_total=0`, which is precisely the ZERO-envelopes failure the same
probe logs one branch earlier.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

#: The ladder, highest rung last. Each entry: (rung name, compiled pattern).
ROOTED = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+ROOTED after ~(\d+)s")
KEX_PRESENT = re.compile(r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+KEX PRESENT after ~(\d+)s")
SHIP_CONFIRMED = re.compile(
    r"\[DELIVERY-PROBE\]\s+canonical\s+(\S+)\s+SHIP CONFIRMED\s+—\s+envelopes_sent_total=(\d+)"
)

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
        choices=["rooted", "kex", "ship"],
        default="ship",
        help=(
            "Highest rung that must be reached. Default 'ship' — the only rung that "
            "means a trace actually left for canonical. Lower values are for "
            "diagnosing a partially-working transport, NOT for release gating."
        ),
    )
    ap.add_argument(
        "--peer",
        default=None,
        help="Only consider probe lines for this canonical key (default: any).",
    )
    args = ap.parse_args()

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
    ship = _match(SHIP_CONFIRMED)

    print(f"Scanned {len(found)} log file(s), {len(probes)} [DELIVERY-PROBE] line(s).")
    print(f"  1. ROOTED         {'yes — ' + rooted.group(1) if rooted else 'NO'}")
    print(f"  2. KEX PRESENT    {'yes' if kex else 'NO'}")
    print(f"  3. SHIP CONFIRMED {'yes — envelopes_sent_total=' + ship.group(2) if ship else 'NO'}")

    reached: Optional[str] = "ship" if ship else "kex" if kex else "rooted" if rooted else None
    order = {"rooted": 1, "kex": 2, "ship": 3}

    if reached is not None and order[reached] >= order[args.require]:
        # SHIP CONFIRMED with a zero count is not delivery. The probe logs a
        # separate ZERO-envelopes branch for this; refuse it explicitly rather
        # than trusting the phrase.
        if args.require == "ship" and int(ship.group(2)) == 0:
            print("\nFAIL: SHIP CONFIRMED but envelopes_sent_total=0 — nothing was actually sent.")
            return 1
        print(f"\nPASS: reached '{reached}' (required '{args.require}').")
        return 0

    print(f"\nFAIL: highest rung reached was '{reached or 'none'}', required '{args.require}'.")
    for rx, why in (
        (NO_ROOT, "the canonical peer never rooted — transport/bootstrap problem"),
        (KEX_NONE, "rooted, but key exchange never resolved — traces cannot be sealed"),
        (ZERO_ENVELOPES, "rooted and KEX'd, but ZERO envelopes were sent"),
        (SHIP_UNCONFIRMED, "the delivery window closed with shipping unconfirmed"),
    ):
        m = rx.search(text)
        if m:
            print(f"      {why}")
    print("\n      The node's own probe lines:")
    for ln in probes[-8:]:
        print(f"        {ln.strip()[:160]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
