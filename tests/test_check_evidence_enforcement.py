"""A compliance gate that cannot check must not report a pass.

check_evidence.py is presented in build.yml as the CI enforcement for stale
compliance gaps: rows declaring `status=open` are verified against the real
issue state so a claim cannot drift behind the code.

Its first version swallowed every lookup failure. A timeout, a rate limit, or
an unauthenticated `gh` produced an empty dict indistinguishable from "nothing
to check", and `main()` exited 0 — so a total outage of the lookup read as a
clean bill of health. Partial success was the subtler half: one resolvable
issue masked any number of unresolvable ones.

That is precisely the defect this script exists to catch, one level up — a
claim (CI checked the issues) drifted from reality (CI checked nothing).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "check_evidence.py"


def _run(env_overrides: dict, path: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    env.update(env_overrides)
    env["PATH"] = path
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=REPO, env=env, capture_output=True, text=True, timeout=300
    )


class TestUnreadableIssueStates:
    def test_a_token_with_no_gh_fails_rather_than_passing_quietly(self, tmp_path) -> None:
        """The CI shape: GH_TOKEN supplied, lookups impossible."""
        result = _run({"GH_TOKEN": "x"}, str(tmp_path))
        assert result.returncode == 1, (
            "with a token supplied, an unreadable issue state must fail the gate.\n"
            f"stdout={result.stdout[-800:]}\nstderr={result.stderr[-800:]}"
        )
        assert "could not be read" in result.stderr

    def test_without_a_token_it_stays_advisory(self, tmp_path) -> None:
        """A developer with no `gh` still gets the shape checks and is told so."""
        result = _run({}, str(tmp_path))
        assert result.returncode == 0, f"stderr={result.stderr[-800:]}"
        assert "not enforced" in result.stdout
        assert "0/" in result.stdout, "the summary must say how many were actually checked"

    def test_the_summary_never_claims_more_than_it_checked(self, tmp_path) -> None:
        """`N issue states checked` used to be printed with no denominator, so
        'checked some' and 'checked all' looked identical."""
        result = _run({}, str(tmp_path))
        assert "/" in result.stdout.split("issue states")[0].rsplit(",", 1)[-1], (
            f"expected an x/y count in the summary; got {result.stdout!r}"
        )


class TestTheFunctionReportsWhatItCouldNotResolve:
    def test_it_returns_both_halves(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_evidence", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        states, unresolved = module._issue_states(set())
        assert states == {} and unresolved == set(), "no refs means nothing unresolved"

        # `gh` present or not, an unknown repo/issue must land in `unresolved`
        # rather than vanishing.
        states, unresolved = module._issue_states({"NoSuchRepo#999999"})
        assert "NoSuchRepo#999999" in unresolved or states, (
            "a ref must end up in exactly one of the two buckets, never neither"
        )
