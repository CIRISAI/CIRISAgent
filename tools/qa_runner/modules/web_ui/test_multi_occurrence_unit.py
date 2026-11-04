"""The parts of multi_occurrence_self that run without a device."""

import asyncio
import json

import pytest

from tools.qa_runner.modules.web_ui.multi_occurrence_self import (
    Device,
    ORDER,
    SignalFailed,
    Signals,
    chunks,
    needed_assents,
    play,
)


class FakeGitHub:
    """Commit statuses: newest first, as the API returns them."""

    def __init__(self):
        self.rows = []

    def __call__(self, args):
        if "statuses" in args[1] and "-f" in args:
            fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("repos"))
            self.rows.insert(0, {"context": fields["context"], "description": fields["description"]})
            return ""
        return json.dumps(self.rows)


async def no_sleep(_):
    await asyncio.sleep(0)


def signals(gh, clock=None):
    return Signals("o/r", "sha", "1-1", gh=gh, sleep=no_sleep, clock=clock or (lambda: 0.0))


def test_the_quorum_table():
    # Extra signatures beyond the proposer's, from a roster of N keys.
    assert [needed_assents(n) for n in (1, 2, 3, 4)] == [0, 1, 1, 2]


def test_a_long_code_round_trips_through_statuses():
    gh = FakeGitHub()
    s = signals(gh)
    code = "x" * 700
    s.put_text("code", code)
    assert len(chunks(code)) > 5
    assert asyncio.run(s.wait_text("code", 5)) == code


def test_the_newest_value_of_a_context_wins():
    gh = FakeGitHub()
    s = signals(gh)
    s.put("a", "old")
    s.put("a", "new")
    assert s.all()["a"] == "new"


def test_another_runs_signals_are_ignored():
    gh = FakeGitHub()
    Signals("o/r", "sha", "2-1", gh=gh).put("ready/linux")
    assert signals(gh).all() == {}


def test_a_failed_device_stops_the_others_at_once():
    gh = FakeGitHub()
    s = signals(gh)
    s.put("failed/windows", "no match code")
    with pytest.raises(SignalFailed, match="windows"):
        asyncio.run(s.wait("joined/windows", 1000))


def test_a_silent_peer_times_out_and_says_what_it_waited_for():
    t = iter(range(0, 100000, 100))
    s = signals(FakeGitHub(), clock=lambda: float(next(t)))
    with pytest.raises(TimeoutError, match="ready/ios"):
        asyncio.run(s.wait("ready/ios", 500))


class FakeDevice:
    """Records the order of a device's acts; other devices are played in the store."""

    def __init__(self, name, s):
        self.name, self.signals, self.acts = name, s, []

    def log(self, _):
        pass

    async def create_identity(self, _):
        self.acts.append("create")

    async def publish_contact_code(self):
        self.signals.put_text("code", "c")

    async def approve(self, joiner, keys_before):
        self.acts.append(f"approve {joiner} {keys_before}")

    async def join(self):
        self.acts.append("join")

    async def assent_to(self, joiner):
        self.acts.append(f"assent {joiner}")

    async def prove_five(self):
        self.signals.put(f"sees-five/{self.name}")


def everyone_else(s, me):
    for d in ORDER:
        if d != me:
            s.put(f"joined/{d}")
            s.put(f"sees-five/{d}")
    s.put("code/count", "1")


def test_the_creator_approves_all_four_in_order_with_the_right_roster_size():
    s = signals(FakeGitHub())
    everyone_else(s, "linux")
    d = FakeDevice("linux", s)
    asyncio.run(play(d, "1"))
    assert d.acts == ["create", "approve android 1", "approve windows 2", "approve macos 3", "approve ios 4"]


def test_a_joiner_helps_every_later_addition_and_the_last_helps_none():
    s = signals(FakeGitHub())
    everyone_else(s, "android")
    d = FakeDevice("android", s)
    asyncio.run(play(d, "1"))
    assert d.acts == ["join", "assent windows", "assent macos", "assent ios"]
    s2 = signals(FakeGitHub())
    everyone_else(s2, "ios")
    last = FakeDevice("ios", s2)
    asyncio.run(play(last, "1"))
    assert last.acts == ["join"]


class SurfaceHelper:
    def __init__(self, answer):
        self.answer = answer

    async def reach_surface(self, surface):
        return self.answer


class SurfaceRunner:
    def __init__(self, answer):
        self.helper = SurfaceHelper(answer)

    async def _dump_tree(self, why):
        pass


def test_reach_surface_answers_none_on_success_and_why_on_failure():
    good = Device(SurfaceRunner(None), "linux", None, "pw")
    asyncio.run(good.identity())
    bad = Device(SurfaceRunner("no route"), "linux", None, "pw")
    with pytest.raises(RuntimeError, match="no route"):
        asyncio.run(bad.identity())
