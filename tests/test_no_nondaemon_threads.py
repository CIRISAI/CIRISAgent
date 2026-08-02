"""Every production `threading.Thread` must be a daemon (#956).

The intermittent pytest-xdist exit-hang was a non-daemon `threading.Thread`
running a CIRISVerify FFI call in `setup/attestation.py`, joined with a timeout.
When the FFI blocked, the join returned, the test passed under the 60s per-test
timeout, and the still-alive non-daemon thread blocked interpreter exit at
session shutdown — where no per-test timeout applies — until CI's 30-minute job
timeout killed the shard. Silent, and intermittent by which worker drew the
test and whether the FFI happened to block that run.

A non-daemon thread is a promise that the interpreter will WAIT for it before
exiting. Almost nothing in this codebase wants to make that promise: every
background thread here is a best-effort worker (FFI probes joined with a
timeout, init workers) that the process must be free to abandon. So the rule is
simple and enforced statically: every `threading.Thread(...)` in production code
passes `daemon=True`. A thread that genuinely must block exit goes in
`ALLOWLIST` with a comment saying why — which makes the dangerous case a
reviewed, deliberate exception rather than an oversight that costs 30 CI
minutes to rediscover.

Static (AST) rather than runtime because these threads are created deep inside
request/FFI paths that a unit test cannot easily reach, and a grep is unreliable
— `daemon=True` is routinely on the line after the `Thread(` call.
"""

from __future__ import annotations

import ast
import pathlib
from typing import List, Tuple

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
PROD_ROOTS = ("ciris_engine", "ciris_adapters")


def _is_daemon_true(call: ast.Call) -> bool:
    """True iff this Thread(...) call passes a literal daemon=True."""
    return any(
        kw.arg == "daemon" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in call.keywords
    )


def _is_thread_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name == "Thread"


# Threads that legitimately must block interpreter exit. Empty by design — add
# an entry ("relative/path.py", lineno) ONLY with a comment justifying why the
# process must wait for this thread rather than being able to abandon it.
ALLOWLIST: set[Tuple[str, int]] = set()


def _thread_calls_missing_daemon() -> List[str]:
    offenders: List[str] = []
    for root in PROD_ROOTS:
        for path in (PROJECT_ROOT / root).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not _is_thread_call(node):
                    continue
                rel = str(path.relative_to(PROJECT_ROOT))
                if (rel, node.lineno) in ALLOWLIST:
                    continue
                if not _is_daemon_true(node):  # type: ignore[arg-type]
                    offenders.append(f"{rel}:{node.lineno}")
    return offenders


def test_no_nondaemon_production_threads() -> None:
    offenders = _thread_calls_missing_daemon()
    assert not offenders, (
        "Non-daemon threading.Thread(...) found in production code (#956). A non-daemon thread "
        "that hangs blocks interpreter exit and wedges the pytest-xdist shard until the CI job "
        "timeout. Pass daemon=True, or add (path, lineno) to ALLOWLIST with a justification:\n  "
        + "\n  ".join(offenders)
    )


def test_the_attestation_threads_that_caused_956_are_daemon() -> None:
    """Anchor the specific regression, so a revert of the fix fails loudly here."""
    src = (PROJECT_ROOT / "ciris_engine/logic/adapters/api/routes/setup/attestation.py").read_text(encoding="utf-8")
    thread_calls = [n for n in ast.walk(ast.parse(src)) if _is_thread_call(n)]
    assert len(thread_calls) == 3, f"expected the 3 known FFI threads, found {len(thread_calls)}"
    for call in thread_calls:
        assert _is_daemon_true(
            call
        ), f"attestation.py Thread at line {call.lineno} is not daemon=True — reintroduces #956"
