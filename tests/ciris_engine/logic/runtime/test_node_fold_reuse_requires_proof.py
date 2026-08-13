"""Reusing a live `:4243` requires proof that it is ours — not merely an open socket.

`node_fold` already hard-errors when it can READ the node's identity and ours is
absent. The hole was the other arm: when identity could not be read at all, it
logged a warning and reused anyway, "preserving the in-process-restart path".

A check whose negative result changes nothing is the same shape as no check, and
CI paid for it. Staged QA run 31657050917:

    postgres 01:17  Node fold: 4243 already serving but identity could not be
                    confirmed (no readable /v1/self/identity …)   ← reused it
    postgres 01:20  auth proxy could not reach the node at 127.0.0.1:4243
    sqlite   01:27  Node fold: … (post-bind) … OWNERSHIP UNCLAIMED — CLAIM PIN

Two legs of one job, one fixed port. Whichever ran first inherited a node it could
not identify and lost it mid-run; the leg that bound its own passed the identical
suite. That asymmetry read as a database problem for hours and was ordering.

THE FIX IS NOT "PROBE HARDER". The restart the reuse branch exists for happens
INSIDE this process, so it is answerable without the network: module globals
survive it, and `_folded_in_this_process` with them. A live `:4243` while that
flag is False belongs to someone else, whatever its endpoints do or do not say.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest

from ciris_engine.logic.runtime import node_fold


@pytest.fixture
def own_listener():
    """A listener on 4243 held by THIS process — the in-process-restart shape.

    Socket ownership is the discriminator, so the fixtures differ only in WHO
    holds the socket. A Python-side flag could not tell these apart: the restart
    this branch serves re-imports the module and wipes any such flag, which is
    stated in node_fold's own comment and is why the first version of this fix
    was wrong.
    """
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", 4243))
    except OSError:  # pragma: no cover - a real node is running on this box
        s.close()
        pytest.skip("port 4243 already in use")
    s.listen(8)
    with closing(s):
        yield s


@pytest.fixture
def foreign_listener():
    """A listener on 4243 held by a DIFFERENT process — the CI shape.

    A child process, not a thread: the point is that the socket belongs to
    another pid, which is precisely what /proc fd matching detects and what an
    open-socket probe cannot.
    """
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import socket,time\n"
            "s=socket.socket()\n"
            "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n"
            "s.bind(('127.0.0.1',4243)); s.listen(8); time.sleep(60)",
        ]
    )
    for _ in range(50):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", 4243)) == 0:
                break
        time.sleep(0.1)
    else:  # pragma: no cover
        child.kill()
        pytest.skip("could not stand up a foreign listener on 4243")
    try:
        yield child
    finally:
        child.kill()
        child.wait(timeout=5)


@pytest.fixture(autouse=True)
def _fold_enabled(monkeypatch):
    """tests/conftest.py sets CIRIS_NODE_FOLD=false globally.

    Without this, `start_node_fold` returns at its first line and EVERY assertion
    here passes by not running — which is how the first version of this file
    reported green on a guard that had never executed. A test that cannot reach
    the code it names is worse than absent: it certifies the opposite of what it
    checks.
    """
    monkeypatch.setenv("CIRIS_NODE_FOLD", "true")
    monkeypatch.setattr(node_fold, "_node_thread", None, raising=False)


def test_refuses_a_live_node_this_process_does_not_own(foreign_listener, tmp_path):
    """The CI failure, as a test."""
    with pytest.raises(RuntimeError) as exc:
        node_fold.start_node_fold(8080, home=str(tmp_path))

    message = str(exc.value)
    assert "not ours" in message, "the refusal must say WHY, not just that it refused"
    assert "NOT held by this process" in message, (
        "the operator needs the distinguishing fact — that we do not own the socket — "
        "or the message is indistinguishable from a transient probe failure"
    )


def test_still_reuses_on_a_genuine_in_process_restart(own_listener, tmp_path):
    """The path the branch exists for, which the fix must not cost.

    Mobile restarts the runtime in-process; the node keeps serving on its own
    tokio thread. Refusing here would break a real, shipped flow to fix CI —
    trading one product defect for another.
    """
    # Must not raise. Downstream reprime/PIN steps are allowed to no-op in a bare
    # test process; the assertion is about the reuse DECISION, not its sequel.
    node_fold.start_node_fold(8080, home=str(tmp_path))


def test_the_flag_is_the_discriminator_not_the_probe() -> None:
    """Structural: the guard must not depend on reaching the network.

    A probe-based guard fails open exactly when the network is unhealthy, which is
    when a stale node is most likely to be sitting there. The in-process fact does
    not have that failure mode.
    """
    import inspect

    source = inspect.getsource(node_fold.start_node_fold)
    guard = source[source.index("if not identity_text:") :]
    assert "_this_process_owns_port" in guard[:2500], (
        "the cannot-read-identity arm no longer consults socket ownership — it is "
        "back to warning-and-reusing, which is what CI caught"
    )
