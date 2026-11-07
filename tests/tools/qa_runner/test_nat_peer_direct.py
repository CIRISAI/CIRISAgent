"""The timed round trip over a punched link."""

import base64
from typing import List, Optional, Tuple

import pytest

from tools.qa_runner.cross_platform_chat import StepFailed
from tools.qa_runner.nat_peer import ROLE_REQUESTER, ROLE_RESPONDER, PeerContact, PeerHalf
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
            entries = [{"filename": "nat-peer-b-n1.bin", "attestation_id": "x", "bytes": "here"}]
            return _Answer({"entries": entries if peer_bytes is not None else []})
        return _Answer({"bytes_base64": base64.b64encode(peer_bytes or b"").decode()})

    half._call = call  # type: ignore[method-assign,assignment]
    return half, calls


def test_a_peers_file_opens_with_exactly_its_bytes() -> None:
    half, calls = _file_half(_half(ROLE_REQUESTER, _Clock()).file_body("b"))
    assert "bytes each way" in half.files_one_side("room/1")
    assert calls[0] == ("POST", "/v1/files")
    assert "room_id=room%2F1" in calls[1][1]


def test_different_bytes_fail_rather_than_pass_on_a_listing() -> None:
    half, _ = _file_half(b"not the file")
    with pytest.raises(StepFailed):
        half.files_one_side("c")


def test_a_file_that_never_arrives_fails() -> None:
    half, _ = _file_half(None)
    with pytest.raises(StepFailed):
        half.files_one_side("c")
