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
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
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
    d = sub.add_parser("drive", help="dispatch node-c in CI and run the local halves against it")
    d.add_argument("--node", action="append", required=True)
    d.add_argument("--server-tag", default="")
    d.add_argument("--ref", default="fix/qa-harness-announce")
    d.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / f"nat-peer-{int(time.time())}")
    args = ap.parse_args(argv)

    if args.cmd == "code":
        contact = contact_of(_node(args.node, args.username, args.password))
        _write(args.out, contact)
        print(json.dumps(asdict(contact)))
        return 0
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
    return drive(args.node, args.server_tag, args.ref, args.out, args.username, args.password)


if __name__ == "__main__":
    sys.exit(main())
