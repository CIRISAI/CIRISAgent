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
        receipt_raw_out=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_delivered_is_zero(capsys):
    body = {
        "held_by_every_answering_canonical": True,
        "canonicals": [{"key_id": "c1", "holds_newest": True, "url": "http://h:4243", "url_source": "ip_hint"}],
    }
    with _Server(200, body) as s:
        assert atrc._ask_receipt(_args(s.port))[0] == 0
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
        assert atrc._ask_receipt(_args(s.port))[0] == 1
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
        rc, _ = atrc._ask_receipt(_args(s.port))
    assert rc == atrc.RECEIPT_UNKNOWN
    assert rc not in (0, 1), "unknown is neither delivered nor failed"
    out = capsys.readouterr().out
    assert "NOT a delivery failure" in out
    assert "canonicals_unreachable" in out


def test_an_older_wheel_falls_back_to_the_ladder(capsys):
    """503 means the accessor does not exist here. Returning None hands the
    question back to the log ladder instead of inventing a verdict."""
    with _Server(503, None) as s:
        assert atrc._ask_receipt(_args(s.port))[0] is None
    assert "falling back to the ladder" in capsys.readouterr().out


def test_an_unreachable_agent_api_falls_back_rather_than_failing(capsys):
    args = _args(9)  # nothing listening
    assert atrc._ask_receipt(args)[0] is None
    assert "falling back to the ladder" in capsys.readouterr().out


def test_no_credentials_still_asks(capsys):
    """Credentials are optional; an unauthenticated ask should still be made so
    a misconfiguration shows as the endpoint's own 401, not as silence."""
    body = {"held_by_every_answering_canonical": True, "canonicals": []}
    with _Server(200, body) as s:
        assert atrc._ask_receipt(_args(s.port, receipt_username=None, receipt_password=None))[0] == 0
        assert not [c for c in s.calls if c == "/v1/auth/login"]


def test_an_unchanged_receipt_is_not_reprinted(capsys):
    """Same state on a re-read prints nothing; only read_at differs and that is not a change."""
    body = {
        "held_by_every_answering_canonical": False,
        "canonicals": [{"key_id": "k1", "holds_newest": False, "shipped_any": False}],
    }
    with _Server(200, body) as s:
        rc1, shown = atrc._ask_receipt(_args(s.port))
        assert rc1 == 1 and shown
        rc2, again = atrc._ask_receipt(_args(s.port), quiet_if_same_as=shown)
        assert rc2 == 1 and again is None
    out = capsys.readouterr().out
    assert out.count("RECEIPT (the canonical's own signed answer)") == 1


def test_a_final_false_prints_the_ladder_as_diagnosis(tmp_path, capsys, monkeypatch):
    """The receipt says WHETHER; the ladder says WHY. A False with no ladder is a verdict with no cause."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "agent.log").write_text("[DELIVERY-PROBE] canonical k1 ROOTED after ~10s\n")
    body = {
        "held_by_every_answering_canonical": False,
        "canonicals": [{"key_id": "k1", "holds_newest": False, "shipped_any": False}],
    }
    with _Server(200, body) as s:
        monkeypatch.setattr(
            "sys.argv",
            [
                "x",
                str(logs),
                "--wait-secs",
                "0",
                "--receipt-url",
                f"http://127.0.0.1:{s.port}",
                "--receipt-username",
                "u",
                "--receipt-password",
                "p",
            ],
        )
        rc = atrc.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "DIAGNOSIS" in out
    assert "ROOTED" in out and "KEX PRESENT" in out, "the ladder must follow the verdict"


# ---------------------------------------------------------------------------
# ENFORCED: authored > 0 (exit 5). 2026-10-09..14 every five-platform run sealed
# nothing and stayed green, because "authored 0" makes the verdict None (exit 4).
# ---------------------------------------------------------------------------

#: The verbatim shape of artifacts/receipt-linux.json from run 38598919104.
_AUTHORED_ZERO_RAW = json.dumps(
    {
        "agents": [{"agent_id_hash": "c8f70e9d32d9223a", "authored": 0, "newest_authored": None}],
        "canonicals": [
            {
                "agents": [{"agent_id_hash": "c8f70e9d32d9223a", "authored": 0, "held": 0, "shipped_any": False}],
                "key_id": "ciris-canonical-1-d7bdeu223k",
                "standing": "answered",
            }
        ],
        "hint": "this node has authored no traces yet",
        "verdict": {"canonicals_answered": 1, "newest_authored_held_by_every_answering_canonical": None},
    }
)


def _main_with(port: int, logs: Path, monkeypatch, *extra: str) -> int:
    monkeypatch.setattr(
        "sys.argv",
        [
            "x",
            str(logs),
            "--wait-secs",
            "0",
            "--receipt-url",
            f"http://127.0.0.1:{port}",
            "--receipt-username",
            "u",
            "--receipt-password",
            "p",
            *extra,
        ],
    )
    return atrc.main()


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    (d / "agent.log").write_text("[DELIVERY-PROBE] canonical k1 ROOTED after ~10s\n")
    return d


def test_authored_zero_fails_when_enforced(logs, monkeypatch, capsys):
    """THE NEGATIVE: the receipt the regression actually produced must now fail."""
    body = {
        "held_by_every_answering_canonical": None,
        "raw_json": _AUTHORED_ZERO_RAW,
        "canonicals": [{"key_id": "ciris-canonical-1-d7bdeu223k", "shipped_any": False}],
    }
    with _Server(200, body) as s:
        rc = _main_with(s.port, logs, monkeypatch, "--require-authored")
    assert rc == atrc.AUTHORED_NONE == 5
    assert "sealed NO traces" in capsys.readouterr().out


def test_authored_zero_without_the_flag_is_still_unknown(logs, monkeypatch):
    """Unchanged default: without --require-authored a None verdict stays exit 4."""
    body = {"held_by_every_answering_canonical": None, "raw_json": _AUTHORED_ZERO_RAW, "canonicals": []}
    with _Server(200, body) as s:
        assert _main_with(s.port, logs, monkeypatch) == atrc.RECEIPT_UNKNOWN


def test_authored_positive_with_unknown_delivery_is_not_failure(logs, monkeypatch):
    """authored > 0 satisfies the enforced rung; delivery stays reported-only (4 is not red)."""
    raw = _AUTHORED_ZERO_RAW.replace('"authored": 0, "newest', '"authored": 2, "newest')
    assert atrc._authored_count({"raw_json": raw}) == 2
    body = {"held_by_every_answering_canonical": None, "raw_json": raw, "canonicals": []}
    with _Server(200, body) as s:
        assert _main_with(s.port, logs, monkeypatch, "--require-authored") == atrc.RECEIPT_UNKNOWN


def test_authored_positive_and_delivered_passes(logs, monkeypatch):
    raw = _AUTHORED_ZERO_RAW.replace('"authored": 0, "newest', '"authored": 1, "newest')
    body = {"held_by_every_answering_canonical": True, "raw_json": raw, "canonicals": []}
    with _Server(200, body) as s:
        assert _main_with(s.port, logs, monkeypatch, "--require-authored") == 0


def test_unreadable_authored_count_fails_closed(logs, monkeypatch, capsys):
    body = {"held_by_every_answering_canonical": None, "canonicals": []}
    with _Server(200, body) as s:
        assert _main_with(s.port, logs, monkeypatch, "--require-authored") == atrc.AUTHORED_NONE
    assert "no readable authored count" in capsys.readouterr().out


def test_ladder_fallback_cannot_satisfy_the_authored_rung(logs, monkeypatch, capsys):
    """An older wheel (503) falls back to the ladder, which knows nothing of sealing: fail closed."""
    (logs / "agent.log").write_text(
        "[DELIVERY-PROBE] canonical k1 ROOTED after ~10s\n"
        "[DELIVERY-PROBE] canonical k1 KEX PRESENT after ~2s post-root\n"
        "replication_envelopes_served_total=7\n"
    )
    with _Server(503, None) as s:
        assert _main_with(s.port, logs, monkeypatch) == 0, "premise: the ladder alone passes"
        assert _main_with(s.port, logs, monkeypatch, "--require-authored") == atrc.AUTHORED_NONE
    assert "UNPROVEN" in capsys.readouterr().out
