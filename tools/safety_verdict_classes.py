"""Did the judge answer, or not? One definition, two readers.

`undetermined` covers two populations that look identical in a summary and mean
opposite things: the judge read the answer and could not decide, versus the judge
never answered at all. Across the 249 interpret runs in `qa_reports/`, 76
`undetermined` verdicts were the second kind — 45x HTTP 400 "Your credit balance
is too low", 24x HTTP 403 "Key limit exceeded (weekly limit)", 7x 529 overloaded.
Counted in the denominator, they made Arabic the worst-looking cell in the corpus
(55.6 % pass) while it had ZERO failures: a billing lapse rendering as a safety
regression (CIRISAgent#1161).

STDLIB ONLY, DELIBERATELY. Two things read this: the interpreter that writes the
bundles (which has httpx, rich and the rest), and `build_results_index.py`, which
the Results page workflow runs on a bare checkout with NO pip install at all.
Importing the interpreter from the index would have taken the public page down
the first time it ran. Restating the rule in both places would let the artifact
and the page disagree about the same run, which is worse.
"""

from __future__ import annotations

import re
from typing import Optional

#: The judge call failed rather than returning a judgement.
_TRANSPORT_ERROR_RE = re.compile(r"^HTTP (\d{3})\b")

#: Faults that do NOT clear inside a run. 429 and 529 are absent on purpose:
#: they are transient and already retried with backoff, and ending a battery on
#: a capacity spike would throw away good evidence.
TERMINAL_JUDGE_STATUSES = {400, 401, 402, 403}


def judge_error_status(error: Optional[str]) -> Optional[int]:
    """The HTTP status behind a transport fault, if it had one."""
    if not error:
        return None
    m = _TRANSPORT_ERROR_RE.match(error.strip())
    return int(m.group(1)) if m else None


def judge_error_class(error: Optional[str]) -> Optional[str]:
    """Which transport fault produced this non-verdict, or None if it was judged.

    None means the interpreter returned a judgement — including a genuine
    `undetermined`, which IS a result and belongs in the denominator. Anything
    else names the fault, so a summary can report what was measured separately
    from what could not be.
    """
    if not error:
        return None
    status = judge_error_status(error)
    if status is not None:
        return f"http_{status}"
    low = error.lower()
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if "connect" in low or "readerror" in low or "network" in low:
        return "network"
    # A rubric that will not compile is a defect in the rubric, not the wire:
    # reported, but never folded into "the judge was unreachable".
    return None


def should_abort_run(error: Optional[str]) -> bool:
    """Does this fault mean the REST of the battery cannot be judged either?

    True only for faults that outlast the run: no credit (400), bad key (401),
    payment required (402), key limit reached (403). Continuing past one of
    these produced 45 and 24 consecutive unjudged verdicts in `es` and `ar`.
    """
    return judge_error_status(error) in TERMINAL_JUDGE_STATUSES
