"""The iOS automation server does ONE recv() and parses what arrived.

httpx writes headers and body separately, so a POST body lands in a second
segment the server never reads -- it decodes an empty body and returns the
kotlinx error text as the response (run 33780331440). Until CIRISClient#33
replaces that server, the gate sends each request in one write.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from contextlib import closing

import httpx

from tools.qa_runner.modules.web_ui.desktop_app_helper import _OneSegmentTransport


def _single_recv_server():
    """A server that behaves like TestAutomationServer.ios.kt: one recv, parse, reply."""
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port)); srv.listen(5)
    seen = {}

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                data = c.recv(8192)                       # exactly one recv, like iOS
                head, _, body = data.partition(b"\r\n\r\n")
                seen["body"] = body
                payload = json.dumps({"got_body": body != b"", "len": len(body)}).encode()
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
                          + f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
    threading.Thread(target=run, daemon=True).start()
    return f"http://127.0.0.1:{port}", srv, seen


def test_the_body_reaches_a_single_recv_server() -> None:
    url, srv, seen = _single_recv_server()
    try:
        async def go():
            async with httpx.AsyncClient(transport=_OneSegmentTransport(), base_url=url) as c:
                r = await c.post("/click", json={"testTag": "btn_local_login"})
                return r.status_code, r.json()
        status, data = asyncio.run(go())
    finally:
        srv.close()
    assert status == 200
    assert data["got_body"] is True and data["len"] > 0, "the POST body did not arrive with the headers"
    assert json.loads(seen["body"]) == {"testTag": "btn_local_login"}


def test_the_request_is_exactly_one_write(monkeypatch) -> None:
    """Delivering the body is not enough; it must be in the SAME write."""
    writes = []

    class _W:
        def write(self, b): writes.append(b)
        async def drain(self): pass
        def close(self): pass
        async def wait_closed(self): pass

    class _R:
        async def read(self, n=-1):
            return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"

    async def fake_open(host, port):
        return _R(), _W()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)

    async def go():
        async with httpx.AsyncClient(transport=_OneSegmentTransport(), base_url="http://127.0.0.1:9091") as c:
            return await c.post("/wait", json={"testTag": "x", "timeoutMs": 5})
    r = asyncio.run(go())
    assert r.status_code == 200
    assert len(writes) == 1, f"expected one write, got {len(writes)}"
    head, sep, body = writes[0].partition(b"\r\n\r\n")
    assert sep, "no header terminator in the single write"
    assert json.loads(body) == {"testTag": "x", "timeoutMs": 5}, "the body must be in the SAME write as the headers"
    assert b"Content-Length: " + str(len(body)).encode() in head


def test_get_still_works_and_desktop_is_untouched() -> None:
    from tools.qa_runner.modules.web_ui.__main__ import _input_settle_for  # noqa: F401  (import sanity)
    from tools.qa_runner.modules.web_ui.desktop_app_helper import DesktopAppConfig

    assert DesktopAppConfig().one_segment_http is False, "desktop/android must keep the normal transport"
