"""The timed round trip over a punched link."""

from typing import List

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

