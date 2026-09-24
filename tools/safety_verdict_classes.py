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

#: Statuses that CAN mean a fault that outlasts the run. 429 and 529 are
#: absent on purpose: they are transient and already retried with backoff, and
#: ending a battery on a capacity spike would throw away good evidence.
TERMINAL_JUDGE_STATUSES = {400, 401, 402, 403}

#: 401 (bad key) and 402 (no credit) are account-wide by definition. 400 and
#: 403 are broad classes: a 400 is usually a per-request validation error
#: (context length, bad content) and on OpenRouter a 403 is also a moderation
#: block on one prompt. Those end the run only when the provider says the
#: account is out of credit or over its limit.
_ACCOUNT_WIDE_STATUSES = {401, 402}
_ACCOUNT_FAULT_RE = re.compile(
    r"credit balance|insufficient (?:credit|funds|balance|quota)|billing|"
    r"key limit|limit exceeded|quota exceeded|exceeded your (?:current )?quota|"
    r"invalid (?:api )?key|unauthori[sz]ed",
    re.IGNORECASE,
)

#: Every httpx transport exception, by the class name that ends up serialized
#: into the error string ("WriteError: ...", "ProxyError: ...").
_TRANSPORT_EXC_RE = re.compile(
    r"\b(?:Connect|Read|Write|Pool)(?:Error|Timeout)\b|\bTimeoutException\b|"
    r"\b(?:Remote|Local)?ProtocolError\b|\bProxyError\b|\bUnsupportedProtocol\b|"
    r"\b(?:Network|Transport)Error\b",
)

#: Prefix for a 200 response that carried no verdict (empty choices, empty
#: content, or text without a PASS/FAIL/UNDETERMINED token).
_MALFORMED_PREFIX = "judge_response:"


def malformed_judge_error(judge_text: str) -> str:
    """The error recorded when the judge answered HTTP 200 but gave no verdict."""
    if not judge_text or not judge_text.strip():
        return f"{_MALFORMED_PREFIX} empty"
    return f"{_MALFORMED_PREFIX} no verdict token: {judge_text.strip()[:120]}"


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
    if error.startswith(_MALFORMED_PREFIX):
        return "malformed_response"
    low = error.lower()
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if low.startswith("network:") or "connect" in low or "network" in low or _TRANSPORT_EXC_RE.search(error):
        return "network"
    # A rubric that will not compile is a defect in the rubric, not the wire:
    # reported, but never folded into "the judge was unreachable".
    return None


def should_abort_run(error: Optional[str]) -> bool:
    """Does this fault mean the REST of the battery cannot be judged either?

    True only for faults that outlast the run: bad key (401), payment required
    (402), or a 400/403 whose message says the account is out of credit or over
    its limit. Continuing past one of these produced 45 and 24 consecutive
    unjudged verdicts in `es` and `ar`. A per-request 400/403 (context length,
    content validation, moderation) judges nothing for that pair only.
    """
    status = judge_error_status(error)
    if status in _ACCOUNT_WIDE_STATUSES:
        return True
    if status in TERMINAL_JUDGE_STATUSES:
        return bool(_ACCOUNT_FAULT_RE.search(error or ""))
    return False
