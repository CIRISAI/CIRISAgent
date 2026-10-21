"""Two ways a green platform reported red for reasons that were ours.

iOS: the first time its test server ever answered in CI, every response failed
strict JSON parsing on a raw control character, and the driver died before it
could say which route or which bytes (run 33777943107).

macOS: the model dropdown was read 0.6s after opening it and reported "0
offered" while the client's own log said it had listed 425 models. The tree
had not caught up yet.
"""

from __future__ import annotations

import inspect
import json

import httpx
import pytest

from tools.qa_runner.modules.web_ui.desktop_app_helper import _json


def _resp(body: bytes, path: str = "/screen") -> httpx.Response:
    req = httpx.Request("GET", f"http://localhost:9091{path}")
    return httpx.Response(200, content=body, request=req)


def test_a_raw_control_character_is_tolerated_and_reported(capsys) -> None:
    body = b'{"success": true, "screen": "Setup\nwizard"}'   # raw newline inside a string
    with pytest.raises(json.JSONDecodeError):
        json.loads(body)                                       # strict: this IS invalid JSON
    data = _json(_resp(body))
    assert data["screen"] == "Setup\nwizard"
    out = capsys.readouterr().out
    assert "invalid JSON" in out and "/screen" in out, "the fault must be named"
    assert "\\\\n" in out or "\\n" in out, "the offending bytes must be quoted, escaped"


def test_genuinely_broken_json_still_raises() -> None:
    with pytest.raises(ValueError):
        _json(_resp(b'{"success": tru'))


def test_valid_json_is_untouched_and_silent(capsys) -> None:
    assert _json(_resp(b'{"success": true}')) == {"success": True}
    assert capsys.readouterr().out == ""


def test_the_model_dropdown_is_polled_not_slept() -> None:
    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m.DesktopAppTestRunner)
    i = src.index('self.helper.click("input_llm_model")')
    after = src[i:i + 900]
    assert 'startswith("menu_model_")' in after
    assert "while time.time() < _deadline" in after, "must poll for the menu items"
    assert "await asyncio.sleep(0.6)\n" not in after, "the fixed sleep is the bug"
