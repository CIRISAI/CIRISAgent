"""The QA runner's expected-incident list must exist exactly once.

There were THREE copies of `ignore_patterns` in runner.py — one per reader (the
WARNING-flood detector, the per-backend log surfacer, and the incidents gate).
They had drifted to 26 / 14 / 27 entries, and the 14-entry copy was the one the
GATE used. So the gate failed on precisely the lines the other two readers
already knew to ignore:

    qa_manifest_test_                                   (adapter_manifest test)
    Invalid target state                                (state_transitions test)
    Config validation failed: Configuration is empty    (adapter_config test)
    Failed to transition from AgentState.WORK to …      (cognitive-state test)
    Reddit credentials are not configured               (adapter probe, no creds)

Every one of those is a QA test asserting that bad input is rejected. The suite
was failing itself for doing its job, and which backend it landed on varied by
timing — postgres one run, sqlite the next, on the same commit.

A QA gate that fires on its own negative tests carries no information: it is red
whether or not anything is wrong. That is the same "instrument reports the wrong
thing" class as a gate that is green whether or not anything is wrong; the
direction differs, the uselessness does not.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.qa_runner.runner import EXPECTED_QA_INCIDENT_PATTERNS

RUNNER = Path("tools/qa_runner/runner.py")

# The exact lines from the CI run that failed (run 31406599409, sqlite leg).
CI_INCIDENT_LINES = [
    "ERROR - adapter_configuration.service - service.py:596 - Config validation failed: Configuration is empty",
    "ERROR - system.runtime - runtime.py:124 - [STATE_TRANSITION] FAIL: Invalid target state 'INVALID_STATE'",
    "ERROR - adapter_manager - adapter_manager.py:300 - Failed to load adapter reddit with ID qa_manifest_test_reddit",
    "ERROR - main_processor - main_processor.py:1328 - Failed to transition from AgentState.WORK to AgentState.WORK",
]

# Incidents that mean something is actually wrong. These must never be silenced.
REAL_INCIDENT_LINES = [
    "CRITICAL - ciris_runtime - ciris_runtime.py:450 - Runtime initialization failed",
    "ERROR - initialization.service - service.py:214 - Error: Engine.__new__() got an unexpected keyword argument",
    "ERROR - db.core - core.py:88 - database is locked",
]


def _ignored(line: str) -> bool:
    return any(pattern in line for pattern in EXPECTED_QA_INCIDENT_PATTERNS)


def test_the_list_is_defined_exactly_once() -> None:
    """The DRY that prevents the drift, asserted structurally."""
    source = RUNNER.read_text(encoding="utf-8")
    literals = re.findall(r"^\s*ignore_patterns = \[", source, re.M)
    assert not literals, (
        f"found {len(literals)} inline ignore_patterns literal(s) — these are copies "
        f"that will drift apart again. Use EXPECTED_QA_INCIDENT_PATTERNS."
    )


def test_every_reader_uses_the_shared_list() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    uses = source.count("ignore_patterns = EXPECTED_QA_INCIDENT_PATTERNS")
    assert uses >= 3, f"expected all three readers to share the list, found {uses}"


def test_the_ci_run_would_now_pass(  ) -> None:
    """Each line that failed the run, by name."""
    missed = [line for line in CI_INCIDENT_LINES if not _ignored(line)]
    assert not missed, f"these QA-induced lines would still fail the run: {missed}"


def test_a_real_incident_still_fails_the_run() -> None:
    """The gate must keep its teeth — silencing everything is the other failure."""
    silenced = [line for line in REAL_INCIDENT_LINES if _ignored(line)]
    assert not silenced, (
        f"the ignore list swallows genuine incidents: {silenced}. A gate that cannot "
        f"go red is not a gate."
    )


def test_patterns_are_specific_enough_to_be_safe() -> None:
    """A pattern short enough to match anything silences everything."""
    too_broad = [p for p in EXPECTED_QA_INCIDENT_PATTERNS if len(p) < 8]
    assert not too_broad, f"suspiciously broad ignore patterns: {too_broad}"


def test_no_duplicate_patterns() -> None:
    seen = [p for p in EXPECTED_QA_INCIDENT_PATTERNS]
    assert len(seen) == len(set(seen)), "duplicate entries — a merge went wrong"
