"""free_ports distinguishes a LIVE LISTENER from TIME_WAIT residue.

Both make a strict (no SO_REUSEADDR) bind fail; only one of them means the
previous platform's backend is still serving. Conflating them cost the android
leg of run 34291675402: killing linux's backend left :8080 and :4243 in
TIME_WAIT, the strict probe called them held, no listener existed to name
("holder unknown"), and the teardown guard skipped android as though a stale
backend were up.

NOTE FOR WHOEVER EDITS THIS: never hold the listening socket in the test
process. The tool kills whatever listens on the port it is given, and the first
version of this file duly had it SIGKILL pytest.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dev.free_ports import bindable, bindable_reuse  # noqa: E402

TOOL = [sys.executable, str(ROOT / "tools" / "dev" / "free_ports.py")]
_LISTENER = (
    "import socket,sys,time;"
    "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
    "s.bind(('127.0.0.1',int(sys.argv[1])));s.listen(1);print('up',flush=True);time.sleep(120)"
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_a_free_port_passes_both_probes() -> None:
    port = _free_port()
    assert bindable(port) and bindable_reuse(port)


def test_a_live_listener_fails_both_probes() -> None:
    """Probe functions only — no tool run, nothing is killed."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert not bindable(port), "a listening socket must fail the strict probe"
        assert not bindable_reuse(port), "and must fail the SO_REUSEADDR probe, which is what makes it a REAL holder"
    finally:
        srv.close()


def test_the_tool_kills_a_listener_it_can_see() -> None:
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", _LISTENER, str(port)], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "up"
        r = subprocess.run(TOOL + [str(port), "--timeout", "10", "--label", "t"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout
        assert "verified free" in r.stdout
        assert proc.poll() is not None or proc.wait(timeout=5) is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_time_wait_residue_is_reported_and_is_not_a_failure() -> None:
    """The real shape: an ACCEPTED connection on the listening port, closed by the
    server side, leaves that port in TIME_WAIT after the listener is gone.

    A strict bind fails while nothing listens — the state the teardown misread as
    "a stale backend is still serving". The SO_REUSEADDR exemption applies here
    (the accepted socket inherits the option from the listener, as uvicorn's and
    the node's do), so the next server binds it fine.
    """
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    cli = socket.socket()
    cli.connect(srv.getsockname())
    conn, _ = srv.accept()
    srv.close()   # the listener dies, as the teardown's kill does
    conn.close()  # server closes first: THIS port goes TIME_WAIT
    cli.close()
    time.sleep(0.3)

    if bindable(port):  # pragma: no cover - the kernel released it early
        return
    assert bindable_reuse(port), "a server-side TIME_WAIT must still accept an SO_REUSEADDR bind"
    r = subprocess.run(TOOL + [str(port), "--timeout", "2", "--label", "t"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "TIME_WAIT" in r.stdout and "the next server will bind these" in r.stdout
