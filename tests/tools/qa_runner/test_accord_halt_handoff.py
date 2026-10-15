"""CSD-129 handoff runner (CIRISServer#769), unit-tested against a fake harness, node and agent.

Nothing here touches :4243 or :8080: HTTP goes through an httpx MockTransport and
the harness is a thread writing the protocol files.
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

import httpx
import pytest

from tools.qa_runner.modules import accord_halt_handoff as h

ENV = {
    "CIRIS_TESTING_MODE": "true",
    "CIRIS_TEST_TRUST_ROOT": "root-b64",
    "CIRIS_TEST_GENESIS_BUNDLE": "/tmp/x/canonical_seed.json",
    "CIRIS_TEST_NO_CEREMONY": "true",
    "CIRIS_TEST_ANNOUNCE_SECS": "15",
    "CIRIS_TEST_BLESS_CANONICAL": "false",
    "CIRIS_TEST_CANONICAL_DIAL": "127.0.0.1:45555",
    "CIRIS_DEVICE_CLASS": "laptop",
    "CIRIS_TEST_HALT_FUSE_SECS": "20",
}
INVOCATION = "csd129-agent-halt-1"


def _handoff_dir(tmp_path: Path, env: Dict[str, str] = ENV) -> Path:
    d = tmp_path / "ciris-native-mesh-agent"
    d.mkdir()
    (d / h.HANDOFF_FILE).write_text(
        json.dumps({"env": env, "agent_url": "http://127.0.0.1:8080", "canonical": {"url": "x"}, "holders": [1]})
    )
    return d


def test_load_handoff_and_refuse_a_bad_env(tmp_path):
    handoff = h.load_handoff(_handoff_dir(tmp_path))
    assert handoff.env == ENV and handoff.canonical == {"url": "x"}
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / h.HANDOFF_FILE).write_text(json.dumps({"env": {"CIRIS_TEST_HALT_FUSE_SECS": 20}}))
    with pytest.raises(ValueError):
        h.load_handoff(bad)


def test_prepare_server_env_exports_verbatim_and_pins_every_data_path(tmp_path):
    home = tmp_path / "home"
    env = {"CIRIS_DATA_DIR": "/home/someone/ciris/data", "PATH": "/usr/bin"}  # as a host .env would leave it
    h.prepare_server_env(env, _handoff_dir(tmp_path), home)
    for key, value in ENV.items():
        assert env[key] == value
    assert env["CIRIS_HOME"] == str(home)
    assert env["CIRIS_DATA_DIR"] == str(home / "data")  # the host value does not win
    assert env["CIRIS_CONFIG_DIR"] == str(home / "config")
    assert env["CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"] == str(home / "tee")
    assert env["CIRIS_ACCORD_METRICS_TRACE_LEVEL"] == "detailed"
    assert all(str(home) in env[k] for k in h.PINNED_DATA_PATHS)


def test_a_handoff_cannot_move_the_data_paths(tmp_path):
    with pytest.raises(ValueError):
        h.prepare_server_env({}, _handoff_dir(tmp_path, {**ENV, "CIRIS_HOME": "/elsewhere"}), tmp_path / "home")


def test_test_anchor_detection(monkeypatch):
    import types

    monkeypatch.setitem(__import__("sys").modules, "ciris_server", types.SimpleNamespace())  # PyPI: no probe
    assert h.test_anchor_compiled() is False
    monkeypatch.setitem(
        __import__("sys").modules, "ciris_server", types.SimpleNamespace(test_anchor_compiled=lambda: False)
    )
    assert h.test_anchor_compiled() is False
    monkeypatch.setitem(
        __import__("sys").modules, "ciris_server", types.SimpleNamespace(test_anchor_compiled=lambda: True)
    )
    assert h.test_anchor_compiled() is True


def _write_batch(tee: Path, trace_id: str, execution_error: Any) -> None:
    tee.mkdir(parents=True, exist_ok=True)
    seq = len(list(tee.glob("lens-batch-*.json")))
    trace = {
        "trace_id": trace_id,
        "components": [
            {"event_type": "THOUGHT_START", "data": {}},
            {
                "event_type": "ACTION_RESULT",
                "data": {"execution_success": execution_error is None, "execution_error": execution_error},
            },
        ],
    }
    (tee / f"lens-batch-{seq:08d}.json").write_text(json.dumps({"events": [{"trace": trace}]}))


def test_find_refusal_trace(tmp_path):
    tee = tmp_path / "tee" / "accord_metrics_x"
    _write_batch(tee, "trace-ok", None)
    _write_batch(tee, "trace-other-halt", "accord_halt_in_effect:some-other-halt")
    assert h.find_refusal_trace(tmp_path / "tee", INVOCATION) is None
    _write_batch(tee, "trace-refused", f"accord_halt_in_effect:{INVOCATION}")
    assert h.find_refusal_trace(tmp_path / "tee", INVOCATION) == "trace-refused"


class FakeWorld:
    """The agent API, the agent's node, and the harness, wired together."""

    def __init__(self, handoff_dir: Path, tee: Path, refusal_seals: bool) -> None:
        self.dir = handoff_dir
        self.tee = tee
        self.refusal_seals = refusal_seals
        self.halted = False
        self.messages = 0
        self.interacts: List[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == h.NODE_HALT_STATUS_URL:
            return httpx.Response(200, json={"halted": self.halted, "lapsed": False})
        if url.endswith("/v1/system/runtime/delivery-receipt"):
            return httpx.Response(200, json={"data": {"agent_id_hash": "abcdef0123456789"}})
        if url.endswith("/v1/agent/message"):
            self.messages += 1
            if self.halted:
                return httpx.Response(423, json={"detail": {"error": "accord_halt_in_effect"}})
            return httpx.Response(200, json={"data": {"accepted": True}})
        if url.endswith("/v1/agent/interact"):
            self.interacts.append(1)
            assert self.halted, "the protocol's one interact must come after the halt"
            return httpx.Response(423, json={"detail": {"error": "accord_halt_in_effect", "reason": "ACCORD_HALT"}})
        return httpx.Response(404)

    def harness(self) -> None:
        ready = h.wait_for_file(self.dir / h.READY_FILE, 10.0, 0.05)
        assert ready and ready["agent_id_hash"] == "abcdef0123456789"
        time.sleep(0.3)
        self.halted = True  # one holder fired at the node; the in-flight act is refused and seals
        if self.refusal_seals:
            _write_batch(self.tee / "accord_metrics_x", "trace-refused", f"accord_halt_in_effect:{INVOCATION}")
        h.write_json_atomic(self.dir / h.FIRED_FILE, {"invocation_id": INVOCATION})
        acted = h.wait_for_file(self.dir / h.ACTED_FILE, 15.0, 0.05)
        assert acted is not None
        self.halted = False
        h.write_json_atomic(self.dir / h.DONE_FILE, {"verdict": "pass" if acted.get("trace_id") else "fail"})


async def _run(tmp_path: Path, refusal_seals: bool, stale_leftovers: bool = False):
    handoff_dir = _handoff_dir(tmp_path)
    if stale_leftovers:
        # What an earlier harness run leaves behind: it must not be read as this run's.
        import os

        old = time.time() - 3600
        for name, body in ((h.FIRED_FILE, {"invocation_id": "stale-halt"}), (h.DONE_FILE, {"verdict": "BROKEN"})):
            (handoff_dir / name).write_text(json.dumps(body))
            os.utime(handoff_dir / name, (old, old))
    tee = tmp_path / "home" / "tee"
    tee.mkdir(parents=True)
    world = FakeWorld(handoff_dir, tee, refusal_seals)
    harness = threading.Thread(target=world.harness, daemon=True)
    harness.start()
    run = h.HandoffRun("http://127.0.0.1:8080", "tok", handoff_dir, tee, Mock())
    run.KEEP_BUSY_EVERY_S = 0.1
    run.timeouts = {"fired": 10.0, "halted": 5.0, "trace": 2.0, "done": 10.0}
    async with httpx.AsyncClient(transport=httpx.MockTransport(world.handler)) as http:
        results = await run.run(http)
    harness.join(5)
    return results, world, json.loads((handoff_dir / h.ACTED_FILE).read_text())


@pytest.mark.asyncio
async def test_the_protocol_end_to_end(tmp_path):
    results, world, acted = await _run(tmp_path, refusal_seals=True)
    assert [r["status"] for r in results] == ["✅ PASS"] * len(results), results
    assert acted == {
        "status": 423,
        "trace_id": "trace-refused",
        "agent_id_hash": "abcdef0123456789",
        "outcome": h.REFUSED_IN_FLIGHT_ACT,
    }
    assert world.messages >= 1  # the agent was kept working until the halt
    assert len(world.interacts) == 1  # interact ONCE, after the halt


@pytest.mark.asyncio
async def test_a_previous_runs_leftovers_are_not_read_as_this_run(tmp_path, monkeypatch):
    results, world, acted = await _run(tmp_path, refusal_seals=True, stale_leftovers=True)
    assert [r["status"] for r in results] == ["✅ PASS"] * len(results), results
    assert acted["trace_id"] == "trace-refused"  # the fresh halt, not "stale-halt"


def test_a_stale_handoff_is_not_waited_out_as_fresh(tmp_path):
    import os

    d = _handoff_dir(tmp_path)
    old = time.time() - 3600
    os.utime(d / h.HANDOFF_FILE, (old, old))
    assert h.wait_for_file(d / h.HANDOFF_FILE, 0.5, 0.1, since=time.time()) is None
    assert h.wait_for_file(d / h.HANDOFF_FILE, 0.5, 0.1, since=old - 1) is not None


def test_a_handoff_written_before_launch_is_accepted(tmp_path, monkeypatch):
    """CSD-129 run 1: the harness wrote its handoff ~4 min before the runner started."""
    import os

    monkeypatch.delenv(h.HANDOFF_SINCE_ENV, raising=False)
    d = _handoff_dir(tmp_path)
    before_launch = time.time() - 240
    os.utime(d / h.HANDOFF_FILE, (before_launch, before_launch))
    floor = h.handoff_floor(d)
    assert floor is None  # a cleared work dir: nothing left behind
    assert h.wait_for_file(d / h.HANDOFF_FILE, 0.5, 0.1, since=floor) is not None


def test_a_handoff_older_than_a_finished_runs_report_is_refused(tmp_path, monkeypatch):
    import os

    monkeypatch.delenv(h.HANDOFF_SINCE_ENV, raising=False)
    d = _handoff_dir(tmp_path)
    old = time.time() - 3600
    os.utime(d / h.HANDOFF_FILE, (old, old))
    (d / h.REPORT_FILE).write_text("{}")
    (d / h.DONE_FILE).write_text("{}")
    os.utime(d / h.REPORT_FILE, (old + 60, old + 60))
    floor = h.handoff_floor(d)
    assert floor is not None and floor > old + 60
    assert h.wait_for_file(d / h.HANDOFF_FILE, 0.5, 0.1, since=floor) is None
    (d / h.HANDOFF_FILE).write_text((d / h.HANDOFF_FILE).read_text())  # the next run's handoff
    assert h.wait_for_file(d / h.HANDOFF_FILE, 0.5, 0.1, since=floor) is not None


def test_the_handoff_floor_env_overrides_the_leftover_scan(tmp_path, monkeypatch):
    d = _handoff_dir(tmp_path)
    monkeypatch.setenv(h.HANDOFF_SINCE_ENV, "1234.5")
    assert h.handoff_floor(d) == 1234.5


@pytest.mark.asyncio
async def test_no_in_flight_act_is_reported_not_invented(tmp_path):
    """If the halt lands between rounds there is no refusal trace; say so, report trace_id null."""
    results, _, acted = await _run(tmp_path, refusal_seals=False)
    failed = [r for r in results if r["status"] != "✅ PASS"]
    assert any(h.NO_IN_FLIGHT_ACT in (r["error"] or "") for r in failed)  # a non-pass, said so
    assert acted == {
        "status": 423,
        "trace_id": "",
        "agent_id_hash": "abcdef0123456789",
        "outcome": h.NO_IN_FLIGHT_ACT,
    }


@pytest.mark.asyncio
async def test_module_refuses_without_a_test_anchor_wheel(tmp_path, monkeypatch):
    from tools.qa_runner.modules import accord_halt_tests as qa

    monkeypatch.setenv(h.HANDOFF_DIR_ENV, str(_handoff_dir(tmp_path)))
    monkeypatch.setattr(h, "test_anchor_compiled", lambda *a: False)
    module = qa.AccordHaltTests(Mock(_transport=Mock(base_url="http://127.0.0.1:1", api_key="t")), Mock())
    results = await module.run()
    assert len(results) == 1 and results[0]["status"] == "❌ FAIL" and "test-anchor" in results[0]["error"]
    assert not (Path(tmp_path) / "ciris-native-mesh-agent" / h.READY_FILE).exists()


def _fake_harness_claim(d: Path, delay_s: float = 0.3) -> threading.Thread:
    """Claims the node the way the harness does: reads agent_up's node_home PIN, writes agent_claimed."""

    def claim() -> None:
        deadline = time.monotonic() + 5
        while not (d / h.UP_FILE).exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        node_home = Path(json.loads((d / h.UP_FILE).read_text())["node_home"])
        pin = (node_home / h.CLAIM_PIN_FILE).read_text().strip()
        time.sleep(delay_s)
        h.write_json_atomic(d / h.CLAIMED_FILE, {"owner_key_id": f"owner-for-{pin}", "token": "owner-bearer"})

    t = threading.Thread(target=claim, daemon=True)
    t.start()
    return t


def test_agent_up_names_the_home_holding_the_claim_pin(tmp_path):
    d = _handoff_dir(tmp_path)
    home = tmp_path / "node-home"
    home.mkdir()

    def mint_pin_late() -> None:
        time.sleep(0.4)  # compose reaches the claim phase after the brain is up
        (home / h.CLAIM_PIN_FILE).write_text("Q4YC-AZQA\n")

    threading.Thread(target=mint_pin_late, daemon=True).start()
    harness = _fake_harness_claim(d)
    claimed = h.claim_via_harness(d, home, pin_timeout_s=5, claim_timeout_s=5)
    harness.join(5)
    assert claimed == {"owner_key_id": "owner-for-Q4YC-AZQA", "token": "owner-bearer"}
    up = json.loads((d / h.UP_FILE).read_text())
    assert Path(up["node_home"]) == home and (Path(up["node_home"]) / h.CLAIM_PIN_FILE).is_file()


def test_no_pin_means_no_agent_up_and_no_claim(tmp_path):
    d = _handoff_dir(tmp_path)
    home = tmp_path / "node-home"
    home.mkdir()  # already ROOT-owned: the node minted no PIN
    assert h.claim_via_harness(d, home, pin_timeout_s=0.5, claim_timeout_s=0.5) is None
    assert not (d / h.UP_FILE).exists()


def test_a_previous_runs_agent_claimed_is_not_this_claim(tmp_path):
    import os

    d = _handoff_dir(tmp_path)
    home = tmp_path / "node-home"
    home.mkdir()
    (home / h.CLAIM_PIN_FILE).write_text("QCKE-AY69")
    h.write_json_atomic(d / h.CLAIMED_FILE, {"owner_key_id": "stale", "token": "old"})
    old = time.time() - 600
    os.utime(d / h.CLAIMED_FILE, (old, old))
    assert h.claim_via_harness(d, home, pin_timeout_s=1, claim_timeout_s=0.5) is None
