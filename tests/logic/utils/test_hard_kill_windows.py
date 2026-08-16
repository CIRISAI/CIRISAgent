"""The kill switch must actually kill, including on Windows.

THE BUG. Every ACCORD termination path ran

    os.kill(os.getpid(), signal.SIGKILL)

and `signal.SIGKILL` does not exist on Windows. The attribute lookup raises
`AttributeError` before `os.kill` is reached, so the kill switch killed nothing
there.

In `base_observer._check_for_accord` this FAILED OPEN, which is the part that
matters. The call sits inside `except Exception`, so on Windows the termination
raised, escaped into `handle_incoming_message`, and was caught by the adapter's
message loop like any other bad message. The agent logged

    CRITICAL FAILURE: Accord check error (...). Agent cannot operate with broken
    kill switch. TERMINATING.

and then carried on serving traffic. The log says the agent stopped. It did not.

WHY THESE TESTS RUN ON LINUX. Every assertion here is about the SHAPE of the
code and the platform-independent behaviour of the helper, so they hold the
invariant on any runner. Nothing here spawns a process to be killed -- a test
that genuinely triggered the switch would take the test runner down with it.
"""

from __future__ import annotations

import ast
import pathlib
import signal
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Paths that terminate the process as a safety action.
KILL_SITES = [
    "ciris_engine/logic/accord/executor.py",
    "ciris_engine/logic/accord/verifier.py",
    "ciris_engine/logic/accord/handler.py",
    "ciris_engine/logic/adapters/base_observer.py",
]


def _bare_sigkill_uses(path: pathlib.Path) -> list[int]:
    """Lines evaluating `signal.SIGKILL` without a hasattr guard nearby.

    AST-based so the long explanatory comments in these files -- which name
    SIGKILL repeatedly and on purpose -- are not findings.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "SIGKILL"
            and isinstance(node.value, ast.Name)
            and node.value.id == "signal"
        ):
            hits.append(node.lineno)
    return hits


@pytest.mark.parametrize("rel", KILL_SITES)
def test_no_kill_site_touches_sigkill_directly(rel: str) -> None:
    """The assertion that would have caught this before a Windows user did."""
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    hits = _bare_sigkill_uses(path)
    assert not hits, (
        f"{rel} evaluates signal.SIGKILL at line(s) {hits}; that attribute does not "
        "exist on Windows and raises AttributeError before the process is killed. "
        "Use terminate_immediately() from ciris_engine.logic.utils.hard_kill."
    )


@pytest.mark.parametrize("rel", KILL_SITES)
def test_every_kill_site_uses_the_shared_helper(rel: str) -> None:
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    assert "terminate_immediately" in path.read_text(encoding="utf-8"), f"{rel} has no terminating path routed through the shared helper"


def test_helper_is_typed_NoReturn() -> None:
    """Callers and mypy must both know control does not come back.

    If it were typed as returning, code after a kill site would look reachable
    and someone would eventually write a `return` there that never runs.
    """
    import inspect

    from ciris_engine.logic.utils.hard_kill import terminate_immediately

    assert "NoReturn" in str(inspect.signature(terminate_immediately).return_annotation) or (
        terminate_immediately.__annotations__.get("return").__name__ == "NoReturn"  # type: ignore[union-attr]
    )


def test_it_really_terminates_and_is_not_catchable() -> None:
    """A subprocess proves the semantics -- os._exit is not `raise SystemExit`.

    `sys.exit()` raises SystemExit, which a bare `except:` anywhere on the stack
    swallows. A kill switch a downstream try can veto is not a kill switch, so
    the child wraps the call in `except BaseException` and prints if it survives.
    """
    child = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, %r)
        from ciris_engine.logic.utils.hard_kill import terminate_immediately
        try:
            terminate_immediately("test")
        except BaseException:
            print("SURVIVED")
        print("REACHED_END")
        """
        % str(REPO)
    )
    proc = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=60)
    assert "SURVIVED" not in proc.stdout, "termination was catchable -- a bare except can veto the kill switch"
    assert "REACHED_END" not in proc.stdout, "control returned from terminate_immediately"
    assert proc.returncode != 0


def test_exit_code_matches_a_killed_process() -> None:
    """137 == 128 + SIGKILL(9), so supervisors see one code from both platforms.

    On POSIX the child is really SIGKILLed, which subprocess reports as -9.
    """
    child = f"import sys; sys.path.insert(0, {str(REPO)!r})\nfrom ciris_engine.logic.utils.hard_kill import terminate_immediately\nterminate_immediately('x')"
    proc = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=60)
    if hasattr(signal, "SIGKILL"):
        assert proc.returncode in (-9, 137), f"expected SIGKILL or 137, got {proc.returncode}"
    else:
        assert proc.returncode == 137


def test_a_broken_log_handler_cannot_veto_the_kill() -> None:
    """Flushing is best-effort by design.

    The helper flushes so the CRITICAL reason survives, but a handler that
    raises must not keep a process alive that has been ordered to die.
    """
    child = textwrap.dedent(
        """
        import logging, sys
        sys.path.insert(0, %r)

        class Exploding(logging.Handler):
            def emit(self, record): raise RuntimeError("boom")
            def flush(self): raise RuntimeError("boom")

        logging.getLogger().addHandler(Exploding())
        from ciris_engine.logic.utils.hard_kill import terminate_immediately
        try:
            terminate_immediately("test")
        except BaseException:
            print("SURVIVED")
        print("REACHED_END")
        """
        % str(REPO)
    )
    proc = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=60)
    assert "SURVIVED" not in proc.stdout
    assert "REACHED_END" not in proc.stdout


def test_the_fail_open_site_is_documented_as_such() -> None:
    """base_observer is the one that kept serving traffic; keep that visible.

    A future refactor that reintroduces a raising call here would be a security
    regression, not a style change, and the comment is what tells the next
    reader that.
    """
    text = (REPO / "ciris_engine/logic/adapters/base_observer.py").read_text(encoding="utf-8")
    assert "FAILED OPEN" in text
