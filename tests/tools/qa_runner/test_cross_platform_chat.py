"""The cross-platform chat stage, against a fake two-node network on a fake clock.

The fake models only what the stage depends on, in the server's own shapes
(CIRISServer src/contacts_chat.rs, membership_invites.rs, self_devices.rs):
a code add that answers 202 contacts.awaiting_key_body until the key body
"arrives", a pair room only the Creator may found, an invite that reaches the
Joiner's /v1/self/invites after a delay, seating after the accept, and messages
that reach the other side after a delay. Each knob that breaks one of those is
a negative test: the stage must fail at that step, and name that layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from tools.qa_runner import cross_platform_chat as xc


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(0.0, seconds)


@dataclass
class Msg:
    att: str
    author: str
    body: str
    delivered_at: float


@dataclass
class FakeNet:
    clock: FakeClock
    fed: Dict[str, str]  # node name -> fedID
    key_body_delay_s: float = 25.0
    key_body_arrives: bool = True
    invite_delay_s: float = 20.0
    invite_delivered: bool = True
    seat_delay_s: float = 15.0
    message_delay_s: float = 12.0
    message_delivered: bool = True
    #: The FIXED server: B can see A's incoming request before adding back.
    incoming_requests_visible: bool = False
    #: A broken server that echoes the receiver's copy as its own (mine=True).
    receiver_sees_mine: bool = False
    # state
    contacts: Dict[str, set] = field(default_factory=dict)
    pending: Dict[Tuple[str, str], float] = field(default_factory=dict)
    room: Optional[str] = None
    invite_at: Optional[float] = None
    accepted_at: Optional[float] = None
    messages: List[Msg] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)

    def node_of_fed(self, fed: str) -> str:
        return next(n for n, f in self.fed.items() if f == fed)

    def creator(self) -> str:
        return min(self.fed, key=lambda n: self.fed[n])

    def seated(self) -> bool:
        return self.accepted_at is not None and self.clock.now() >= self.accepted_at + self.seat_delay_s


class FakeTransport:
    def __init__(self, net: FakeNet, name: str) -> None:
        self.net, self.name = net, name

    def request(self, method: str, path: str, body: Optional[dict] = None, token: Optional[str] = None) -> xc.HttpResult:
        n, me, now = self.net, self.name, self.net.clock.now()
        n.calls.append(f"{me} {method} {path}")
        other = next(x for x in n.fed if x != me)
        if path == "/v1/system/health":
            return xc.HttpResult(200, {"status": "healthy"})
        if path == "/v1/auth/login":
            return xc.HttpResult(200, {"access_token": f"tok-{me}"})
        if token != f"tok-{me}":
            return xc.HttpResult(401, {"detail": "no session"})
        if path == "/v1/self/contact-code":
            return xc.HttpResult(200, {"key_id": n.fed[me], "code": f"CODE-{n.fed[me]}", "included_nodes": [{}]})
        if path == "/v1/contacts" and method == "POST":
            target = n.node_of_fed(str(body["key_id"]).removeprefix("CODE-"))
            mine = n.contacts.setdefault(me, set())
            if n.fed[target] in mine:
                return xc.HttpResult(200, {"key_id": n.fed[target]})
            started = n.pending.setdefault((me, target), now)
            if n.key_body_arrives and now >= started + n.key_body_delay_s:
                mine.add(n.fed[target])
                return xc.HttpResult(200, {"key_id": n.fed[target]})
            return xc.HttpResult(202, {"reason_id": "contacts.awaiting_key_body", "converges_on_its_own": True})
        if path == "/v1/contacts":
            listed = set(n.contacts.get(me, set()))
            if n.incoming_requests_visible and n.fed[me] in n.contacts.get(other, set()):
                listed.add(n.fed[other])
            return xc.HttpResult(200, {"contacts": [{"key_id": k} for k in sorted(listed)], "total": len(listed)})
        if path == "/v1/chat" and method == "POST":
            peer = str(body["key_id"])
            if peer not in n.contacts.get(me, set()):
                return xc.HttpResult(403, {"reason_id": "chat.not_a_contact"})
            cid = "pair-" + "-".join(sorted(n.fed.values()))
            if me != n.creator():
                return xc.HttpResult(200, {"community_id": cid, "state": "awaiting_invitation"})
            if n.room is None:
                n.room, n.invite_at = cid, now + n.invite_delay_s
            state = "open" if n.seated() else "accepted" if n.accepted_at is not None else "invited"
            return xc.HttpResult(200, {"community_id": cid, "state": state})
        if path == "/v1/self/invites":
            invites = []
            if me != n.creator() and n.room and n.invite_delivered and n.invite_at is not None and now >= n.invite_at:
                if n.accepted_at is None:
                    invites.append({"proposal_id": "prop-1", "group_id": n.room, "is_pair_room": True,
                                    "proposer_key_id": n.fed[other]})
            return xc.HttpResult(200, {"invitee_key_id": n.fed[me], "invites": invites})
        if path == "/v1/self/invites/prop-1/accept":
            n.accepted_at = now
            return xc.HttpResult(200, {"state": "accepted", "proposal_id": "prop-1"})
        if n.room and path == f"/v1/chat/{n.room}/messages":
            if not n.seated():
                return xc.HttpResult(200, {"messages": [{"kind": "system", "body": "Waiting"}], "ready": False})
            if method == "POST":
                att = f"att-{len(n.messages)}"
                n.messages.append(Msg(att, me, str(body["body"]), now + n.message_delay_s))
                return xc.HttpResult(200, {"attestation_id": att, "message": {"body": body["body"]}})
            rows = []
            for m in n.messages:
                if m.author == me:
                    rows.append({"attestation_id": m.att, "kind": "message", "body": m.body, "mine": True})
                elif n.message_delivered and now >= m.delivered_at:
                    rows.append({"attestation_id": m.att, "kind": "message", "body": m.body,
                                 "mine": n.receiver_sees_mine})
            return xc.HttpResult(200, {"messages": rows, "ready": True, "total": len(rows)})
        return xc.HttpResult(404, {"detail": f"fake has no {method} {path}"})


def _stage(**knobs) -> Tuple[xc.CrossChatStage, FakeNet, List[str]]:
    clock = FakeClock()
    fed = knobs.pop("fed", {"linux": "alice-aaaa", "android": "bob-bbbb"})
    net = FakeNet(clock=clock, fed=fed, **knobs)
    out: List[str] = []
    a = xc.Node("linux", FakeTransport(net, "linux"), "qaadmin", "pw")
    b = xc.Node("android", FakeTransport(net, "android"), "qaadmin", "pw")
    return xc.CrossChatStage(a, b, clock=clock, log=out.append, nonce="n0nce"), net, out


def _step(rep: xc.StageReport, name: str) -> xc.StepResult:
    return next(s for s in rep.steps if s.step == name)


def test_mutual_add_room_and_messages_pass():
    stage, net, _ = _stage()
    rep = stage.run()
    assert rep.ok, rep.to_json()
    assert rep.failed_step is None
    assert [s.step for s in rep.steps] == [
        "ready:linux", "ready:android", "code:linux", "code:android",
        "add:linux->android", "add:android->linux", "room", "messages",
    ]
    assert all(s.ok for s in rep.steps)
    # The 202 ladder was walked, not skipped.
    assert "after awaiting the key body" in _step(rep, "add:linux->android").detail
    assert rep.creator == "linux" and rep.joiner == "android"
    assert rep.community_id == "pair-alice-aaaa-bob-bbbb"
    assert "/v1/self/invites/prop-1/accept" in " ".join(net.calls)


def test_the_creator_is_the_smaller_fed_id_not_node_a():
    stage, _, _ = _stage(fed={"linux": "zed-9999", "android": "amy-1111"})
    rep = stage.run()
    assert rep.ok, rep.to_json()
    assert rep.creator == "android" and rep.joiner == "linux"


def test_negative_a_missing_invite_fails_at_the_room_step_naming_the_layer():
    stage, _, _ = _stage(invite_delivered=False)
    rep = stage.run()
    assert not rep.ok
    assert rep.failed_step == "room" and rep.failed_layer == xc.LAYER_ROOM == "room"
    assert "invite" in _step(rep, "room").detail and "/v1/self/invites" in _step(rep, "room").detail
    assert "messages" not in [s.step for s in rep.steps], "a failed room must stop the stage"


def test_negative_a_message_that_never_arrives_fails_at_the_message_step():
    stage, _, _ = _stage(message_delivered=False)
    rep = stage.run()
    assert not rep.ok
    assert rep.failed_step == "messages" and rep.failed_layer == xc.LAYER_MESSAGE == "message"
    assert "never read" in _step(rep, "messages").detail
    assert _step(rep, "room").ok


def test_negative_an_echo_of_your_own_copy_is_not_a_received_message():
    """A server that shows the receiver its copy as mine=True has not delivered anything readable."""
    stage, _, _ = _stage(receiver_sees_mine=True)
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "messages"


def test_negative_an_add_whose_key_body_never_arrives_fails_at_contacts():
    stage, _, _ = _stage(key_body_arrives=False)
    rep = stage.run()
    assert not rep.ok
    assert rep.failed_step == "add:linux->android" and rep.failed_layer == "contacts"
    assert "awaiting_key_body" in _step(rep, "add:linux->android").detail


def test_one_sided_request_is_reported_as_the_known_gap_and_not_enforced():
    stage, _, out = _stage()
    rep = stage.run()
    assert rep.ok
    o = rep.one_sided
    assert o is not None and o.checked
    assert o.observer == "android" and o.requester == "linux"
    assert o.visible is False, "today's server: an incoming request has no reader"
    assert "KNOWN GAP" in o.note
    assert any("REPORTED, NOT ENFORCED" in line and "could NOT see" in line for line in out)


def test_one_sided_request_visible_once_the_gap_is_fixed_and_still_passes():
    stage, _, out = _stage(incoming_requests_visible=True)
    rep = stage.run()
    assert rep.ok
    assert rep.one_sided is not None and rep.one_sided.visible is True
    assert rep.one_sided.where and "GET /v1/contacts" in rep.one_sided.where[0]
    assert any("COULD see" in line for line in out)


def test_one_sided_is_checked_before_b_adds_back():
    stage, net, _ = _stage()
    stage.run()
    first_b_add = net.calls.index("android POST /v1/contacts")
    assert "android GET /v1/self/invites" in net.calls[:first_b_add]


def test_every_step_is_bounded():
    """No step may outlive its deadline by more than one poll, even when nothing converges."""
    stage, _, _ = _stage(invite_delivered=False)
    rep = stage.run()
    d = xc.Deadlines()
    room = _step(rep, "room")
    assert room.elapsed_s <= 2 * d.room_open_s + d.invite_s + 3 * d.poll_s
    for s in rep.steps:
        assert s.elapsed_s <= 600, f"{s.step} ran {s.elapsed_s}s"


def test_annotations_name_the_step_layer_and_the_gap(capsys):
    stage, _, _ = _stage(invite_delivered=False)
    xc._annotate(stage.run())
    out = capsys.readouterr().out
    assert "::error::cross-platform chat FAILED at step 'room' [layer: room]" in out
    assert "REPORTED, NOT ENFORCED" in out and "KNOWN GAP" in out


def test_report_json_round_trips():
    stage, _, _ = _stage()
    data = json.loads(stage.run().to_json())
    assert data["ok"] is True and data["one_sided"]["visible"] is False
    assert data["fed_ids"] == {"linux": "alice-aaaa", "android": "bob-bbbb"}


def test_a_refused_add_fails_fast_with_its_reason():
    class Refusing(FakeTransport):
        def request(self, method, path, body=None, token=None):
            if path == "/v1/contacts" and method == "POST":
                return xc.HttpResult(409, {"reason_id": "contacts.code_commitment_mismatch", "error": "x"})
            return super().request(method, path, body, token)

    clock = FakeClock()
    net = FakeNet(clock=clock, fed={"linux": "alice-aaaa", "android": "bob-bbbb"})
    a = xc.Node("linux", Refusing(net, "linux"), "u", "p")
    b = xc.Node("android", FakeTransport(net, "android"), "u", "p")
    rep = xc.CrossChatStage(a, b, clock=clock, log=lambda _: None).run()
    assert rep.failed_step == "add:linux->android"
    assert "code_commitment_mismatch" in _step(rep, "add:linux->android").detail
    assert _step(rep, "add:linux->android").elapsed_s < xc.Deadlines().poll_s


def test_an_unreachable_node_fails_at_ready_as_local_api():
    class Dead:
        def request(self, method, path, body=None, token=None):
            return xc.HttpResult(0, None, "ConnectError: refused")

    clock = FakeClock()
    net = FakeNet(clock=clock, fed={"linux": "alice-aaaa", "android": "bob-bbbb"})
    a = xc.Node("linux", FakeTransport(net, "linux"), "u", "p")
    b = xc.Node("android", Dead(), "u", "p")
    rep = xc.CrossChatStage(a, b, clock=clock, log=lambda _: None).run()
    assert rep.failed_step == "ready:android" and rep.failed_layer == "local-api"


def test_scan_picks_the_transport_and_chat_lines(tmp_path: Path):
    d = tmp_path / "logs"
    d.mkdir()
    (d / "ciris-server.log").write_text(
        "INFO boot\n"
        "WARN edge: link_seal_refused peer=abc\n"
        "INFO contacts: pending — the contact completes when this key's record arrives\n"
        "INFO [DELIVERY-PROBE] canonical k ROOTED after ~8s\n"
        "DEBUG unrelated\n"
    )
    hits = xc.scan_logs([d])
    assert len(hits) == 3
    assert any("link_seal_refused" in h for h in hits)
    assert not any("unrelated" in h for h in hits)


def test_cli_scan_writes_its_output(tmp_path: Path, capsys):
    (tmp_path / "a.log").write_text("chat: accepted the pair room's invitation\n")
    out = tmp_path / "scan.txt"
    assert xc.main(["scan", "--logs", f"linux={tmp_path}", "--out", str(out)]) == 0
    assert "accepted the pair room" in out.read_text()


def test_summary_names_the_failing_step_and_the_gap():
    stage, _, _ = _stage(message_delivered=False)
    md = xc.summary_markdown(stage.run())
    assert "FAIL at `messages` [message]" in md
    assert "Reported, not enforced" in md and "not visible" in md
