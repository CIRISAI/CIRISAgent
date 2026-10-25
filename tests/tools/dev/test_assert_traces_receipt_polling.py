"""The receipt is POLLED across the canonical's replication round, and a failed
READ is never a verdict.

Diagnosed from the canonical's own store (2026-10-25): delivery latency is
9-32 s, set by a ~30 s replication round. Run 40091023664 read `held: false`
twice, ten seconds apart, and its third read hit a LOCAL :8080 login timeout;
the gate then fell back to the log ladder and reported "the node exposes no
receipt (CIRISServer#518) ... regression". The retry passed.

Driven against a scripted loopback server, like test_assert_traces_receipt.py:
each read pops the next scripted answer, so "false, false, login timeout, true"
is exactly the incident's sequence.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("atrc_poll", ROOT / "tools/dev/assert_traces_reached_canonical.py")
assert _spec and _spec.loader
atrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atrc)

#: A receipt read: "held" / "not_held" / "unknown", or a local failure:
#: "login_timeout" (login hangs past the gate's timeout), "http_500", "absent" (503).
Step = str

_RAW_AUTHORED_2 = json.dumps({"agents": [{"agent_id_hash": "9fba1f67d6585450", "authored": 2}]})


class _Scripted:
    """Each GET of the receipt (and its login) consumes one step; the last step repeats."""

    def __init__(self, steps: List[Step], hang_secs: float = 1.5):
        self.steps = list(steps)
        self.reads: List[Step] = []
        self.current: Step = self.steps[0]
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, obj) -> None:
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):  # login: decides this read's step
                outer.current = outer.steps.pop(0) if len(outer.steps) > 1 else outer.steps[0]
                outer.reads.append(outer.current)
                if outer.current == "login_timeout":
                    time.sleep(hang_secs)
                    return
                self._send(200, {"access_token": "t0ken"})

            def do_GET(self):
                step = outer.current
                if step == "http_500":
                    self._send(500, {"detail": "boom"})
                    return
                if step == "absent":
                    self._send(503, {"detail": "no accessor"})
                    return
                verdict = {"held": True, "not_held": False, "unknown": None}[step]
                self._send(
                    200,
                    {
                        "data": {
                            "held_by_every_answering_canonical": verdict,
                            "raw_json": _RAW_AUTHORED_2,
                            "canonicals": [
                                {"key_id": "ciris-canonical-1-d7bdeu223k", "holds_newest": verdict, "shipped_any": True}
                            ],
                        }
                    },
                )

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    """The ladder's evidence on the incident's wheel: rooted, and the counter ABSENT —
    which is exactly what turns a fallback into exit 3 / "#518"."""
    d = tmp_path / "logs"
    d.mkdir()
    (d / "agent.log").write_text(
        "[DELIVERY-PROBE] canonical ciris-canonical-1-d7bdeu223k ROOTED after ~8s\n"
        "[TRACE-SHIP] replication_envelopes_served_total ABSENT from delivery_status (top-level keys: [])\n"
    )
    return d


def _gate(port: int, logs: Path, monkeypatch, wait: float, poll: float = 0.2, timeout: float = 0.5) -> int:
    monkeypatch.setattr(
        "sys.argv",
        [
            "x",
            str(logs),
            "--require",
            "replication",
            "--wait-secs",
            str(wait),
            "--poll-secs",
            str(poll),
            "--receipt-timeout",
            str(timeout),
            "--receipt-url",
            f"http://127.0.0.1:{port}",
            "--receipt-username",
            "qaadmin",
            "--receipt-password",
            "pw",
            "--require-authored",
        ],
    )
    return atrc.main()


#: The incident: false, false, a local login timeout, then the canonical holds it.
INCIDENT = ["not_held", "not_held", "login_timeout", "held"]


def test_the_incident_sequence_passes_once_delivery_lands(logs, monkeypatch, capsys):
    with _Scripted(INCIDENT) as s:
        rc = _gate(s.port, logs, monkeypatch, wait=8)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert s.reads[:4] == INCIDENT
    assert "CIRISServer#518" not in out and "NOT COVERED" not in out
    assert "could not read the receipt" in out and "will retry" in out


def test_negative_the_old_two_read_window_fails_slow_delivery(logs, monkeypatch, capsys):
    """THE NEGATIVE. Delivery lands on the 4th read (one replication round later);
    a window that only fits two reads fails a run that delivers fine. This is the
    shape the gate had, and why the workflow now waits ~90 s (three rounds)."""
    slow = ["not_held", "not_held", "not_held", "held"]
    with _Scripted(slow) as s:
        rc_two_reads = _gate(s.port, logs, monkeypatch, wait=0.2, poll=0.2)
    assert rc_two_reads == 1, "two reads must not be enough to see a delivery that lands later"
    assert len(s.reads) == 2
    capsys.readouterr()
    with _Scripted(slow) as s:
        rc_full = _gate(s.port, logs, monkeypatch, wait=8, poll=0.2)
    assert rc_full == 0
    assert len(s.reads) == 4


def test_a_local_timeout_is_never_reported_as_no_receipt(logs, monkeypatch, capsys):
    """A login that times out on EVERY read is a local failure: exit 4 (not
    established), worded as such — never exit 3, never '#518'."""
    with _Scripted(["login_timeout"]) as s:
        rc = _gate(s.port, logs, monkeypatch, wait=1.0, poll=0.2, timeout=0.3)
    out = capsys.readouterr().out
    assert rc == atrc.RECEIPT_UNKNOWN == 4, out
    assert rc != 3
    assert "CIRISServer#518" not in out and "NOT COVERED" not in out
    assert "LOCAL read failure" in out


def test_a_failed_final_read_keeps_the_last_real_verdict(logs, monkeypatch, capsys):
    """false, then only local failures to the deadline: the answer is the canonical's
    last word (1), with the ladder as diagnosis — not the ladder's #518."""
    with _Scripted(["not_held", "http_500"]) as s:
        rc = _gate(s.port, logs, monkeypatch, wait=1.0, poll=0.2)
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "the final read failed" in out
    assert "DIAGNOSIS" in out


def test_an_absent_route_after_a_real_answer_is_a_failed_read(logs, monkeypatch, capsys):
    """Once the receipt has answered, a later 503 cannot mean 'older wheel'."""
    with _Scripted(["not_held", "absent", "held"]) as s:
        rc = _gate(s.port, logs, monkeypatch, wait=5, poll=0.2)
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "NOT COVERED" not in out


def test_an_absent_route_from_the_start_still_falls_back_to_the_ladder(logs, monkeypatch, capsys):
    """An older wheel (503 on every read) still gets the ladder's answer; with
    --require-authored that fails closed (5), exactly as before."""
    with _Scripted(["absent"]) as s:
        rc = _gate(s.port, logs, monkeypatch, wait=0.5, poll=0.2)
    out = capsys.readouterr().out
    assert "falling back to the ladder" in out
    assert rc == atrc.AUTHORED_NONE


def test_not_established_is_polled_not_terminal(logs, monkeypatch):
    """None (a canonical unreachable this round) can change next round: poll it."""
    with _Scripted(["unknown", "unknown", "held"]) as s:
        assert _gate(s.port, logs, monkeypatch, wait=5, poll=0.2) == 0
    assert len(s.reads) == 3


def test_held_never_seen_by_the_deadline_still_fails(logs, monkeypatch):
    """The wait is bounded, and a canonical that never holds it is still red."""
    with _Scripted(["not_held"]) as s:
        started = time.monotonic()
        rc = _gate(s.port, logs, monkeypatch, wait=1.0, poll=0.2)
        elapsed = time.monotonic() - started
    assert rc == 1
    assert elapsed < 5
