"""One fault must produce one red.

Nightly 34596459034: the Windows desktop test server was unreachable once, and
the leg reported FOUR failures — setup-noai, login-noai, reset, each classified
UNKNOWN — because the no-AI legs ran unconditionally against an app that was
never driveable. The three downstream reds read as client defects (CIRISAgent#1172).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/five-platform-live-qa.yml"


def _driving_step() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text())
    for job in doc["jobs"].values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and "Run the shared flow" in str(step.get("name", "")):
                return step["run"]
    raise AssertionError("driving step not found")


GUARD = 'if [ "$noai_ok" = 1 ]; then'


def _guarded_block(body: str, needle: str) -> str:
    """The enclosing `if [ "$noai_ok" = 1 ] ... fi` around `needle`.

    Bounded by the guard and its `fi` rather than a byte window, so a longer
    command or another comment cannot make this assert the wrong thing.
    """
    i = body.index(needle)
    start = body.rfind(GUARD, 0, i)
    assert start != -1, f"{needle!r} is not inside a {GUARD!r} block"
    # YAML block scalars strip the common indent, so match `fi` at any depth
    # rather than at the indentation it happens to have in the file.
    m = re.search(r"\n\s*fi\s*\n", body[i:])
    assert m, f"no `fi` closes the block around {needle!r}"
    return body[start : i + m.end()]


def test_setup_noai_records_its_verdict():
    body = _driving_step()
    line = next(l for l in body.splitlines() if "run-without-AI setup failed" in l)
    assert "noai_ok=0" in line, "setup-noai must record the verdict, not only count it"


def test_the_flag_is_reset_per_platform():
    """The loop walks two platforms per runner; a stale flag would skip the second."""
    body = _driving_step()
    assert re.search(r"^\s*noai_ok=1\s*$", body, re.M), "noai_ok must be initialised inside the loop"
    init = body.index("noai_ok=1")
    assert init < body.index("run-without-AI setup failed"), "initialise before the first use"


def test_login_noai_only_runs_when_setup_noai_succeeded():
    body = _driving_step()
    ctx = _guarded_block(body, "desktop-login \\")
    assert GUARD in ctx, "the no-AI login must be gated"
    assert "SKIPPED" in ctx, "a skip must be announced, not silent"


def test_reset_is_gated_and_the_home_is_cleared_when_it_cannot_run():
    body = _driving_step()
    ctx = _guarded_block(body, "desktop-reset \\")
    assert GUARD in ctx, "the reset must be gated"
    assert 'rm -rf "$CIRIS_HOME"' in ctx, (
        "when the UI reset cannot run, the home must be cleared so the with-AI " "pass still starts from a known state"
    )


def test_the_with_ai_pass_is_not_gated_on_the_noai_flag():
    """The with-AI pass is the gate's headline assertion and must always run."""
    body = _driving_step()
    withai = body[body.index("# 1. Setup wizard through the real UI") :]
    assert "noai_ok" not in withai, "the with-AI pass must not depend on the no-AI outcome"
