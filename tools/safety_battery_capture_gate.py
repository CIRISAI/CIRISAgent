"""Refuse a safety-battery capture that did not capture the battery.

The 2.16 1.2b-vs-1.3 battery (2026-10-15) went green on ten runs that captured
1 response out of 90 questions: every DMA call timed out, every question came
back ``interact failed``, and the interpret job still graded 63 verdicts PASS
against empty responses. A capture is evidence only if it answered what it
was asked. This reads the bundle's ``summary.json`` and fails unless every
question has a captured response.

    python3 tools/safety_battery_capture_gate.py <bundle_dir>

Exit 0 = complete capture; 1 = incomplete (the reason is printed as a GitHub
``::error::``); 2 = no readable summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


def check_summary(summary: Dict[str, Any]) -> Tuple[bool, str]:
    """``(ok, reason)``: ok only when every question has a captured response."""
    try:
        n_questions = int(summary["n_questions"])
        n_captured = int(summary["n_responses_captured"])
    except (KeyError, TypeError, ValueError):
        return False, "summary.json lacks integer n_questions / n_responses_captured"
    n_errors = summary.get("n_errors", "?")
    if n_questions <= 0:
        return False, f"battery has {n_questions} questions; nothing was asked"
    if n_captured < n_questions:
        return False, (
            f"capture incomplete: {n_captured}/{n_questions} responses captured, "
            f"{n_errors} errors. Verdicts over missing responses are not evidence; "
            f"check the agent logs (LLM timeouts / circuit breaker) before re-running."
        )
    return True, f"capture complete: {n_captured}/{n_questions} responses"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: safety_battery_capture_gate.py <bundle_dir>", file=sys.stderr)
        return 2
    path = Path(args[0]) / "summary.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error title=Capture gate::no readable {path}: {exc}")
        return 2
    ok, reason = check_summary(summary)
    print(reason if ok else f"::error title=Capture incomplete::{reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
