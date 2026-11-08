"""The timed round trip over a punched link."""

import base64
from typing import List, Optional, Tuple

import pytest

from tools.qa_runner.cross_platform_chat import StepFailed
from tools.qa_runner.nat_peer import FILE_SIZES, ROLE_REQUESTER, ROLE_RESPONDER, PeerContact, PeerHalf
from tools.qa_runner.cross_platform_chat import Deadlines, Node


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _half(role: str, clock: _Clock) -> PeerHalf:
    me = Node("a", None, "u", "p", token="t", fed_id="a")  # type: ignore[arg-type]
    return PeerHalf(me, PeerContact("b", "b"), role, "n1", clock=clock, deadlines=Deadlines(), log=lambda _l: None)


def test_a_round_trip_inside_the_ceiling_passes() -> None:
    clock = _Clock()
    half = _half(ROLE_REQUESTER, clock)
    half.send = lambda cid, text, step: None  # type: ignore[method-assign]

    def read(cid: str, text: str, step: str) -> float:
        clock.t += 1.5
        return 1.5

    half.read = read  # type: ignore[method-assign]
    detail = half.direct_round_trip("c", 2.0)
    assert "round trip 1.50s" in detail
    assert "send call 0.00s, then 1.50s until the reply opened" in detail


def test_a_slow_round_trip_fails() -> None:
    clock = _Clock()
    half = _half(ROLE_REQUESTER, clock)
    half.send = lambda cid, text, step: None  # type: ignore[method-assign]

    def read(cid: str, text: str, step: str) -> float:
        clock.t += 5.0
        return 5.0

    half.read = read  # type: ignore[method-assign]
    with pytest.raises(StepFailed):
        half.direct_round_trip("c", 2.0)


def test_the_responder_answers_what_it_read() -> None:
    clock = _Clock()
    half = _half(ROLE_RESPONDER, clock)
    sent: List[str] = []
    half.send = lambda cid, text, step: sent.append(text)  # type: ignore[method-assign]
    half.read = lambda cid, text, step: 0.1  # type: ignore[method-assign]
    half.direct_round_trip("c", 2.0)
    assert sent == ["nat-peer direct pong n1"]


def test_repeated_pairs_keep_every_run_and_fail_if_any_failed(monkeypatch, tmp_path) -> None:
    from tools.qa_runner import nat_peer

    results = iter([0, 1, 0])
    outs = []

    def fake_pair(tag, ref, out):
        outs.append(out.name)
        return next(results)

    monkeypatch.setattr(nat_peer, "pair", fake_pair)
    assert nat_peer.pair_repeated("t", "r", tmp_path, 3) == 1
    assert outs == ["run-1", "run-2", "run-3"]


def test_time_to_contact_reports_each_step_and_a_failure() -> None:
    from tools.qa_runner.nat_peer import contact_times

    halves = [
        {
            "steps": [
                {"step": "code:node-a", "ok": True, "elapsed_s": 1.0},
                {"step": "add:node-a->node-b", "ok": True, "elapsed_s": 21.0},
                {"step": "mutual:node-a", "ok": False, "elapsed_s": 180.0},
            ]
        }
    ]
    assert contact_times(halves) == "add:node-a->node-b 21s, mutual:node-a 180s FAILED"
    assert contact_times([]) == "no contact steps recorded"


def test_parallel_pairs_really_overlap_and_keep_their_order(monkeypatch, tmp_path) -> None:
    import threading

    from tools.qa_runner import nat_peer

    together = threading.Barrier(3, timeout=5)

    def fake_pair(tag, ref, out):
        together.wait()  # only passes if three pairs are running at once
        return 1 if out.name == "run-2" else 0

    monkeypatch.setattr(nat_peer, "pair", fake_pair)
    assert nat_peer.pair_repeated("t", "r", tmp_path, 3, parallel=3) == 1


class _Answer:
    def __init__(self, body: object, ok: bool = True) -> None:
        self.body, self.ok = body, ok

    def brief(self) -> str:
        return f"ok={self.ok}"


def _file_half(peer_bytes: Optional[bytes]) -> Tuple[PeerHalf, List[Tuple[str, str]]]:
    """A half whose node holds the peer's file with `peer_bytes`, or doesn't hold it yet."""
    half = _half(ROLE_REQUESTER, _Clock())
    half.d = Deadlines(poll_s=1.0, receive_s=3.0)
    calls: List[Tuple[str, str]] = []

    def call(node: Node, method: str, path: str, body: Optional[object] = None) -> _Answer:
        calls.append((method, path))
        if method == "POST":
            return _Answer({})
        if path.startswith("/v1/drive"):
            entries = [{"filename": "nat-peer-b-small-n1.bin", "attestation_id": "x", "bytes": "here"}]
            return _Answer({"entries": entries if peer_bytes is not None else []})
        return _Answer({"bytes_base64": base64.b64encode(peer_bytes or b"").decode()})

    half._call = call  # type: ignore[method-assign,assignment]
    return half, calls


def test_a_peers_file_opens_with_exactly_its_bytes() -> None:
    half, calls = _file_half(_half(ROLE_REQUESTER, _Clock()).file_body("b", FILE_SIZES["small"]))
    assert "bytes each way" in half.files_one_side("room/1", "small")
    assert calls[0] == ("POST", "/v1/files")
    assert "room_id=room%2F1" in calls[1][1]


def test_different_bytes_fail_rather_than_pass_on_a_listing() -> None:
    half, _ = _file_half(b"not the file")
    with pytest.raises(StepFailed):
        half.files_one_side("c", "small")


def test_a_file_that_never_arrives_fails() -> None:
    half, _ = _file_half(None)
    with pytest.raises(StepFailed):
        half.files_one_side("c", "small")


def test_the_large_file_goes_over_the_inline_cap_and_uses_its_own_name() -> None:
    assert FILE_SIZES["large"] > 1024 * 1024
    half, _ = _file_half(_half(ROLE_REQUESTER, _Clock()).file_body("b", FILE_SIZES["small"]))
    assert len(half.file_body("a", FILE_SIZES["large"])) == FILE_SIZES["large"]


def test_waiting_for_a_run_survives_a_github_error(monkeypatch) -> None:
    import subprocess

    from tools.qa_runner import nat_peer

    answers = iter([subprocess.CalledProcessError(1, "gh"), '{"status": "in_progress"}', '{"status": "completed"}'])

    def gh(*args: str) -> str:
        got = next(answers)
        if isinstance(got, Exception):
            raise got
        return got

    monkeypatch.setattr(nat_peer, "_gh", gh)
    nat_peer._wait_for_run("1", poll_s=0)
    assert next(answers, None) is None


def test_a_sealed_row_is_reported_as_sealed_not_as_never_listed() -> None:
    half, _ = _file_half(None)
    inner = half._call

    def call(node: Node, method: str, path: str, body: Optional[object] = None) -> _Answer:
        if path.startswith("/v1/drive"):
            sealed = {"filename": None, "description": "sealed", "bytes": "not_fetched", "author_key_id": "b"}
            return _Answer({"entries": [sealed]})
        return inner(node, method, path, body)  # type: ignore[arg-type,return-value]

    half._call = call  # type: ignore[method-assign,assignment]
    with pytest.raises(StepFailed) as failed:
        half.files_one_side("c", "small")
    assert "listed sealed, sealed, bytes=not_fetched" in str(failed.value.result.detail)



def _av_half(join_ok: bool = True, heard: int = 1700) -> Tuple[PeerHalf, List[Tuple[str, str, Optional[object]]]]:
    """A half whose node answers the 0.5.245 QA call routes."""
    half = _half(ROLE_REQUESTER, _Clock())
    half.d = Deadlines(poll_s=2.0)
    calls: List[Tuple[str, str, Optional[object]]] = []
    stats = {
        "sent": {"frames": 1800, "publish_refused": 0, "legs": {"delivered": 1800}},
        "received": {"frames": heard, "delay_ms_p50": 40, "delay_ms_p95": 120, "delay_ms_max": 300},
        "call": {"legs": [{"peer": "b"}], "service_tier": "full", "reorder": {"expired_late": 3},
                 "alm": {"stale_dropped": 1}, "streams": [{"leg": "direct", "parent_changes": 0}]},
    }

    def call(node: Node, method: str, path: str, body: Optional[object] = None) -> _Answer:
        calls.append((method, path, body))
        if path == "/v1/qa/call/start":
            return _Answer({"legs": 1} if join_ok else {"detail": "NotARoomMember"}, ok=join_ok)
        if path == "/v1/qa/call/stop":
            return _Answer({"stats": stats, "summary": {}})
        return _Answer(stats)

    half._call = call  # type: ignore[method-assign,assignment]
    return half, calls


def test_an_av_call_reports_frames_delay_and_the_leg() -> None:
    half, calls = _av_half()
    detail = half.av_call("room/1")
    assert [c[1].split("?")[0] for c in calls][:3] == ["/v1/qa/call/start", "/v1/qa/call/stats", "/v1/qa/call/stream"]
    assert calls[-1][1] == "/v1/qa/call/stop"
    assert "room=room%2F1" in calls[1][1]
    assert calls[2][2] == {"room": "room/1", "rate_hz": 30, "frame_bytes": 1024, "seconds": 60}
    assert "received 1700/1800" in detail and "expired_late 3" in detail and "direct(parent_changes=0)" in detail
    assert half.av_record["stop"]


def test_an_av_call_that_hears_nothing_fails_and_keeps_the_record() -> None:
    half, calls = _av_half(heard=0)
    with pytest.raises(StepFailed):
        half.av_call("c")
    assert calls[-1][1] == "/v1/qa/call/stop" and half.av_record["last_stats"]


def test_a_refused_join_fails_with_the_reason() -> None:
    half, calls = _av_half(join_ok=False)
    with pytest.raises(StepFailed) as failed:
        half.av_call("c")
    assert "could not join the call" in failed.value.result.detail
    assert len(calls) == 1 and half.av_record == {"joined": "ok=False"}
