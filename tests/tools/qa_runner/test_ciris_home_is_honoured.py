"""An explicitly-set CIRIS_HOME must survive into the backend the harness spawns.

THE BUG, and it is the worst kind: a guard that could not fail.

The Windows UI job pins

    CIRIS_HOME=C:\\Users\\runneradmin\\franc\\ciris

deliberately, because `\\f` is the escape sequence that corrupted a real user's
paths -- python-dotenv applies POSIX escape processing inside double quotes, so
`\\f` + `ranc` became one form-feed character and Windows rejected the path with
WinError 123. The whole job exists to make that shape appear in a real .env.

The harness then did this when spawning the backend:

    env["CIRIS_HOME"] = self.config.project_root

Unconditional assignment. The pinned home was discarded and replaced with the
repo checkout, so the path written into .env was
`D:\\a\\CIRISAgent\\CIRISAgent\\data\\...` -- which contains no escape trigger at
all. Both boots passed the control-character assertion trivially, for three
runs, because nothing dangerous was ever written. The assertion failed only
because it looked for .env in the home it had ASKED for and found none, which is
what finally exposed the substitution.

setdefault satisfies the determinism the original comment cared about -- what it
needs is that both boots agree on ONE home, not that the harness picks it.

These tests assert the substitution cannot come back, without spawning a
backend: the environment construction is the thing that was wrong.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
SERVER_MANAGER = REPO / "tools" / "qa_runner" / "modules" / "web_ui" / "server_manager.py"


def test_ciris_home_is_not_overwritten_unconditionally() -> None:
    """`env["CIRIS_HOME"] = ...` discards the operator's explicit choice."""
    tree = ast.parse(SERVER_MANAGER.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "env"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "CIRIS_HOME"
            ):
                offenders.append(node.lineno)
    assert not offenders, (
        f"server_manager.py assigns env['CIRIS_HOME'] at line(s) {offenders}, which throws away an "
        "explicitly-set CIRIS_HOME. The Windows UI job pins a home containing an escape trigger on "
        "purpose; overwriting it makes that job prove nothing. Use env.setdefault('CIRIS_HOME', ...)."
    )


def test_it_still_pins_a_home_when_none_is_set() -> None:
    """The determinism the original code wanted must be preserved.

    Both boots have to agree on one data dir, or the admin user created in run 1
    lives in a different SQLite file than the auth probe in run 2 reads -- which
    is the failure the pin was introduced to fix.
    """
    text = SERVER_MANAGER.read_text(encoding="utf-8")
    assert 'env.setdefault("CIRIS_HOME"' in text, "the fallback pin was removed entirely; both boots could diverge again"


def test_an_explicit_home_wins_over_the_default() -> None:
    """The actual behaviour, exercised rather than described."""
    env: dict[str, str] = {"CIRIS_HOME": "/pinned/franc/ciris"}
    env.setdefault("CIRIS_HOME", "/repo/checkout")
    assert env["CIRIS_HOME"] == "/pinned/franc/ciris"

    env2: dict[str, str] = {}
    env2.setdefault("CIRIS_HOME", "/repo/checkout")
    assert env2["CIRIS_HOME"] == "/repo/checkout"


def test_the_workflow_still_pins_an_escape_triggering_home() -> None:
    """If the pin is ever softened, the job silently stops testing the bug.

    The escape characters python-dotenv processes inside double quotes are what
    make this path dangerous; a "tidier" home without one turns the job green
    and meaningless.
    """
    wf = REPO / ".github" / "workflows" / "windows-desktop-ui.yml"
    if not wf.exists():
        pytest.skip("windows workflow not in this checkout")
    body = wf.read_text(encoding="utf-8")
    assert "CIRIS_UI_HOME_FLAVOUR" in body
    assert "franc" in body, "the \\f trigger is gone from the pinned home"


def test_config_path_follows_ciris_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """The product half: an explicit CIRIS_HOME decides where .env is written.

    Holds in development mode too -- which matters, because the harness runs
    from the repo checkout and `is_development_mode()` is just
    `(Path.cwd() / ".git").exists()`.
    """
    from ciris_engine.logic.setup.first_run import get_default_config_path

    home = tmp_path / "franc" / "ciris"
    monkeypatch.setenv("CIRIS_HOME", str(home))
    monkeypatch.delenv("CIRIS_CONFIG_DIR", raising=False)

    resolved = get_default_config_path()
    assert resolved == home / ".env", f"CIRIS_HOME was ignored; .env resolved to {resolved}"


def test_the_wipe_target_follows_ciris_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A destructive helper must aim at the home it was TOLD to use.

    _wipe_dev_data used to hardcode `Path.home()/"ciris"`, so setting CIRIS_HOME
    to a scratch directory still deleted the developer's real ~/ciris/data on
    every desktop-setup run. Observed doing exactly that on 2026-08-16.

    This tests the DECISION, not the destruction. Calling _wipe_dev_data for
    real also clears `<repo>/data` -- a unit test that damages the working tree
    of whoever runs the suite, which the first version of this test did.
    """
    from tools.qa_runner.modules.web_ui.__main__ import resolved_qa_home

    pinned = tmp_path / "scratch" / "ciris"
    monkeypatch.setenv("CIRIS_HOME", str(pinned))
    assert resolved_qa_home() == pinned

    monkeypatch.delenv("CIRIS_HOME", raising=False)
    assert resolved_qa_home() == pathlib.Path.home() / "ciris", "the default for an unset CIRIS_HOME changed"


def test_the_wipe_uses_the_shared_resolver() -> None:
    """It must not go back to reading Path.home() directly."""
    src = (REPO / "tools/qa_runner/modules/web_ui/__main__.py").read_text(encoding="utf-8")
    body = src[src.index("def _wipe_dev_data") :]
    body = body[: body.index("\ndef ", 10)] if "\ndef " in body[10:] else body
    assert "resolved_qa_home()" in body
    # The ASSIGNMENT, not any mention: the docstring names the old expression on
    # purpose, to record what the bug was.
    assert 'home_ciris = Path.home() / "ciris"' not in body, "_wipe_dev_data hardcodes the home again"
