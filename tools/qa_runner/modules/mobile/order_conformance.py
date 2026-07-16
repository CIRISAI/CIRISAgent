"""First-run provisioning-saga trace conformance (FSD/FIRST_RUN_STATECHART.md).

Extracts the [ORDER] event trace (plus node-side markers) from logcat and
validates the observed order against the normative precedence DAG. This is the
"trace conformance" layer of the first-run statechart: ordering regressions —
the class behind the claim-401, the first-run nav loop, and the setAge-401 —
surface as a named violated edge instead of log archaeology.

Runs on EVERY full_flow (success or failure): a green suite with a red
conformance report means an ordering bug that happened not to bite this run.

Best-effort by design: a conformance crash must never mask a suite result.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# ── Event vocabulary (FSD § 2) ───────────────────────────────────────────────
# Each entry: (event_id, human name, compiled pattern). First match on a line
# wins; line order in `logcat -d` is chronological, so line index is the clock.
_EVENT_PATTERNS: List[Tuple[str, str, re.Pattern]] = [
    ("E1", "node_bound", re.compile(r"LISTENING on 4243")),
    ("E2", "pin_minted", re.compile(r"CLAIM PIN")),
    ("E4", "fedid_minted", re.compile(r"\[ORDER\] fedid_minted")),
    ("E5", "claim_accepted", re.compile(r"\[ORDER\] claim_accepted")),
    ("E5x", "claim_rejected", re.compile(r"\[ORDER\] claim_rejected")),
    ("E6", "owner_login", re.compile(r"\[ORDER\] owner_login ok")),
    ("E7", "age_recorded", re.compile(r"\[ORDER\] age_recorded")),
    ("E7x", "age_record_failed", re.compile(r"\[ORDER\] age_record FAILED")),
    ("E8", "announced", re.compile(r"\[ORDER\] announced to federation")),
    ("E8x", "announce_failed", re.compile(r"\[ORDER\] announce FAILED")),
    ("E9", "claim_settled", re.compile(r"\[ORDER\] claim_settled")),
    ("E9t", "settle_await_timeout", re.compile(r"\[ORDER\] settle_await TIMEOUT")),
    ("E10", "complete_begin", re.compile(r"\[ORDER\] complete_setup begin")),
    ("E11", "config_written", re.compile(r"completeSetup returned: success=true")),
    # E12 restart boundary — the session-invalidation line (I1). Either the
    # fold's clean-restart primitive or the app's reconfiguring hold marks it.
    ("E12", "runtime_restart", re.compile(r"shutdown_node\(\) →|holding reconfiguring state")),
]

# ── Precedence DAG (FSD § 3) — only edges whose BOTH ends are observable ─────
# (a, b): every occurrence of b must come after the first occurrence of a,
# checked only when both events are present in the trace.
_EDGES: List[Tuple[str, str]] = [
    ("E1", "E2"),   # PIN minted only after the node bound
    ("E2", "E5"),   # claim requires the minted PIN
    ("E4", "E5"),   # claim binds the minted fed-ID
    ("E5", "E6"),   # owner login only post-claim
    ("E5", "E7"),   # setAge is owner-scope, post-claim
    ("E5", "E8"),   # announce post-claim
    ("E6", "E9"),   # settle covers owner login
    ("E7", "E9"),   # settle covers age record
    ("E8", "E9"),   # settle covers announce
    ("E5", "E9"),   # settle only after claim outcome
    ("E9", "E10"),  # THE GATE: no config-write/restart until settled
    ("E10", "E11"),
    ("E11", "E12"),
]

# I1: session-consuming :4243 saga events must precede the restart boundary.
_SESSION_EVENTS = ("E4", "E5", "E6", "E7", "E8")

# Required-presence implications: if `given` occurred, `required` must occur.
_REQUIRES: List[Tuple[str, str, str]] = [
    ("E5", "E9", "claim accepted but never settled — settle gate broken"),
    ("E10", "E9", "completeSetup began without a prior settle — E9≺E10 gate bypassed"),
]


def _adb_out(adb, args: List[str], timeout: int = 30) -> str:
    try:
        result = adb._run_adb(args, timeout=timeout)
        return result.stdout or ""
    except Exception:
        return ""


def extract_trace(logcat_text: str) -> List[dict]:
    """Extract the chronological event trace from a logcat dump."""
    trace: List[dict] = []
    for idx, line in enumerate(logcat_text.splitlines()):
        for ev_id, name, pat in _EVENT_PATTERNS:
            if pat.search(line):
                trace.append({"idx": idx, "event": ev_id, "name": name, "line": line.strip()[:220]})
                break
    return trace


def validate_trace(trace: List[dict]) -> dict:
    """Validate a trace against the DAG. Returns {conformant, events, violations}."""
    first: dict = {}
    for t in trace:
        first.setdefault(t["event"], t)

    violations: List[str] = []

    # Edge order: every occurrence of b must follow the FIRST a.
    for a, b in _EDGES:
        if a in first and b in first:
            a_idx = first[a]["idx"]
            for t in trace:
                if t["event"] == b and t["idx"] < a_idx:
                    violations.append(
                        f"ORDER VIOLATION {a}≺{b}: {first[a]['name']} (line {a_idx}) "
                        f"must precede {t['name']} (line {t['idx']})"
                    )
                    break

    # I1: no session-consuming event after the restart boundary (any occurrence).
    if "E12" in first:
        boundary = first["E12"]["idx"]
        for t in trace:
            if t["event"] in _SESSION_EVENTS and t["idx"] > boundary:
                violations.append(
                    f"I1 VIOLATION: session event {t['name']} (line {t['idx']}) after the "
                    f"restart boundary (line {boundary}) — its bearer was invalidated"
                )

    # Required-presence implications.
    for given, required, msg in _REQUIRES:
        if given in first and required not in first:
            violations.append(f"MISSING EVENT: {msg}")

    # Settle-await timeout is always noteworthy (bounded gate expired).
    if "E9t" in first:
        violations.append("SETTLE TIMEOUT: the E9 await expired (90s) — completeSetup ran ungated")

    return {
        "conformant": not violations,
        "events": trace,
        "violations": violations,
    }


def run_order_conformance(adb, logcat_text: Optional[str] = None) -> dict:
    """Pull logcat (unless provided) and validate the saga order."""
    text = logcat_text if logcat_text is not None else _adb_out(adb, ["logcat", "-d", "-v", "time"], timeout=60)
    return validate_trace(extract_trace(text))


def format_conformance(result: dict) -> str:
    lines = ["════ ORDER CONFORMANCE (FSD/FIRST_RUN_STATECHART.md) ════"]
    n = len(result["events"])
    if result["conformant"]:
        lines.append(f"CONFORMANT ({n} saga events observed, all edges respected)")
    else:
        lines.append(f"NON-CONFORMANT ({n} events, {len(result['violations'])} violation(s)):")
        for v in result["violations"]:
            lines.append(f"  ✗ {v}")
    for t in result["events"]:
        lines.append(f"  | {t['event']:>4} {t['name']:<22} {t['line'][:150]}")
    lines.append("═" * 58)
    return "\n".join(lines)
