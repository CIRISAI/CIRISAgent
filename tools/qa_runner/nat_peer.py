"""One side of the cross-node chat, against its OWN node only: a peer across a NAT.

`cross_platform_chat.py` drives both nodes of a pair from one machine, so it
can only reach nodes that machine can reach. A peer behind a different NAT
(node-c on a GitHub runner, the phone on cellular) is reachable only by its own
driver. Here each driver runs its half of the same steps against its own node,
and the two halves meet through the mesh alone:

  requester  add the peer by its code -> wait for mutual
  responder  see the peer's request -> accept it (the entry's own accept call)
  both       pair room (the smaller fedID founds it, edge PairRole) -> ready
             -> one message each way, each read and opened -> re-open the same
             room -> after the direct-link window, one timed message each way

Each half needs the other's fedID (and the requester needs its code) before it
starts; `drive` gets node-c's from the workflow's early `node-c-contact`
artifact and hands the locals' to the workflow as a dispatch input.

  python -m tools.qa_runner.nat_peer code --node home=http://127.0.0.1:18081
  python -m tools.qa_runner.nat_peer half --node node-c=http://127.0.0.1:18083 \\
      --role requester --peers peers.json --nonce abcd1234 --out result.json
  python -m tools.qa_runner.nat_peer drive --node home=http://127.0.0.1:18081 \\
      --node phone=http://127.0.0.1:8080 --server-tag test-0.5.242-adce9ee2
  python -m tools.qa_runner.nat_peer pair --server-tag test-0.5.242-358d4078   # both in CI
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from tools.qa_runner.cross_platform_chat import (
    LAYER_CONTACTS,
    LAYER_LOCAL_API,
    LAYER_MESSAGE,
    LAYER_ROOM,
    Clock,
    CrossChatStage,
    Deadlines,
    HttpResult,
    HttpxTransport,
    Node,
    StageReport,
    StepResult,
    _payload,
    chat_messages,
    pending_invites,
    room_ready,
    room_view,
)

ROLE_REQUESTER = "requester"
ROLE_RESPONDER = "responder"
REPO = "CIRISAI/CIRISAgent"
NODE_C = "node-c"
# The A/V step: a 60 s call, one stream each way (Eric, via edge).
AV_SECONDS, AV_RATE_HZ, AV_FRAME_BYTES = 60, 30, 256  # audio-sized: 400 B A/V MDU today (leviculum#104)
AV_JOIN_S, AV_DRAIN_S = 60.0, 15.0


@dataclass
class PeerContact:
    """What one half knows of the other before it starts."""

    name: str
    key_id: str
    code: str = ""


@dataclass
class HalfReport:
    me: str
    peer: str
    role: str
    ok: bool = False
    failed_step: Optional[str] = None
    community_id: Optional[str] = None
    creator: Optional[str] = None
    steps: List[StepResult] = field(default_factory=list)


class PeerHalf(CrossChatStage):
    """The steps of `CrossChatStage`, each run against `me` alone.

    `peer` is a Node with no reachable transport: only its name, fedID and code
    are read. Every call goes to `me`.
    """

    def __init__(
        self,
        me: Node,
        peer: PeerContact,
        role: str,
        nonce: str,
        clock: Optional[Clock] = None,
        deadlines: Optional[Deadlines] = None,
        log: Callable[[str], None] = print,
    ) -> None:
        remote = Node(peer.name, _Unreachable(), "", "", fed_id=peer.key_id, code=peer.code or None)
        super().__init__(me, remote, clock=clock, deadlines=deadlines, log=log, nonce=nonce)
        self.me, self.peer, self.role = me, remote, role
        self.report = StageReport(pair=[me.name, peer.name])
        self.av_record: Dict[str, object] = {}

    # -- one-sided steps the two-node stage does not have --

    def room_one_side(self) -> str:
        """Found the room (Creator) or accept its invite (Joiner), then wait for MY side to read ready."""
        me, peer = self.me, self.peer
        assert me.fed_id and peer.fed_id
        creator = me.fed_id < peer.fed_id
        self.report.creator = me.name if creator else peer.name
        trail: List[str] = []
        cid: List[str] = []
        if creator:

            def found(_: int) -> Optional[str]:
                r = self._call(me, "POST", "/v1/chat", {"key_id": str(peer.fed_id)})
                trail.append(r.trail("creator POST /v1/chat"))
                p = _payload(r.body)
                if r.ok and isinstance(p, dict) and p.get("community_id"):
                    cid[:] = [str(p["community_id"])]
                    return "opened"
                if r.status not in (0, 403) and r.status < 500:
                    raise self._fail("room", LAYER_ROOM, f"could not open the pair room: {r.brief()}", trail)
                return None

            if self._poll(self.d.room_open_s, found) is None:
                raise self._fail("room", LAYER_ROOM, "POST /v1/chat never opened the pair room", trail[-6:])
        else:
            seen: List[str] = []

            def invited(_: int) -> Optional[str]:
                r = self._call(me, "GET", "/v1/self/invites")
                invites = pending_invites(r.body) if r.ok else []
                seen[:] = [f"invites {[str(i.get('group_id')) for i in invites]}"]
                # The invite names its proposer in some field; prefer the one from this peer,
                # else the only pending one (each driver's node is fresh for this run).
                mine = [i for i in invites if str(peer.fed_id) in json.dumps(i)] or (invites if len(invites) == 1 else [])
                if not mine:
                    return None
                inv = mine[0]
                acc = self._call(me, "POST", f"/v1/self/invites/{inv.get('proposal_id')}/accept")
                trail.append(acc.trail(f"joiner accept {inv.get('proposal_id')}"))
                if not acc.ok:
                    raise self._fail("room", LAYER_ROOM, f"could not accept the invite: {acc.brief()}", trail[-6:])
                cid[:] = [str(inv.get("group_id"))]
                return "accepted"

            if self._poll(self.d.invite_s, invited) is None:
                raise self._fail(
                    "room",
                    LAYER_ROOM,
                    f"{peer.name}'s pair-room invite never reached {me.name} within {self.d.invite_s:.0f}s",
                    seen + trail[-6:],
                )
        self.report.community_id = cid[0]
        last: Dict[str, str] = {}

        def ready(_: int) -> Optional[str]:
            r = self._call(me, "GET", f"/v1/chat/{cid[0]}/messages")
            view = room_view(r)
            if last.get("v") != view:
                trail.append(f"{me.name} GET messages -> {view}")
                last["v"] = view
            return "ready" if r.ok and room_ready(r.body) else None

        if self._poll(self.d.room_open_s, ready) is None:
            raise self._fail(
                "room", LAYER_ROOM, f"room {cid[0]} never read ready on {me.name} within {self.d.room_open_s:.0f}s", trail[-12:]
            )
        return f"room {cid[0]}: {'founded' if creator else 'joined'} by {me.name}, ready on {me.name}'s side"

    def send(self, cid: str, text: str, step: str) -> None:
        last: List[HttpResult] = []

        def attempt(_: int) -> Optional[str]:
            r = self._call(self.me, "POST", f"/v1/chat/{cid}/messages", {"body": text})
            last[:] = [r]
            if r.ok:
                return "sent"
            if 400 <= r.status < 500:
                raise self._fail(step, LAYER_MESSAGE, f"{self.me.name} could not send: {r.brief()}")
            return None

        if self._poll(self.d.send_s, attempt) is None:
            raise self._fail(
                step, LAYER_MESSAGE, f"{self.me.name} could not send within {self.d.send_s:.0f}s: "
                f"{last[0].brief() if last else 'no attempt'}"
            )

    def read(self, cid: str, text: str, step: str) -> float:
        """Seconds until `text` (the peer's) reads opened on my side."""
        started = self.clock.now()
        seen: List[str] = []

        def attempt(_: int) -> Optional[str]:
            r = self._call(self.me, "GET", f"/v1/chat/{cid}/messages")
            for m in chat_messages(r.body) if r.ok else []:
                if m.get("body") != text:
                    continue
                if m.get("mine") is False:
                    return "opened"
                seen[:] = [f"present but unopened: {m.get('unopened_reason')} {m.get('unopened_detail') or ''}"]
            return None

        if self._poll(self.d.receive_s, attempt) is None:
            raise self._fail(
                step, LAYER_MESSAGE,
                f"{self.me.name} never read {self.peer.name}'s message within {self.d.receive_s:.0f}s"
                + (f" ({seen[0]})" if seen else " (the row never arrived)"),
            )
        return self.clock.now() - started

    def text(self, kind: str, src: str, dst: str) -> str:
        return f"nat-peer {kind} {src}->{dst} {self.nonce}"

    def messages_one_side(self, cid: str) -> str:
        me, peer = self.me.name, self.peer.name
        self.send(cid, self.text("hello", me, peer), "messages")
        took = self.read(cid, self.text("hello", peer, me), "messages")
        return f"sent one; {peer}'s read and opened {took:.0f}s after mine was sent"

    def reopen_one_side(self, cid: str) -> str:
        r = self._call(self.me, "POST", "/v1/chat", {"key_id": str(self.peer.fed_id)})
        p = _payload(r.body)
        if not (r.ok and isinstance(p, dict)):
            raise self._fail("reopen", LAYER_ROOM, f"could not re-open the existing chat: {r.brief()}")
        if str(p.get("community_id")) != cid:
            raise self._fail("reopen", LAYER_ROOM, f"re-open answered room {p.get('community_id')!r}, not {cid}")
        return f"re-open returned the same room {cid}"

    def file_body(self, src: str, size: int) -> bytes:
        """The file `src` sends: the same bytes on both runners, so each can check the other's."""
        block = hashlib.sha256(f"{self.nonce} {src} {size}".encode()).digest()
        return (block * (size // len(block) + 1))[:size]

    def files_one_side(self, cid: str, label: str) -> str:
        """Each side puts a file in the room, then opens the peer's and checks every byte."""
        me, peer, size, step = self.me.name, self.peer.name, FILE_SIZES[label], f"files:{label}"
        r = self._call(
            self.me,
            "POST",
            "/v1/files",
            {
                "cohort": "community",
                "room_id": cid,
                "bytes_base64": base64.b64encode(self.file_body(me, size)).decode(),
                "media_type": "application/octet-stream",
                "filename": f"nat-peer-{me}-{label}-{self.nonce}.bin",
            },
        )
        if not r.ok:
            raise self._fail(step, LAYER_MESSAGE, f"{me} could not put a {size} byte file in the room: {r.brief()}")
        started = self.clock.now()
        name, want = f"nat-peer-{peer}-{label}-{self.nonce}.bin", self.file_body(peer, size)
        room = f"cohort=community&room_id={urllib.parse.quote(cid, safe='')}"
        seen: List[str] = []

        def attempt(_: int) -> Optional[str]:
            listed = self._call(self.me, "GET", f"/v1/drive?{room}&limit=200")
            page = _payload(listed.body) if listed.ok else None
            for entry in page.get("entries", []) if isinstance(page, dict) else []:
                # A row held but not opened here lists no name, so it isn't a missing row.
                if entry.get("filename") is None and entry.get("author_key_id") != self.me.fed_id:
                    seen[:] = [f"listed sealed, {entry.get('description')}, bytes={entry.get('bytes')}"]
                if entry.get("filename") != name:
                    continue
                seen[:] = [f"listed, bytes={entry.get('bytes')}"]
                got = self._call(self.me, "GET", f"/v1/files/{entry.get('attestation_id')}?{room}")
                opened = _payload(got.body) if got.ok else None
                if not isinstance(opened, dict):
                    seen[:] = [f"listed, open answered {got.brief()}"]
                    return None
                if base64.b64decode(str(opened.get("bytes_base64", ""))) != want:
                    raise self._fail(step, LAYER_MESSAGE, f"{peer}'s {size} byte file opened with different bytes")
                return "opened"
            return None

        if self._poll(self.d.receive_s, attempt) is None:
            raise self._fail(
                step, LAYER_MESSAGE,
                f"{me} never opened {peer}'s {size} byte file within {self.d.receive_s:.0f}s ({seen[0] if seen else 'never listed'})",
            )
        return f"{size} bytes each way; {peer}'s opened and matched {self.clock.now() - started:.0f}s after mine went up"

    def timed_one_side(self, cid: str) -> str:
        """After the direct-link window: send, then time the peer's arrival from my send."""
        wait = (self.room_ready_at or self.clock.now()) + self.DIRECT_WINDOW_S - self.clock.now()
        if wait > 0:
            self.log(f"[nat-peer {self.me.name}<->{self.peer.name}] waiting {wait:.0f}s for the direct-link window")
            self.clock.sleep(wait)
        me, peer = self.me.name, self.peer.name
        self.send(cid, self.text("timed", me, peer), "timed")
        took = self.read(cid, self.text("timed", peer, me), "timed")
        return f"{peer}->{me} opened {took:.1f}s after {me} sent (both send at room-ready + {self.DIRECT_WINDOW_S:.0f}s)"

    def direct_round_trip(self, cid: str, ceiling_secs: float) -> str:
        """Run once the link is punched: one round trip, timed by the requester.

        The two runners' clocks can't be compared, so the requester sends, the
        responder answers the moment it reads that, and the requester times the
        round trip against twice the one-way ceiling. Each side reports its own legs,
        so a slow total says which part to look at; the ceiling is on the total.
        """
        me, peer = self.me.name, self.peer.name
        ping, pong = f"nat-peer direct ping {self.nonce}", f"nat-peer direct pong {self.nonce}"
        if self.role == ROLE_RESPONDER:
            took = self.read(cid, ping, "direct")
            answering = self.clock.now()
            self.send(cid, pong, "direct")
            return (
                f"{me} answered {peer}'s ping {took:.1f}s after it started listening; "
                f"send call {self.clock.now() - answering:.2f}s"
            )
        started = self.clock.now()
        self.send(cid, ping, "direct")
        sent = self.clock.now()
        self.read(cid, pong, "direct")
        round_trip = self.clock.now() - started
        detail = (
            f"{me}->{peer}->{me} round trip {round_trip:.2f}s (ceiling {2 * ceiling_secs:.0f}s): "
            f"send call {sent - started:.2f}s, then {round_trip - (sent - started):.2f}s until the reply opened"
        )
        if round_trip > 2 * ceiling_secs:
            raise self._fail("direct", LAYER_MESSAGE, detail)
        return detail

    def av_call(self, cid: str, seconds: int = AV_SECONDS, rate_hz: int = AV_RATE_HZ, frame_bytes: int = AV_FRAME_BYTES) -> str:
        """A call in the pair room: one generated stream each way, then the stats edge kept.

        Server 0.5.245's QA call routes (node runs with CIRIS_QA_CALLS=1). Both
        sides join, wait until the call has a leg, stream for `seconds`, keep
        listening for the drain, then leave. The peer's frames arriving here is
        the pass; the rest (late, stale, leg kind) is recorded for edge in
        `self.av_record`, whether or not the step passed.
        """
        me, peer, step = self.me.name, self.peer.name, "av"
        started = self._call(self.me, "POST", "/v1/qa/call/start", {"room": cid, "relay": False})  # type: ignore[dict-item]
        if not started.ok:
            self.av_record = {"joined": started.brief()}
            raise self._fail(step, LAYER_MESSAGE, f"{me} could not join the call: {started.brief()}")
        joined_at = self.clock.now()
        last: Dict[str, object] = {}

        def stats() -> Dict[str, object]:
            r = self._call(self.me, "GET", f"/v1/qa/call/stats?room={urllib.parse.quote(cid, safe='')}")
            got = _payload(r.body) if r.ok else None
            if isinstance(got, dict):
                last.clear()
                last.update(got)
            return last

        def has_leg(_: int) -> Optional[str]:
            call = stats().get("call")
            return "leg up" if isinstance(call, dict) and call.get("legs") else None

        leg_wait = self._poll(AV_JOIN_S, has_leg)
        # A leg's budget is its link's Channel limit less chunk overhead; over it, publish is refused.
        budget = _dig(last, "call", "frame_budget_bytes")
        if isinstance(budget, int) and budget > 0:
            frame_bytes = max(16, min(frame_bytes, budget))
        stream = self._call(
            self.me, "POST", "/v1/qa/call/stream",
            {"room": cid, "rate_hz": rate_hz, "frame_bytes": frame_bytes, "seconds": seconds},  # type: ignore[dict-item]
        )
        if not stream.ok:
            self._call(self.me, "POST", "/v1/qa/call/stop", {"room": cid})
            raise self._fail(step, LAYER_MESSAGE, f"{me} could not start its stream: {stream.brief()}")
        self.clock.sleep(seconds + AV_DRAIN_S)
        stats()
        stop = self._call(self.me, "POST", "/v1/qa/call/stop", {"room": cid})
        final = _payload(stop.body) if stop.ok else None
        self.av_record = record = {
            "joined": _payload(started.body),
            "leg_up_s": None if leg_wait is None else round(self.clock.now() - joined_at - seconds - AV_DRAIN_S, 1),
            "last_stats": dict(last),
            "stop": final if isinstance(final, dict) else stop.brief(),
            "asked": {"seconds": seconds, "rate_hz": rate_hz, "frame_bytes": frame_bytes, "frame_budget_bytes": budget},
        }
        # The stop body carries the stats at its top level, beside "room" and "summary".
        body = final if isinstance(final, dict) else last
        detail = av_summary(body if isinstance(body, dict) else {}, seconds * rate_hz)
        received = _dig(body, "received", "frames")
        if not isinstance(received, int) or received <= 0:
            raise self._fail(step, LAYER_MESSAGE, f"{me} heard none of {peer}'s frames: {detail}")
        return f"{peer}->{me}: {detail}"

    # -- the half --

    def run_half(self) -> HalfReport:
        me, peer = self.me, self.peer
        rep = HalfReport(me.name, peer.name, self.role)
        plan: List[Tuple[str, str, Callable[[], str]]] = [
            (f"ready:{me.name}", LAYER_LOCAL_API, lambda: self.ready(me)),
            (f"code:{me.name}", LAYER_CONTACTS, lambda: self.contact_code(me)),
        ]
        if self.role == ROLE_REQUESTER:
            plan += [
                (f"add:{me.name}->{peer.name}", LAYER_CONTACTS, lambda: self.add(me, peer)),
                (f"mutual:{me.name}", LAYER_CONTACTS, lambda: self.mutual(me, peer)),
            ]
        else:
            plan += [
                (f"request:{me.name}<-{peer.name}", LAYER_CONTACTS, lambda: self.request_seen(me, peer)),
                (f"accept:{me.name}->{peer.name}", LAYER_CONTACTS, lambda: self.accept_request(me, peer)),
                (f"cleared:{me.name}", LAYER_CONTACTS, lambda: self.request_cleared(me, peer)),
            ]
        plan.append(("room", LAYER_ROOM, self.room_one_side))
        for name, layer, fn in plan:
            if not self._step(name, layer, fn).ok:
                return self._finish_half(rep)
        cid = str(self.report.community_id)
        self.room_ready_at = self.clock.now()
        for name, layer, fn2 in (
            ("messages", LAYER_MESSAGE, lambda: self.messages_one_side(cid)),
            ("reopen", LAYER_ROOM, lambda: self.reopen_one_side(cid)),
            ("files:small", LAYER_MESSAGE, lambda: self.files_one_side(cid, "small")),
            ("files:large", LAYER_MESSAGE, lambda: self.files_one_side(cid, "large")),
        ):
            if not self._step(name, layer, fn2).ok:
                return self._finish_half(rep)
        self._step("timed", LAYER_MESSAGE, lambda: self.timed_one_side(cid), enforced=False)
        return self._finish_half(rep)

    def _finish_half(self, rep: HalfReport) -> HalfReport:
        rep.steps = list(self.report.steps)
        rep.community_id, rep.creator = self.report.community_id, self.report.creator
        failed = next((s for s in rep.steps if not s.ok and s.enforced), None)
        rep.ok = failed is None
        rep.failed_step = failed.step if failed else None
        return rep


class _Unreachable:
    """The peer's transport: never called (every step talks to `me`)."""

    def request(self, method: str, path: str, body: Optional[Dict[str, str]] = None, token: Optional[str] = None) -> HttpResult:
        raise AssertionError(f"a half must not call the peer's node ({method} {path})")


# ── CLI ─────────────────────────────────────────────────────────────────────


def _node(spec: str, username: str, password: str) -> Node:
    name, _, url = spec.partition("=")
    if not name or not url:
        raise SystemExit(f"--node must be NAME=URL, got {spec!r}")
    return Node(name, HttpxTransport(url, 30.0), username, password)


def contact_of(node: Node) -> PeerContact:
    """Log in and read the node's own contact code (polls until the node can produce one)."""
    stage = CrossChatStage(node, node, log=lambda _l: None)
    stage.ready(node)
    stage.contact_code(node)
    return PeerContact(node.name, str(node.fed_id), str(node.code))


def run_halves(me_spec: str, peers: List[PeerContact], role: str, nonce: str, username: str, password: str) -> List[HalfReport]:
    """One half per peer, concurrently, each with its own owner session on `me`."""
    out: Dict[str, HalfReport] = {}
    lock = threading.Lock()

    def one(peer: PeerContact) -> None:
        me = _node(me_spec, username, password)

        def log(line: str) -> None:
            with lock:
                print(f"[{me.name}<->{peer.name}] {line}", flush=True)

        out[peer.name] = PeerHalf(me, peer, role, nonce, log=log).run_half()

    threads = [threading.Thread(target=one, args=(p,), daemon=True) for p in peers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return [out[p.name] for p in peers if p.name in out]


def _write(path: Optional[Path], obj: object) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=lambda o: asdict(o)))


_FETCH_LOCK = threading.Lock()
#: One under the node's 1 MiB inline cap, one over it, which the edge seals as a chunk DAG.
FILE_SIZES = {"small": 64 * 1024, "large": 8 * 1024 * 1024}


def _dig(obj: object, *keys: str) -> object:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def av_summary(stats: Dict[str, object], expected: int) -> str:
    """One line edge reads: frames each way, delay, late/stale, and the leg each stream rode."""
    streams = _dig(stats, "call", "streams")
    legs = ", ".join(
        f"{s.get('leg')}(parent_changes={s.get('parent_changes')})" for s in streams if isinstance(s, dict)
    ) if isinstance(streams, list) else "no streams"
    return (
        f"sent {_dig(stats, 'sent', 'frames')} (refused {_dig(stats, 'sent', 'publish_refused')}"
        f" last_error {_dig(stats, 'sent', 'last_publish_error')}, "
        f"legs {_dig(stats, 'sent', 'legs')}); received {_dig(stats, 'received', 'frames')}/{expected} "
        f"p50 {_dig(stats, 'received', 'delay_ms_p50')} p95 {_dig(stats, 'received', 'delay_ms_p95')} "
        f"max {_dig(stats, 'received', 'delay_ms_max')} ms (incl. clock skew); "
        f"expired_late {_dig(stats, 'call', 'reorder', 'expired_late')}, "
        f"stale_dropped {_dig(stats, 'call', 'alm', 'stale_dropped')}; streams: {legs}; "
        f"tier {_dig(stats, 'call', 'service_tier')}"
    )


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def drive(local_specs: List[str], server_tag: str, ref: str, out: Path, username: str, password: str) -> int:
    """Start node-c in CI, run every local responder half against it, collect node-c's side."""
    nonce = secrets.token_hex(4)
    locals_ = [_node(s, username, password) for s in local_specs]
    contacts = [contact_of(n) for n in locals_]
    for c in contacts:
        print(f"[drive] {c.name}: fedID {c.key_id}")
    branch = f"nat-peer/{nonce}"
    request: Dict[str, object] = {"nonce": nonce, "server_tag": server_tag, "peers": [asdict(c) for c in contacts]}
    _push_request(ref, branch, request)
    started = time.time()
    try:
        return _drive_run(branch, nonce, local_specs, out, username, password, started)
    finally:
        subprocess.run(["git", "push", "-q", "origin", "--delete", branch], capture_output=True)


def _push_request(ref: str, branch: str, request: Dict[str, object]) -> None:
    """Push `ref` plus .nat-peer/request.json to `branch` without touching the worktree."""
    def git(*args: str, env: Optional[Dict[str, str]] = None, stdin: Optional[str] = None) -> str:
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True, env=env, input=stdin).stdout.strip()

    with _FETCH_LOCK:  # FETCH_HEAD is one file, and pairs can start together.
        subprocess.run(["git", "fetch", "-q", "origin", ref], check=True)
        base = git("rev-parse", "FETCH_HEAD")
    blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(request, indent=2) + "\n")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        git("read-tree", base, env=env)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},.nat-peer/request.json", env=env)
        tree = git("write-tree", env=env)
    commit = git("commit-tree", tree, "-p", base, "-m", f"qa(nat-peer): node-c request {request['nonce']}")
    git("push", "-q", "origin", f"{commit}:refs/heads/{branch}")


def _drive_run(branch: str, nonce: str, local_specs: List[str], out: Path, username: str, password: str, started: float) -> int:
    run_id = ""
    while not run_id and time.time() - started < 180:
        time.sleep(5)
        rows = json.loads(_gh("run", "list", "-R", REPO, "-b", branch, "-L", "5", "--json", "databaseId,workflowName"))
        run_id = next((str(r["databaseId"]) for r in rows if r.get("workflowName", "").startswith("NAT peer")), "")
    if not run_id:
        print(f"[drive] no run started for {branch}")
        return 2
    print(f"[drive] node-c run https://github.com/{REPO}/actions/runs/{run_id} (nonce {nonce})")

    # node-c's contact arrives as an artifact as soon as its node is claimed and announced.
    nodec: Optional[PeerContact] = None
    with tempfile.TemporaryDirectory() as tmp:
        while nodec is None and time.time() - started < 1500:
            time.sleep(15)
            names = _gh("api", f"repos/{REPO}/actions/runs/{run_id}/artifacts", "--jq", ".artifacts[].name").split()
            if "node-c-contact" in names:
                _gh("run", "download", run_id, "-R", REPO, "-n", "node-c-contact", "-D", tmp)
                nodec = PeerContact(**json.loads((Path(tmp) / "contact.json").read_text()))
            elif json.loads(_gh("run", "view", run_id, "-R", REPO, "--json", "status"))["status"] == "completed":
                break
    if nodec is None:
        print("[drive] node-c never published its contact; see the run")
        return 2
    print(f"[drive] node-c: fedID {nodec.key_id}")

    reports = []
    threads = []
    lock = threading.Lock()
    for spec in local_specs:

        def one(spec: str = spec) -> None:
            r = run_halves(spec, [nodec], ROLE_RESPONDER, nonce, username, password)
            with lock:
                reports.extend(r)

        threads.append(threading.Thread(target=one, daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    subprocess.run(["gh", "run", "watch", run_id, "-R", REPO, "--exit-status", "--interval", "30"], capture_output=True)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "run", "download", run_id, "-R", REPO, "-n", "node-c-results", "-D", str(out / "node-c")], check=False)
    _write(out / "local_halves.json", reports)
    remote = []
    rpath = out / "node-c" / "result.json"
    if rpath.exists():
        remote = json.loads(rpath.read_text())
    ok = bool(reports) and all(r.ok for r in reports) and bool(remote) and all(r.get("ok") for r in remote)
    for r in reports:
        print(f"[drive] {r.me}<->{r.peer} ({r.role}): {'PASS' if r.ok else 'FAIL at ' + str(r.failed_step)}")
        for s in r.steps:
            print(f"    {s.step:28} {'ok' if s.ok else 'FAIL'} {s.elapsed_s:5.0f}s {s.detail[:150]}")
    for r in remote:
        print(f"[drive] {r['me']}<->{r['peer']} ({r['role']}): {'PASS' if r.get('ok') else 'FAIL at ' + str(r.get('failed_step'))}")
        for s in r.get("steps", []):
            print(f"    {s['step']:28} {'ok' if s['ok'] else 'FAIL'} {s['elapsed_s']:5.0f}s {s['detail'][:150]}")
    print(f"[drive] {'PASS' if ok else 'FAIL'}; node-c's logs and result under {out / 'node-c'}")
    return 0 if ok else 1


def _wait_for_run(run_id: str, poll_s: float = 30.0) -> None:
    """Until the run ends. `gh run watch` can return early, and the branch goes when this does."""
    while True:
        try:
            if json.loads(_gh("run", "view", run_id, "-R", REPO, "--json", "status"))["status"] == "completed":
                return
        except subprocess.CalledProcessError:
            pass  # a passing GitHub error is not the end of the run
        time.sleep(poll_s)


def pair(server_tag: str, ref: str, out: Path) -> int:
    """Both nodes in CI (cross-nat-pair.yml), each on its own runner; collect both sides."""
    nonce = secrets.token_hex(4)
    branch = f"nat-pair/{nonce}"
    _push_request(ref, branch, {"nonce": nonce, "server_tag": server_tag})
    started = time.time()
    try:
        run_id = ""
        while not run_id and time.time() - started < 180:
            time.sleep(5)
            rows = json.loads(_gh("run", "list", "-R", REPO, "-b", branch, "-L", "5", "--json", "databaseId,workflowName"))
            run_id = next((str(r["databaseId"]) for r in rows if r.get("workflowName") == "Cross-NAT pair"), "")
        if not run_id:
            print(f"[pair] no run started for {branch}")
            return 2
        out.mkdir(parents=True, exist_ok=True)
        (out / "run-id.txt").write_text(run_id + "\n", encoding="utf-8")
        print(f"[pair] https://github.com/{REPO}/actions/runs/{run_id} (nonce {nonce}, server {server_tag or 'the pin'})", flush=True)
        _wait_for_run(run_id)
        out.mkdir(parents=True, exist_ok=True)
        ok = True
        for name in ("node-a", "node-b"):
            subprocess.run(["gh", "run", "download", run_id, "-R", REPO, "-n", f"results-{name}", "-D", str(out / name)],
                           capture_output=True)
            rpath = out / name / "result.json"
            halves = json.loads(rpath.read_text()) if rpath.exists() else []
            ok = ok and bool(halves) and all(h.get("ok") for h in halves)
            for h in halves or [{"me": name, "peer": "?", "role": "?", "ok": False, "failed_step": "no result", "steps": []}]:
                print(f"[pair] {h['me']}<->{h['peer']} ({h['role']}): {'PASS' if h.get('ok') else 'FAIL at ' + str(h.get('failed_step'))}")
                for st in h.get("steps", []):
                    print(f"    {st['step']:28} {'ok' if st['ok'] else 'FAIL'} {st['elapsed_s']:5.0f}s {st['detail'][:150]}")
            print(f"[pair] {name} time to contact: {contact_times(halves)}")
            timed = out / name / "direct-timed.json"
            if timed.exists():
                print(f"[pair] {name} direct: {json.loads(timed.read_text()).get('detail', '')}")
            av = out / name / "av.json"
            if av.exists():
                got = json.loads(av.read_text())
                print(f"[pair] {name} av: {'ok' if got.get('ok') else 'FAIL'} {got.get('detail', '')[:400]}")
            gate = out / name / "trace-gate.log"
            tail = gate.read_text().strip().splitlines()[-1:] if gate.exists() else ["no trace-gate log"]
            print(f"[pair] {name} trace gate: {tail[0][:200]}")
        conclusion = json.loads(_gh("run", "view", run_id, "-R", REPO, "--json", "conclusion"))["conclusion"]
        print(f"[pair] run {conclusion}; chat {'PASS' if ok else 'FAIL'}; artifacts under {out}")
        return 0 if ok and conclusion == "success" else 1
    finally:
        subprocess.run(["git", "push", "-q", "origin", "--delete", branch], capture_output=True)


def contact_times(halves: Sequence[dict]) -> str:
    """Seconds each contact step took, measured against the 30 s target for a relayed add."""
    parts = []
    for half in halves:
        for st in half.get("steps", []):
            if st["step"].split(":")[0] in ("add", "request", "mutual"):
                parts.append(f"{st['step']} {st['elapsed_s']:.0f}s{'' if st['ok'] else ' FAILED'}")
    return ", ".join(parts) or "no contact steps recorded"


def pair_repeated(server_tag: str, ref: str, out: Path, repeat: int, parallel: int = 1) -> int:
    """One sample can't give a rate: run every pair, and fail if any of them did."""
    if repeat <= 1:
        return pair(server_tag, ref, out)
    with ThreadPoolExecutor(max_workers=max(parallel, 1)) as pool:
        codes = list(pool.map(lambda n: pair(server_tag, ref, out / f"run-{n}"), range(1, repeat + 1)))
    print(f"[pair] {codes.count(0)} of {repeat} passed: {codes}")
    return 0 if not any(codes) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", default="qaadmin")
    ap.add_argument("--password", default="qa_test_password_12345")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("code", help="print the node's own contact as JSON")
    c.add_argument("--node", required=True)
    c.add_argument("--out", type=Path, default=None)
    h = sub.add_parser("half", help="run one side against each peer in --peers")
    h.add_argument("--node", required=True)
    h.add_argument("--role", choices=[ROLE_REQUESTER, ROLE_RESPONDER], required=True)
    h.add_argument("--peers", type=Path, required=True, help='JSON [{"name","key_id","code"}]')
    h.add_argument("--nonce", required=True)
    h.add_argument("--out", type=Path, default=None)
    h.add_argument("--summary", type=Path, default=None)
    t = sub.add_parser("direct-timed", help="one timed round trip after the link went direct")
    t.add_argument("--node", required=True)
    t.add_argument("--role", choices=[ROLE_REQUESTER, ROLE_RESPONDER], required=True)
    t.add_argument("--peers", type=Path, required=True)
    t.add_argument("--nonce", required=True)
    t.add_argument("--result", type=Path, required=True, help="this node's half result, for the room id")
    t.add_argument("--ceiling-secs", type=float, default=2.0, help="one-way ceiling")
    t.add_argument("--out", type=Path, default=None)
    v = sub.add_parser("av", help="a 60 s call in the pair room, one stream each way (needs CIRIS_QA_CALLS=1)")
    v.add_argument("--node", required=True)
    v.add_argument("--role", choices=[ROLE_REQUESTER, ROLE_RESPONDER], required=True)
    v.add_argument("--peers", type=Path, required=True)
    v.add_argument("--nonce", required=True)
    v.add_argument("--result", type=Path, required=True, help="this node's half result, for the room id")
    v.add_argument("--seconds", type=int, default=AV_SECONDS)
    v.add_argument("--out", type=Path, default=None)
    d = sub.add_parser("drive", help="dispatch node-c in CI and run the local halves against it")
    d.add_argument("--node", action="append", required=True)
    d.add_argument("--server-tag", default="")
    d.add_argument("--ref", default="main")
    d.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"nat-peer-{int(time.time())}")
    pr = sub.add_parser("pair", help="both nodes in CI, each on its own runner (cross-nat-pair.yml)")
    pr.add_argument("--server-tag", default="")
    pr.add_argument("--ref", default="main")
    pr.add_argument("--repeat", type=int, default=1, help="run the pair this many times")
    pr.add_argument("--parallel", type=int, default=1, help="how many of them run at once")
    pr.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"nat-pair-{int(time.time())}")
    args = ap.parse_args(argv)

    if args.cmd == "code":
        contact = contact_of(_node(args.node, args.username, args.password))
        _write(args.out, contact)
        print(json.dumps(asdict(contact)))
        return 0
    if args.cmd == "direct-timed":
        peer = PeerContact(**json.loads(args.peers.read_text())[0])
        me = _node(args.node, args.username, args.password)
        half = PeerHalf(me, peer, args.role, args.nonce, deadlines=Deadlines(poll_s=0.2, send_s=30.0, receive_s=300.0))
        half._login(me)
        cid = str(json.loads(args.result.read_text())[0]["community_id"])
        step = half._step("direct", LAYER_MESSAGE, lambda: half.direct_round_trip(cid, args.ceiling_secs))
        _write(args.out, asdict(step))
        return 0 if step.ok else 1
    if args.cmd == "av":
        peer = PeerContact(**json.loads(args.peers.read_text())[0])
        me = _node(args.node, args.username, args.password)
        half = PeerHalf(me, peer, args.role, args.nonce, deadlines=Deadlines(poll_s=2.0, send_s=30.0, receive_s=300.0))
        half._login(me)
        cid = str(json.loads(args.result.read_text())[0]["community_id"])
        step = half._step("av", LAYER_MESSAGE, lambda: half.av_call(cid, seconds=args.seconds))
        _write(args.out, {**asdict(step), "record": half.av_record})
        return 0 if step.ok else 1
    if args.cmd == "half":
        peers = [PeerContact(**p) for p in json.loads(args.peers.read_text())]
        reports = run_halves(args.node, peers, args.role, args.nonce, args.username, args.password)
        _write(args.out, reports)
        if args.summary:
            lines = []
            for r in reports:
                lines += [f"### {r.me} <-> {r.peer} ({r.role}): {'PASS' if r.ok else f'FAIL at `{r.failed_step}`'}", "",
                          "| step | result | seconds | detail |", "|---|---|---|---|"]
                lines += [f"| {s.step} | {'ok' if s.ok else 'FAIL'} | {s.elapsed_s:.0f} | {s.detail.replace('|', '/')[:240]} |"
                          for s in r.steps]
                lines.append("")
            with open(args.summary, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        return 0 if reports and all(r.ok for r in reports) else 1
    if args.cmd == "pair":
        return pair_repeated(args.server_tag, args.ref, args.out, args.repeat, args.parallel)
    return drive(args.node, args.server_tag, args.ref, args.out, args.username, args.password)


if __name__ == "__main__":
    sys.exit(main())
