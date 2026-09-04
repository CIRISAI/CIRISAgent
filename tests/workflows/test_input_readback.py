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

from tools.qa_runner.modules.web_ui.desktop_app_helper import DesktopAppConfig, DesktopAppHelper, _looks_secret


class _FakeClient(http.server.BaseHTTPRequestHandler):
    """A test server that acknowledges every /input; whether it APPLIES is configurable."""

    applies = True
    omit_text = False
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
            body = {"success": True, "testTag": tag, "x": 0, "y": 0, "width": 1, "height": 1,
                    "centerX": 0, "centerY": 0}
            if not getattr(type(self), "omit_text", False):
                body["text"] = type(self).fields.get(tag, "")
            self._send(body)
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


def _helper(url: str, settle: float = 0.0) -> DesktopAppHelper:
    h = DesktopAppHelper.__new__(DesktopAppHelper)
    h._client = httpx.AsyncClient(base_url=url, timeout=5.0)
    h.config = DesktopAppConfig(server_url=url, input_settle_s=settle)
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


def test_mobile_settles_between_inputs_and_desktop_does_not() -> None:
    """The delay belongs to the platform, not to whoever remembered it.

    login() slept 2s between fields for this reason; the setup wizard did not,
    so you_step typed username -> password -> confirm back-to-back and the
    password was dropped -- Android stopped on "Password is required" with every
    call reporting success.
    """
    from tools.qa_runner.modules.web_ui.__main__ import _input_settle_for

    assert _input_settle_for("android") >= 2.0
    assert _input_settle_for("ios") >= 2.0
    for desktop in ("desktop", "linux", "macos", "windows"):
        assert _input_settle_for(desktop) == 0.0, f"{desktop} applies input synchronously"


def test_the_settle_is_actually_waited(fake) -> None:
    """Config alone proves nothing; input_text must honour it."""
    import time as _t

    h = _helper(fake, settle=0.4)
    t0 = _t.monotonic()
    asyncio.run(h.input_text("input_username", "qaadmin"))
    assert _t.monotonic() - t0 >= 0.4, "input_settle_s was ignored"


def test_no_settle_costs_nothing_on_desktop(fake) -> None:
    import time as _t

    h = _helper(fake, settle=0.0)
    t0 = _t.monotonic()
    asyncio.run(h.input_text("input_username", "qaadmin"))
    assert _t.monotonic() - t0 < 0.4


def test_a_client_that_omits_text_is_concluded_immediately(fake) -> None:
    """Not slow -- structural. Polling 3s per field to learn the same thing
    costs the wizard ten seconds on the slowest platform."""
    import time as _t

    class _NoText(type(_FakeClient)):
        pass

    _FakeClient.omit_text = True
    try:
        h = _helper(fake)
        t0 = _t.monotonic()
        asyncio.run(h._verify_input_landed("input_username", "qaadmin", budget_s=3.0))
        assert _t.monotonic() - t0 < 1.0, "burned the whole budget on a structural fact"
    finally:
        _FakeClient.omit_text = False


def test_the_you_step_advance_is_detected_by_the_next_steps_control() -> None:
    """Absence in a registry that never forgets is not evidence.

    iOS registers elements and never unregisters them (CIRISClient#33), so
    waiting for the age band to vanish reported "still on the YOU step" for the
    full budget while join_federation found its toggle 0.8s later (runs
    33782490319, 33784560419). The next step's own control appearing is the
    signal, on every platform.
    """
    import inspect

    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m.DesktopAppTestRunner)
    # The LAST occurrence: the phrase also appears in the comment that explains
    # this fix, which precedes the code. The raise is what we anchor on.
    i = src.rindex("still on the YOU step")
    loop = src[i - 1500:i]
    assert 'is_element_visible("toggle_announce_ownership")' in loop, "advance must be detected positively"
    assert "while await self.helper.is_element_visible(band_tag)" in loop
