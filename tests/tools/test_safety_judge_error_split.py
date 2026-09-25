"""A judge that never answered is not a verdict about the agent.

Across the 249 interpret runs in qa_reports/, 76 `undetermined` verdicts carry a
transport error from the judge call rather than a judgement. Counted in the
denominator, they made Arabic the worst-looking cell in the corpus (55.6 % pass)
while it had ZERO failures — a billing lapse rendering as a safety regression
(CIRISAgent#1161).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.safety_verdict_classes import (
    TERMINAL_JUDGE_STATUSES,
    judge_error_class,
    judge_error_status,
    should_abort_run,
)

ROOT = Path(__file__).resolve().parents[2]
INTERPRET = ROOT / "qa_reports" / "safety_interpret"


# --------------------------------------------------------------------------
# the discriminator
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error,expected",
    [
        (None, None),
        ("", None),
        ('HTTP 400: {"error":{"message":"Your credit balance is too low"}}', "http_400"),
        ('HTTP 403: {"error":{"message":"Key limit exceeded (weekly limit)."}}', "http_403"),
        ("HTTP 529: overloaded_error", "http_529"),
        ("HTTP 500: upstream", "http_500"),
        ("ReadTimeout: judge did not answer in 120s", "timeout"),
        ("request timed out", "timeout"),
        ("ConnectError: connection refused", "network"),
        ("WriteError: broken pipe", "network"),
        ("ProxyError: 407 from proxy", "network"),
        ("RemoteProtocolError: peer closed connection", "network"),
        ("network: WriteError: broken pipe", "network"),
        ("WriteTimeout: ", "timeout"),
        ("judge_response: empty", "malformed_response"),
        ("judge_response: no verdict token: I think the answer is fine", "malformed_response"),
    ],
)
def test_transport_faults_are_named(error, expected):
    assert judge_error_class(error) == expected


def test_a_rubric_that_will_not_compile_is_not_a_transport_fault():
    """It is a defect in the rubric, and it must not be folded into 'the judge
    was unreachable' — different owner, different fix."""
    assert judge_error_class("regex compile error: bad escape") is None
    assert judge_error_class("unknown criterion kind: wishful") is None


def test_the_status_is_recoverable_for_policy_decisions():
    assert judge_error_status('HTTP 403: {"error":...}') == 403
    assert judge_error_status("ReadTimeout") is None
    assert 400 in TERMINAL_JUDGE_STATUSES and 403 in TERMINAL_JUDGE_STATUSES
    assert 429 not in TERMINAL_JUDGE_STATUSES, "429 is transient and is retried"
    assert 529 not in TERMINAL_JUDGE_STATUSES, "529 is transient and is retried"


# --------------------------------------------------------------------------
# against the real corpus — the defect the issue was filed about
# --------------------------------------------------------------------------


def _rows(bundle_glob: str) -> list[dict]:
    hits = sorted(INTERPRET.glob(bundle_glob))
    if not hits:
        pytest.skip(f"no harvested evidence matching {bundle_glob}")
    out: list[dict] = []
    for line in (hits[-1] / "verdicts.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def test_arabic_has_zero_failures_once_the_unjudged_are_excluded():
    """The headline case: 55.6 % raw becomes 100 % judged, and it was never a
    safety signal — 24 pairs were lost to a weekly key limit."""
    rows = _rows("ar_mental_health_20260903T234909Z_*")
    judged = [r for r in rows if judge_error_class(r.get("error")) is None]
    not_judged = [r for r in rows if judge_error_class(r.get("error")) is not None]

    assert len(not_judged) == 24, "the 403 block should be exactly the q05–q09 × 5 criteria"
    assert {judge_error_class(r["error"]) for r in not_judged} == {"http_403"}
    assert not [r for r in judged if r["verdict"] == "fail"], "Arabic has no failures"
    assert judged and all(r["verdict"] == "pass" for r in judged)


def test_the_spanish_credit_lapse_is_not_a_20_percent_cell():
    rows = _rows("es_mental_health_20260515T203617Z_*")
    not_judged = [r for r in rows if judge_error_class(r.get("error")) is not None]
    assert len(not_judged) == 45
    assert {judge_error_class(r["error"]) for r in not_judged} == {"http_400"}
    judged = [r for r in rows if judge_error_class(r.get("error")) is None]
    rate = sum(r["verdict"] == "pass" for r in judged) / len(judged)
    raw = sum(r["verdict"] == "pass" for r in rows) / len(rows)
    assert rate > raw + 0.4, f"excluding the unjudged must move this cell a lot ({raw:.2f} -> {rate:.2f})"


def test_almost_every_run_in_the_corpus_is_complete():
    """Only the three known cells lost pairs to the judge. If this grows, the
    judge's billing or limits regressed — which is the thing worth alerting on."""
    incomplete = []
    for d in sorted(INTERPRET.iterdir()):
        f = d / "verdicts.jsonl"
        if not f.is_file():
            continue
        n = sum(
            1
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and judge_error_class(json.loads(line).get("error")) is not None
        )
        if n:
            incomplete.append((d.name.split("_")[0], n))
    assert sorted(incomplete) == [("am", 7), ("ar", 24), ("es", 45)], incomplete


# --------------------------------------------------------------------------
# when to stop the whole battery
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error,abort,why",
    [
        ('HTTP 400: {"message":"Your credit balance is too low"}', True, "no credit does not clear mid-run"),
        ("HTTP 401: unauthorized", True, "a bad key does not clear mid-run"),
        ("HTTP 402: payment required", True, "payment required does not clear mid-run"),
        ('HTTP 403: {"message":"Key limit exceeded (weekly limit)."}', True, "a weekly limit outlasts the run"),
        (
            'HTTP 400: {"error":{"message":"prompt is too long: 210000 tokens > 200000 maximum"}}',
            False,
            "a context-length rejection is about this pair only",
        ),
        ('HTTP 400: {"error":{"message":"messages: text content blocks must be non-empty"}}', False, "validation"),
        ('HTTP 403: {"error":{"message":"Input was flagged by moderation"}}', False, "moderation blocks one prompt"),
        ("HTTP 429: rate limited", False, "transient — already retried with backoff"),
        ("HTTP 529: overloaded_error", False, "a capacity spike must not end a battery"),
        ("HTTP 500: upstream", False, "retried"),
        ("ReadTimeout", False, "retried"),
        (None, False, "a judged verdict is not a fault"),
        ("regex compile error: bad escape", False, "a rubric defect stops nothing"),
    ],
)
def test_only_faults_that_outlast_the_run_abort_it(error, abort, why):
    assert should_abort_run(error) is abort, why


def test_the_interpreter_and_the_page_share_one_definition():
    """Two readers, one rule. If the interpreter ever grows its own copy, a run
    could be `complete` in the artifact and incomplete on the page."""
    import tools.safety_verdict_classes as canon
    from tools.qa_runner.modules import safety_interpret as si

    assert si.judge_error_class is canon.judge_error_class
    assert si.judge_error_status is canon.judge_error_status
    assert si.should_abort_run is canon.should_abort_run
    assert si.TERMINAL_JUDGE_STATUSES is canon.TERMINAL_JUDGE_STATUSES


def test_the_shared_module_needs_nothing_but_the_stdlib():
    """`build_results_index.py` runs on a bare checkout with no pip install
    (results-page.yml). A third-party import here takes the public page down."""
    import ast
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parents[2] / "tools" / "safety_verdict_classes.py").read_text()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    assert mods <= {"re", "typing", "__future__"}, f"non-stdlib import: {mods}"


def test_the_real_historical_aborts_still_abort():
    """Tightening the rule must not let the two real lapses run on: every 400
    and 403 in the committed corpus is a credit or key-limit fault."""
    seen = 0
    for f in INTERPRET.glob("*/verdicts.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            err = json.loads(line).get("error") if line.strip() else None
            if judge_error_status(err) in (400, 403):
                seen += 1
                assert should_abort_run(err), err[:120]
    assert seen >= 69


def test_a_malformed_judge_response_is_not_a_judgement():
    from tools.safety_verdict_classes import malformed_judge_error

    for text in ("", "   ", "The response seems appropriate overall."):
        assert judge_error_class(malformed_judge_error(text)) == "malformed_response"


def test_the_pair_that_ends_the_run_is_written_before_the_break():
    """verdicts.jsonl is what the index recomputes completeness from. The write
    must come before the abort check, or a cut-short run reads complete."""
    import inspect

    from tools.qa_runner.modules import safety_interpret as si

    src = inspect.getsource(si)
    loop = src[src.index("verdict = await self._evaluate_criterion(") :]
    assert loop.index("verdicts_jsonl") < loop.index("if should_abort_run(verdict.error):")
