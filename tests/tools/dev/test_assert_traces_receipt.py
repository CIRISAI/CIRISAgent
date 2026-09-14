"""The receipt is authoritative, and UNKNOWN is not failure.

Driven against a real loopback HTTP server rather than a mocked urlopen: the
thing under test is an HTTP conversation with auth, a 503 fallback and a JSON
envelope, and mocking the transport would assert our idea of it instead.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("atrc", ROOT / "tools/dev/assert_traces_reached_canonical.py")
assert _spec and _spec.loader
atrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atrc)


class _Server:
    def __init__(self, receipt_status: int, receipt_body: dict | None):
        self.calls: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep pytest output clean
                pass

            def _send(self, code: int, obj) -> None:
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                outer.calls.append(self.path)
                self._send(200, {"access_token": "t0ken"})

            def do_GET(self):
                outer.calls.append(self.path)
                if receipt_status != 200:
                    self._send(receipt_status, {"detail": "nope"})
                else:
                    self._send(200, {"data": receipt_body})

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _args(port: int, **over):
    base = dict(
        receipt_url=f"http://127.0.0.1:{port}",
        receipt_username="qaadmin",
        receipt_password="pw",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_delivered_is_zero(capsys):
    body = {
        "held_by_every_answering_canonical": True,
        "canonicals": [{"key_id": "c1", "holds_newest": True, "url": "http://h:4243", "url_source": "ip_hint"}],
    }
    with _Server(200, body) as s:
        assert atrc._ask_receipt(_args(s.port)) == 0
        assert "/v1/auth/login" in s.calls
        assert "/v1/system/runtime/delivery-receipt" in s.calls
    assert "PASS" in capsys.readouterr().out


def test_a_canonical_that_answered_and_does_not_hold_it_is_one(capsys):
    body = {
        "held_by_every_answering_canonical": False,
        "canonicals": [
            {"key_id": "c1", "holds_newest": False, "shipped_any": True},
            {"key_id": "c2", "holds_newest": False, "shipped_any": False},
        ],
    }
    with _Server(200, body) as s:
        assert atrc._ask_receipt(_args(s.port)) == 1
    out = capsys.readouterr().out
    assert "behind" in out and "never landed" in out, "the two faults must be told apart in the output"


def test_unknown_is_its_own_code_and_is_not_failure(capsys):
    """THE RULE: None means unknown, not zero. It must not share an exit code
    with 'a canonical said it does not hold it'."""
    body = {
        "held_by_every_answering_canonical": None,
        "canonicals_unreachable": 2,
        "canonicals": [{"key_id": "c1", "error": "connect timeout"}],
    }
    with _Server(200, body) as s:
        rc = atrc._ask_receipt(_args(s.port))
    assert rc == atrc.RECEIPT_UNKNOWN
    assert rc not in (0, 1), "unknown is neither delivered nor failed"
    out = capsys.readouterr().out
    assert "NOT a delivery failure" in out
    assert "canonicals_unreachable" in out


def test_an_older_wheel_falls_back_to_the_ladder(capsys):
    """503 means the accessor does not exist here. Returning None hands the
    question back to the log ladder instead of inventing a verdict."""
    with _Server(503, None) as s:
        assert atrc._ask_receipt(_args(s.port)) is None
    assert "falling back to the ladder" in capsys.readouterr().out


def test_an_unreachable_agent_api_falls_back_rather_than_failing(capsys):
    args = _args(9)  # nothing listening
    assert atrc._ask_receipt(args) is None
    assert "falling back to the ladder" in capsys.readouterr().out


def test_no_credentials_still_asks(capsys):
    """Credentials are optional; an unauthenticated ask should still be made so
    a misconfiguration shows as the endpoint's own 401, not as silence."""
    body = {"held_by_every_answering_canonical": True, "canonicals": []}
    with _Server(200, body) as s:
        assert atrc._ask_receipt(_args(s.port, receipt_username=None, receipt_password=None)) == 0
        assert not [c for c in s.calls if c == "/v1/auth/login"]
