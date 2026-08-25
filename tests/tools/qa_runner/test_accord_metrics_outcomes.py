"""A check that cannot run is not a check that failed.

A live run reported two red tests:

    ❌ Lens Key Registration Check: Lens server returned 404: 404 — lens retired;
       see /v1/identity and /lens/api/v1/*
    ❌ Lens Key ID Consistency: Cannot fetch keys: HTTP 404

Nothing about the agent was wrong. Someone else's service retired an endpoint
and said so in the response body. Reporting that in red is how a suite teaches
its readers that red does not mean anything — and this suite already had a
third red in the same run that DID matter.

The same run also produced:

    ❌ Verb Second Pass Trace:

with nothing after the colon, because the only failure path was
`return False, str(e)` and `str(TimeoutError())` is the empty string.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[3] / "tools/qa_runner/modules/accord_metrics_tests.py"


class TestRetirementIsNotFailure:
    @pytest.mark.parametrize(
        "status,body,expected",
        [
            (404, "404 — lens retired; see /v1/identity and /lens/api/v1/*", True),
            (410, "Gone: retired", True),
            (404, "not found", False),          # an ordinary 404 is still a failure
            (500, "retired", False),            # a 500 mentioning it is not a retirement
            (503, "service unavailable", False),
            (404, "", False),
            (404, None, False),
        ],
    )
    def test_only_a_declared_retirement_counts(self, status, body, expected):
        from tools.qa_runner.modules.accord_metrics_tests import _endpoint_retired

        assert _endpoint_retired(status, body) is expected

    def test_both_lens_checks_route_a_retirement_to_SKIP(self):
        src = MODULE.read_text(encoding="utf-8")
        for fn in ("_test_lens_key_registration", "_test_lens_key_id_consistency"):
            start = src.index(f"async def {fn}")
            body = src[start : src.index("\n    async def ", start + 10)]
            assert "_endpoint_retired" in body, f"{fn} still fails red on a retired endpoint"
            assert "SKIP_PREFIX" in body, f"{fn} does not report the retirement as a skip"

    def test_the_runner_renders_skips_as_their_own_status(self):
        src = MODULE.read_text(encoding="utf-8")
        assert 'startswith(SKIP_PREFIX)' in src
        assert '"[SKIP]"' in src, "a skip must not be recorded as a pass or a fail"
        # and it must stay ASCII: an emoji here kills the process on a Windows
        # cp1252 console, which the repo guards against repo-wide
        assert "⏭" not in src, "the skip marker must be ASCII, like [OK] and [FAIL]"


class TestAFailureAlwaysSaysSomething:
    def test_the_verb_test_names_the_exception_type(self):
        src = MODULE.read_text(encoding="utf-8")
        start = src.index("async def _test_verb_second_pass_traces")
        body = src[start : src.index("\n    async def ", start + 10)]
        assert "type(e).__name__" in body, (
            "an exception whose str() is empty must still be named, or the report reads "
            "'FAIL Verb Second Pass Trace:' with nothing after it"
        )
        assert "verbs captured before the failure" in body, (
            "say how far it got — a stall and a wrong verb look identical otherwise"
        )

    def test_the_generic_loop_names_the_exception_type(self):
        src = MODULE.read_text(encoding="utf-8")
        loop = src[src.index("for name, test_fn in tests:") :]
        loop = loop[: loop.index("\n    async def ")]
        assert "type(e).__name__" in loop
        assert "exc_info=True" in loop, "the traceback belongs in the log even when the message is empty"
