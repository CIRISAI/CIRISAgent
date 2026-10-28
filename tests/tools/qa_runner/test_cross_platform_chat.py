"""The cross-platform chat stage, against a fake two-node network on a fake clock.

The fake models only what the stage depends on, in the server's own shapes
(CIRISServer src/contacts_chat.rs, membership_invites.rs, self_devices.rs):
a code add that answers 202 contacts.awaiting_key_body until the key body
"arrives", an incoming contact request that reaches the other side's
contact_requests after a replication delay and carries its own `accept`
(0.5.237, FSD/MEMBERSHIP_INVITES.md §8), `mutual` on contact rows, a pair room
only the Creator may found, an invite that reaches the
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
    request_delay_s: float = 30.0
    requests_delivered: bool = True
    #: A node before 0.5.237: /v1/self/invites has no contact_requests at all.
    has_requests_field: bool = True
    #: A broken accept that points somewhere other than POST /v1/contacts.
    accept_path: str = "/v1/contacts"
    mutual_reported: bool = True
    #: A broken server whose second POST /v1/chat founds a NEW room for the same pair.
    reopen_new_room: bool = False
    #: Message faults, applied to turns whose body contains this marker.
    drop_marker: Optional[str] = None
    duplicate_marker: Optional[str] = None
    #: A broken server that loses non-ASCII text on the way through.
    mangle_unicode: bool = False
    #: A broken server that tells the receiver a message is theirs (mine=True).
    flip_mine_marker: Optional[str] = None
    room_posts: int = 0
    #: A broken server that echoes the receiver's copy as its own (mine=True).
    receiver_sees_mine: bool = False
    # state
    contacts: Dict[str, set] = field(default_factory=dict)
    pending: Dict[Tuple[str, str], float] = field(default_factory=dict)
    added_at: Dict[Tuple[str, str], float] = field(default_factory=dict)
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
                n.added_at[(me, target)] = now
                return xc.HttpResult(200, {"key_id": n.fed[target]})
            return xc.HttpResult(202, {"reason_id": "contacts.awaiting_key_body", "converges_on_its_own": True})
        if path == "/v1/contacts":
            listed = sorted(n.contacts.get(me, set()))
            rows = [{"key_id": k, "mutual": n.mutual_reported and self._replicated(n.node_of_fed(k), me)}
                    for k in listed]
            return xc.HttpResult(200, {"contacts": rows, "total": len(rows)})
        if path == "/v1/chat" and method == "POST":
            peer = str(body["key_id"])
            if peer not in n.contacts.get(me, set()):
                return xc.HttpResult(403, {"reason_id": "chat.not_a_contact"})
            cid = "pair-" + "-".join(sorted(n.fed.values()))
            if me != n.creator():
                return xc.HttpResult(200, {"community_id": cid, "state": "awaiting_invitation"})
            if n.room is None:
                n.room, n.invite_at = cid, now + n.invite_delay_s
            elif n.seated():
                n.room_posts += 1
                if n.reopen_new_room:
                    return xc.HttpResult(200, {"community_id": cid + "-second", "state": "invited"})
            state = "open" if n.seated() else "accepted" if n.accepted_at is not None else "invited"
            return xc.HttpResult(200, {"community_id": cid, "state": state})
        if path == "/v1/self/invites":
            invites = []
            if me != n.creator() and n.room and n.invite_delivered and n.invite_at is not None and now >= n.invite_at:
                if n.accepted_at is None:
                    invites.append({"proposal_id": "prop-1", "group_id": n.room, "is_pair_room": True,
                                    "proposer_key_id": n.fed[other]})
            out = {"invitee_key_id": n.fed[me], "invites": invites}
            if n.has_requests_field:
                out["contact_requests"] = [
                    {"kind": "contact", "requester_key_id": n.fed[other], "requester_label": n.fed[other].split("-")[0],
                     "grant_attestation_id": f"grant-{other}",
                     "accept": {"method": "POST", "path": n.accept_path, "body": {"key_id": n.fed[other]}}}
                ] if (n.requests_delivered and self._replicated(other, me)
                      and n.fed[other] not in n.contacts.get(me, set())) else []
            return xc.HttpResult(200, out)
        if path == "/v1/self/invites/prop-1/accept":
            n.accepted_at = now
            return xc.HttpResult(200, {"state": "accepted", "proposal_id": "prop-1"})
        if n.room and path == f"/v1/chat/{n.room}/messages":
            if not n.seated():
                return xc.HttpResult(200, {"messages": [{"kind": "system", "body": "Waiting"}], "ready": False})
            if method == "POST":
                text = str(body["body"])
                if n.mangle_unicode:
                    text = text.encode("ascii", "replace").decode()
                att = f"att-{len(n.messages)}"
                if n.drop_marker and n.drop_marker in text:
                    return xc.HttpResult(200, {"attestation_id": att, "message": {"body": text}})
                n.messages.append(Msg(att, me, text, now + n.message_delay_s))
                if n.duplicate_marker and n.duplicate_marker in text:
                    n.messages.append(Msg(att + "b", me, text, now + n.message_delay_s))
                return xc.HttpResult(200, {"attestation_id": att, "message": {"body": body["body"]}})
            rows = []
            for m in n.messages:
                if m.author == me:
                    rows.append({"attestation_id": m.att, "kind": "message", "body": m.body, "mine": True})
                elif n.message_delivered and now >= m.delivered_at:
                    flip = bool(n.flip_mine_marker and n.flip_mine_marker in m.body)
                    rows.append({"attestation_id": m.att, "kind": "message", "body": m.body,
                                 "mine": n.receiver_sees_mine or flip})
            return xc.HttpResult(200, {"messages": rows, "ready": True, "total": len(rows)})
        return xc.HttpResult(404, {"detail": f"fake has no {method} {path}"})


def _replicated(self, adder: str, to: str) -> bool:
    """`adder`'s grant naming `to` has replicated to `to`'s node."""
    at = self.net.added_at.get((adder, to))
    return at is not None and self.net.clock.now() >= at + self.net.request_delay_s


FakeTransport._replicated = _replicated  # type: ignore[attr-defined]


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
        "add:linux->android", "request:android<-linux", "accept:android->linux",
        "cleared:android", "mutual:linux", "room", "messages", "reopen", "conversation",
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


def test_b_answers_with_the_requests_own_accept_by_fed_id_not_the_code():
    stage, net, _ = _stage()
    rep = stage.run()
    assert rep.ok, rep.to_json()
    assert rep.request is not None and rep.request["requester_key_id"] == "alice-aaaa"
    assert "label 'alice'" in _step(rep, "request:android<-linux").detail
    # B's add went in after B read the request, and B never needed A's code.
    first_b_add = net.calls.index("android POST /v1/contacts")
    assert "android GET /v1/self/invites" in net.calls[:first_b_add]
    assert "mutual: true" in _step(rep, "mutual:linux").detail


def test_negative_a_node_without_contact_requests_fails_at_request():
    """A pre-0.5.237 node: the request has no reader, and the stage says why."""
    stage, _, _ = _stage(has_requests_field=False)
    rep = stage.run()
    assert not rep.ok
    assert rep.failed_step == "request:android<-linux" and rep.failed_layer == "contacts"
    assert "predates ciris-server 0.5.237" in _step(rep, "request:android<-linux").detail
    assert _step(rep, "request:android<-linux").elapsed_s < xc.Deadlines().poll_s, "structural: no need to wait"


def test_negative_a_request_that_never_replicates_fails_at_request():
    stage, _, _ = _stage(requests_delivered=False)
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "request:android<-linux"
    assert "only by replication" in _step(rep, "request:android<-linux").detail
    assert "accept:android->linux" not in [s.step for s in rep.steps]


def test_negative_an_accept_that_is_not_the_add_route_fails_at_accept():
    stage, _, _ = _stage(accept_path="/v1/self/invites/x/accept")
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "accept:android->linux"


def test_negative_a_row_that_never_turns_mutual_fails_at_mutual():
    stage, _, _ = _stage(mutual_reported=False)
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "mutual:linux"
    assert "mutual=False" in " ".join(_step(rep, "mutual:linux").evidence)


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
    assert "REPORTED, NOT ENFORCED" not in out


def test_report_json_round_trips():
    stage, _, _ = _stage()
    data = json.loads(stage.run().to_json())
    assert data["ok"] is True and data["request"]["grant_attestation_id"] == "grant-linux"
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


def test_summary_names_the_failing_step():
    stage, _, _ = _stage(message_delivered=False)
    md = xc.summary_markdown(stage.run())
    assert "FAIL at `messages` [message]" in md
    assert "| request:android<-linux | ok |" in md


# ── reopen + conversation ───────────────────────────────────────────────────


def test_reopening_returns_the_same_room_from_both_sides():
    stage, net, _ = _stage()
    rep = stage.run()
    assert rep.ok, rep.to_json()
    assert "same room" in _step(rep, "reopen").detail
    assert net.room_posts >= 1


def test_negative_a_second_room_for_the_same_pair_fails_reopen():
    stage, _, _ = _stage(reopen_new_room=True)
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "reopen"
    assert "a second room for the same pair" in _step(rep, "reopen").detail


def test_the_conversation_carries_unicode_rtl_long_and_symbols_intact():
    stage, net, _ = _stage()
    rep = stage.run()
    assert rep.ok
    bodies = [m.body for m in net.messages]
    assert any("你好" in b and "🙂" in b for b in bodies)
    assert any("مرحبا" in b for b in bodies)
    assert any(len(b) > 1500 for b in bodies)
    assert any('"quotes"' in b and "\\" in b for b in bodies)


@pytest.mark.parametrize(
    "knob, why",
    [
        ({"drop_marker": "turn 4"}, "missing"),
        ({"duplicate_marker": "turn 5"}, "duplicated"),
        ({"mangle_unicode": True}, "missing"),
        ({"flip_mine_marker": "turn 3"}, "mine flag wrong"),
    ],
)
def test_negative_a_broken_conversation_fails_naming_what_broke(knob, why):
    stage, _, _ = _stage(**knob)
    rep = stage.run()
    assert not rep.ok and rep.failed_step == "conversation", rep.to_json()
    assert why in _step(rep, "conversation").detail


# ── diagnosis ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expect",
    [
        ("POST /v1/contacts -> 202 contacts.awaiting_key_body", "CIRISEdge#904"),
        ("contacts: CONTACT UNRESOLVED — the person is a contact", "CIRISEdge#907"),
        ("attested_key_id ciris-node-bootstrap-5pl5kvavvi resolves as neither a registered", "node keys first"),
        ("refused (membership_founding_member_unsigned): nobody joins", "founding record"),
        ("creator POST /v1/chat -> 403 chat.delegation_denied: delegated", "owner's own session"),
        ("creator POST /v1/chat -> 403 chat.author_signer_unavailable", "pen"),
        ('invitee_nodes=["ciris-node-bootstrap-uewp47am66: No(NotInAudience)"]', "no principal on the creator"),
        ("the invite was accepted but the room never became ready on both sides within 180s", "never keyed"),
    ],
)
def test_known_failures_are_named_with_where_to_look(text, expect):
    found = xc.diagnose([text])
    assert found and expect in found[0], found


def test_an_unknown_failure_is_said_to_be_unknown(capsys):
    assert xc.diagnose(["something nobody has seen"]) == []
    stage, _, out = _stage(invite_delivered=False)
    rep = stage.run()
    assert _step(rep, "room").diagnosis == [] and any("UNKNOWN" in line for line in out)


def test_a_failed_step_carries_its_diagnosis_into_the_report_and_summary():
    stage, _, _ = _stage(key_body_arrives=False)
    rep = stage.run()
    st = _step(rep, "add:linux->android")
    assert any("CIRISEdge#904" in d for d in st.diagnosis)
    md = xc.summary_markdown(rep)
    assert "**Why `add:linux->android` failed**" in md and "likely:" in md and "CIRISEdge#904" in md
    assert "CIRISEdge#904" in json.loads(rep.to_json())["steps"][-1]["diagnosis"][0]


def test_the_trail_carries_the_nodes_own_error_text():
    r = xc.HttpResult(500, {"reason_id": "chat.community_create_failed", "error": "open_pair_room: refused (x)"})
    assert r.trail("creator POST /v1/chat") == (
        "creator POST /v1/chat -> 500 chat.community_create_failed: open_pair_room: refused (x)"
    )
    assert xc.HttpResult(200, {"error": "ignored on success"}).trail("x") == "x -> 200"


def test_scan_names_likely_causes_from_node_logs(tmp_path: Path):
    (tmp_path / "ciris-server.log").write_text(
        "WARN contacts: CONTACT UNRESOLVED — the person is a contact but resolves to no node here\n"
        "WARN open_pair_room: found room x: membership refused (membership_founding_member_unsigned)\n"
    )
    out, summary = tmp_path / "scan.txt", tmp_path / "summary.md"
    assert xc.main(["scan", "--logs", f"linux={tmp_path}", "--out", str(out), "--summary", str(summary)]) == 0
    text = out.read_text()
    assert "likely causes from linux's log" in text and "CIRISEdge#907" in text and "founding record" in text
    assert "CIRISEdge#907" in summary.read_text()
