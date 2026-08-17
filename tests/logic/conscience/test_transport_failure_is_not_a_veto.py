"""A conscience that cannot reach its model must not report a judgement.

CIRISAgent#1049. Every conscience shard wrapped its LLM call in a bare
`except Exception` and turned any failure into a principled veto:

    except Exception as e:
        result = EpistemicHumilityResult(recommended_action="abort", ...)

so a provider timeout was logged as

    Epistemic humility concern: abort - LLM error: Request timed out.

Nothing about humility happened -- the network failed. A downstream scorer read
those non-responses as the agent DECLINING to answer and inflated a safety
headline on a biosecurity battery until an audit caught it. 24 of 60 turns never
returned.

An unrun safety check that reports as caution is worse than an outage: an outage
is visible, this looks like the system working.

TWO DEFECTS, both covered here:

  1. FAIL-CLOSED IS INDISTINGUISHABLE FROM A PRINCIPLED OBJECTION. The result
     must say the check did not run, and must not be phrased as a judgement.

  2. THE RETRY LOOP HAS NO EXIT. passed=False triggers CONSCIENCE_RETRY +
     PONDER; the retry makes the same call against the same dead provider and
     burns another full timeout. Observed: 28 CONSCIENCE_RETRY lines, 4 override
     rounds, one conscience call taking 142s to fail.

AND IT MUST BE DRY. Four shards each invented their own fiction -- two returned
"abort", two silently judged against a default score the model never produced.
These tests assert every shard routes through the one shared handler, so a fifth
shard added later inherits the behaviour instead of reinventing it.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from ciris_engine.logic.conscience.transport import (
    LLM_FAULT_CATEGORIES,
    TRANSPORT_CATEGORIES,
    is_transport_failure,
    transport_failure_reason,
    unavailable_result,
)
from ciris_engine.schemas.conscience.core import ConscienceStatus

REPO = pathlib.Path(__file__).resolve().parents[3]
CORE = REPO / "ciris_engine" / "logic" / "conscience" / "core.py"

#: The shards that make an LLM call. Named individually so adding a fifth fails
#: this list rather than silently escaping the policy.
LLM_SHARDS = [
    "EntropyConscience",
    "CoherenceConscience",
    "OptimizationVetoConscience",
    "EpistemicHumilityConscience",
]


class _Timeout(Exception):
    """Shaped like the real thing: instructor surfaces the provider's text."""

    def __init__(self) -> None:
        super().__init__("Request timed out.")


def test_a_timeout_is_recognised_as_transport() -> None:
    assert is_transport_failure(_Timeout())


@pytest.mark.parametrize("category", sorted(TRANSPORT_CATEGORIES))
def test_transport_categories_are_disjoint_from_llm_fault(category: str) -> None:
    """A category cannot be both, or the shard would both retry and not retry."""
    assert category not in LLM_FAULT_CATEGORIES


def test_the_result_fails_closed() -> None:
    """An unreachable safety check must NOT wave the action through.

    The honest-reporting fix must not become a fail-open one: that would trade a
    misleading veto for a skipped check, which is strictly worse.
    """
    r = unavailable_result("EpistemicHumilityConscience", _Timeout())
    assert r.passed is False


def test_the_result_says_the_check_did_not_run() -> None:
    r = unavailable_result("EpistemicHumilityConscience", _Timeout())
    assert r.status == ConscienceStatus.ERROR
    assert r.check_ran is False


def test_the_reason_cannot_be_read_as_a_judgement() -> None:
    """The exact wording is the defect: a scorer parsed the old one as a refusal."""
    reason = transport_failure_reason("EpistemicHumilityConscience", _Timeout())
    assert "DID NOT RUN" in reason
    assert "not a judgement" in reason.lower()
    # The old phrasing, which must never come back.
    assert "humility concern" not in reason.lower()
    assert "abort" not in reason.lower()
    # Names the category so an operator knows where to look.
    assert "TIMEOUT" in reason


def test_an_unrecognised_error_is_not_treated_as_transport() -> None:
    """Conservative by design.

    The dangerous direction is calling a real judgement "transport" and skipping
    it. An unclassified failure keeps the old fail-closed behaviour.
    """

    class Weird(Exception):
        pass

    assert not is_transport_failure(Weird("something we have never seen"))


@pytest.mark.parametrize("shard", LLM_SHARDS)
def test_every_llm_shard_routes_through_the_shared_handler(shard: str) -> None:
    """DRY, asserted structurally rather than trusted.

    Four shards had four different failure behaviours. One handler means one
    behaviour; this fails if a shard grows its own again.
    """
    src = CORE.read_text(encoding="utf-8")
    assert f'unavailable_result("{shard}"' in src, f"{shard} does not fail fast through the shared transport handler"


def test_no_shard_still_fabricates_abort_on_a_bare_exception() -> None:
    """The specific shape that caused #1049.

    Every `except Exception` around an LLM call must consult
    is_transport_failure BEFORE constructing any result, or a timeout becomes a
    veto again.
    """
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body_src = ast.dump(ast.Module(body=node.body, type_ignores=[]))
        constructs_result = "OptimizationVetoResult" in body_src or "EpistemicHumilityResult" in body_src
        consults_policy = "is_transport_failure" in body_src
        if constructs_result and not consults_policy:
            offenders.append(node.lineno)
    assert not offenders, (
        f"except handler(s) at line(s) {offenders} build a conscience verdict without first checking "
        "is_transport_failure() — a provider timeout would be reported as a principled veto again"
    )


def test_the_processor_does_not_retry_an_unavailable_conscience() -> None:
    """Defect 2: the retry loop had no exit.

    Asserted against the predicate directly rather than by driving a whole
    thought, so it stays a unit test and still pins the behaviour that hung the
    turn.
    """
    src = (REPO / "ciris_engine/logic/processors/core/thought_processor/main.py").read_text(encoding="utf-8")
    fn = src[src.index("def _should_retry_with_conscience_guidance") :]
    fn = fn[: fn.index("\n    async def ")]
    assert "conscience_unavailable" in fn, "the retry predicate ignores whether the conscience actually ran"
    assert "return False" in fn


def test_the_unavailable_flag_reaches_the_processor() -> None:
    """The flag is only useful if the override path sets it."""
    src = (
        REPO / "ciris_engine/logic/processors/core/thought_processor/conscience_execution.py"
    ).read_text(encoding="utf-8")
    assert "conscience_unavailable = True" in src
    assert "conscience_unavailable=conscience_unavailable" in src
