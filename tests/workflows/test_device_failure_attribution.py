"""Which layer died — the automation server, or the whole app process?

Run 33704781359 could not answer that. Android's TestAutomationServer answered
/health with testMode=true, then returned RemoteProtocolError seconds later. On
Android the automation port is reached through an adb forward, and adb accepts
on the HOST socket before it tries the device — so a dead device-side port and
a live server with a dead handler produce the identical error. The owner of the
bug differs in each case, and the host-side evidence could not distinguish them.

The sibling listener settles it, so these tests drive both verdicts for real
rather than reading the source.
"""

from __future__ import annotations

import asyncio
import http.server
import socket
import threading
from contextlib import closing

import pytest

from tools.qa_runner.modules.web_ui.desktop_app_helper import attribute_device_failure


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def live_backend():
    port = _free_port()
    srv = http.server.HTTPServer(("127.0.0.1", port), _Health)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://localhost:{port}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_backend_alive_means_only_the_automation_server_died(live_backend) -> None:
    """Process alive => the automation surface is the thing to look at."""
    verdict = asyncio.run(attribute_device_failure("http://localhost:9091", live_backend))
    assert "PROCESS IS ALIVE" in verdict
    assert "automation server" in verdict
    assert "process death" in verdict  # tells the reader where NOT to look


def test_backend_gone_means_the_process_died(live_backend) -> None:
    """Both listeners gone => a process kill, not an accept-loop bug.

    Uses a port that was just bound and released, so nothing is listening —
    the same observable state as an app the OS killed.
    """
    dead = f"http://localhost:{_free_port()}"
    verdict = asyncio.run(attribute_device_failure("http://localhost:9091", dead))
    assert "PROCESS IS GONE" in verdict
    assert "OOM" in verdict or "low-memory" in verdict


def test_the_two_verdicts_are_actually_different(live_backend) -> None:
    """Guard against a helper that returns one string for both states.

    A discriminator that cannot discriminate is the exact failure it exists to
    prevent — it would read as an authoritative attribution while carrying no
    information.
    """
    alive = asyncio.run(attribute_device_failure("http://localhost:9091", live_backend))
    gone = asyncio.run(attribute_device_failure("http://localhost:9091", f"http://localhost:{_free_port()}"))
    assert alive != gone
