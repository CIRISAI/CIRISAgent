"""success:true from /input means the request was POSTED, not that the field changed.

On mobile the request goes onto a StateFlow, which keeps only the latest
value; the Compose field applies it when it next collects. Three inputs in
quick succession can leave the first two applied to nothing -- every call
acknowledged, the wizard refusing to advance because a required field is empty
(run 33708152999, you_step, Android). So the helper reads the field back.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import socket
import threading
from contextlib import closing

import httpx
import pytest

from tools.qa_runner.modules.web_ui.desktop_app_helper import DesktopAppHelper, _looks_secret


class _FakeClient(http.server.BaseHTTPRequestHandler):
    """A test server that acknowledges every /input; whether it APPLIES is configurable."""

    applies = True
    fields: dict = {}

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/input":
            if type(self).applies:
                type(self).fields[req["testTag"]] = req["text"]
            self._send({"success": True})
        else:
            self._send({"success": False, "error": "unknown"})

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/element/"):
            tag = self.path.rsplit("/", 1)[1]
            self._send({"success": True, "testTag": tag, "x": 0, "y": 0, "width": 1, "height": 1,
                        "centerX": 0, "centerY": 0, "text": type(self).fields.get(tag, "")})
        else:
            self._send({"success": False, "error": "nope"})

    def log_message(self, *a):
        pass


@pytest.fixture
def fake():
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    _FakeClient.fields = {}
    _FakeClient.applies = True
    srv = http.server.HTTPServer(("127.0.0.1", port), _FakeClient)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown(); srv.server_close()


def _helper(url: str) -> DesktopAppHelper:
    h = DesktopAppHelper.__new__(DesktopAppHelper)
    h._client = httpx.AsyncClient(base_url=url, timeout=5.0)
    return h


def test_an_input_that_is_applied_passes(fake) -> None:
    assert asyncio.run(_helper(fake).input_text("input_username", "qaadmin"))


def test_an_input_that_is_acknowledged_but_never_applied_fails(fake) -> None:
    """THE CASE. The client says success; the field never changes."""
    _FakeClient.applies = False
    with pytest.raises(RuntimeError, match="acknowledged but .* never applied"):
        asyncio.run(_helper(fake)._verify_input_landed("input_username", "qaadmin", budget_s=0.5))


def test_a_stale_value_from_an_earlier_input_is_not_accepted(fake) -> None:
    """Coalescing leaves the PREVIOUS value in place; that must not read as success."""
    _FakeClient.fields["input_username"] = "someone_else"
    _FakeClient.applies = False
    with pytest.raises(RuntimeError, match="'someone_else', not 'qaadmin'"):
        asyncio.run(_helper(fake)._verify_input_landed("input_username", "qaadmin", budget_s=0.5))


@pytest.mark.parametrize("tag", ["input_password", "input_password_confirm", "input_api_key", "input_token"])
def test_masked_fields_are_not_pretended_to_be_verified(tag) -> None:
    assert _looks_secret(tag)


def test_username_and_message_fields_are_verified() -> None:
    assert not _looks_secret("input_username")
    assert not _looks_secret("input_message")
    assert not _looks_secret("input_fedid_label")
