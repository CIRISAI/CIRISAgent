"""Cross-platform chat: two real nodes, two people, one conversation, through the live canonical.

WHY THIS STAGE EXISTS. Two real users (one on Linux, one on Windows) added each
other as contacts and could never chat. Nothing in the five-platform run
exercised two nodes interacting -- each platform ran the flow alone -- so the
whole person-to-person path (contact codes, the add ladder, the pair room, the
sealed message plane) had no gate at all. This stage runs it between two of the
platforms the gate already brought up (Linux desktop + Android emulator on the
linux-android runner), each owned by its own setup-created person, talking
through the live canonical.

WHAT IS ENFORCED (a fresh pair of nodes must do all of it):

  codes     each side reads its own contact code     GET  /v1/self/contact-code
  add a->b  A adds B by code, converges              POST /v1/contacts {"key_id": <code>}
  add b->a  B adds A by code, converges                (202 contacts.awaiting_key_body
                                                        while the key body is pulled over
                                                        the mesh, then listed by
                                                        GET /v1/contacts)
  room      the Creator (lexicographically smaller   POST /v1/chat {"key_id": <fedID>}
            fedID, edge PairRole) opens the pair
            room; the Joiner sees the invite and     GET  /v1/self/invites
            accepts it; both sides report ready      POST /v1/self/invites/{id}/accept
                                                     GET  /v1/chat/{cid}/messages
  messages  one message each way; each side reads   POST /v1/chat/{cid}/messages {"body"}
            the other's, opened                      GET  /v1/chat/{cid}/messages

WHAT IS REPORTED, NOT ENFORCED: whether B could see A's request BEFORE B added A
back. Today an incoming contact request has no reader: "add contact" writes only
the adder's own consent grant, GET /v1/contacts lists only grants the owner
authored, and the pair invite exists only once the Creator holds the other as a
contact. The expected answer is "not visible"; it is printed as a KNOWN GAP so the
day the server and client fix it, the report changes on its own.

Every step has its own bounded deadline sized to the canonical's ~30 s
replication round (90-180 s, never more), and a failure names the step and the
layer (local-api / contacts / room / message), with transport evidence grepped
from the node logs by the `scan` subcommand.

The logic is plain Python over a small `Transport` protocol so it is unit-tested
against a fake two-node network (tests/tools/qa_runner/test_cross_platform_chat.py).
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

# ── Wire ────────────────────────────────────────────────────────────────────

#: A request body: every route this stage calls takes flat string fields.
Body = Dict[str, str]
#: A parsed JSON object from a node (the server's shapes, read defensively).
JsonObject = Dict[str, Any]


@dataclass
class HttpResult:
    """One HTTP exchange. `status` 0 means no answer at all (`error` says why)."""

    status: int
    body: Any = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def reason_id(self) -> str:
        return str(self.body.get("reason_id") or "") if isinstance(self.body, dict) else ""

    def brief(self) -> str:
        if self.status == 0:
            return f"no answer ({self.error})"
        text = json.dumps(self.body)[:300] if self.body is not None else ""
        return f"HTTP {self.status} {text}"


class Transport(Protocol):
    """How the stage reaches one node's HTTP API."""

    def request(self, method: str, path: str, body: Optional[Body] = None, token: Optional[str] = None) -> HttpResult:
        ...


class HttpxTransport:
    """The real wire: httpx against the agent's :8080 (which forwards node routes to :4243)."""

    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def request(self, method: str, path: str, body: Optional[Body] = None, token: Optional[str] = None) -> HttpResult:
        import httpx

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            # A fresh connection per request: a node restarting under a pooled
            # socket is the dropped read CIRISServer#568 diagnosed as the harness's.
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.request(method, f"{self.base_url}{path}", json=body, headers=headers)
        except Exception as exc:  # noqa: BLE001 - every transport fault is "no answer"
            return HttpResult(0, None, f"{type(exc).__name__}: {exc}")
        try:
            parsed: Any = r.json()
        except ValueError:
            parsed = r.text[:500]
        return HttpResult(r.status_code, parsed)


class Clock(Protocol):
    def now(self) -> float:
        ...

    def sleep(self, seconds: float) -> None:
        ...


class RealClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


# ── Shapes ──────────────────────────────────────────────────────────────────


#: The layers a failure can be attributed to.
LAYER_LOCAL_API = "local-api"
LAYER_CONTACTS = "contacts"
LAYER_ROOM = "room"
LAYER_MESSAGE = "message"


@dataclass
class Deadlines:
    """Per-step bounds, sized to the canonical's ~30 s replication round."""

    ready_s: float = 180.0
    code_s: float = 120.0
    add_s: float = 180.0
    one_sided_s: float = 75.0
    invite_s: float = 180.0
    room_open_s: float = 180.0
    send_s: float = 120.0
    receive_s: float = 180.0
    poll_s: float = 10.0
    #: Re-POST a converging add every N polls (the add is idempotent).
    repost_every: int = 3


@dataclass
class Node:
    """One side of the conversation."""

    name: str
    transport: Transport
    username: str
    password: str
    token: Optional[str] = None
    fed_id: Optional[str] = None
    code: Optional[str] = None


@dataclass
class StepResult:
    step: str
    ok: bool
    layer: str
    detail: str
    elapsed_s: float = 0.0
    enforced: bool = True
    evidence: List[str] = field(default_factory=list)


@dataclass
class OneSidedReport:
    """REPORTED, NOT ENFORCED: did B see A's request before B added A back?"""

    observer: str
    requester: str
    checked: bool = False
    visible: Optional[bool] = None
    where: List[str] = field(default_factory=list)
    window_s: float = 0.0
    note: str = (
        "KNOWN GAP: an incoming contact request has no reader. 'Add contact' writes only the "
        "adder's own consent:replication:v1 grant, GET /v1/contacts lists only grants the owner "
        "authored, and the pair-room invite is sent only by POST /v1/chat from the Creator once it "
        "already holds the other as a contact. Expected today: not visible. Tracks the server + "
        "client fix; not enforced."
    )


@dataclass
class StageReport:
    pair: List[str]
    ok: bool = False
    failed_step: Optional[str] = None
    failed_layer: Optional[str] = None
    creator: Optional[str] = None
    joiner: Optional[str] = None
    fed_ids: Dict[str, Optional[str]] = field(default_factory=dict)
    community_id: Optional[str] = None
    steps: List[StepResult] = field(default_factory=list)
    one_sided: Optional[OneSidedReport] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


class StepFailed(Exception):
    def __init__(self, result: StepResult) -> None:
        super().__init__(result.detail)
        self.result = result


# ── Helpers ─────────────────────────────────────────────────────────────────


def _payload(body: Any) -> Any:
    """Node routes answer raw; agent-owned routes wrap in {"data": ...}. Read either."""
    if isinstance(body, dict) and isinstance(body.get("data"), dict) and len(body) <= 3:
        return body["data"]
    return body


def contact_key_ids(body: Any) -> List[str]:
    rows = _payload(body).get("contacts") if isinstance(_payload(body), dict) else None
    return [str(r.get("key_id")) for r in rows or [] if isinstance(r, dict) and r.get("key_id")]


def pending_invites(body: Any) -> List[JsonObject]:
    p = _payload(body)
    rows = p.get("invites") if isinstance(p, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def chat_messages(body: Any) -> List[JsonObject]:
    p = _payload(body)
    rows = p.get("messages") if isinstance(p, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def room_ready(body: Any) -> bool:
    p = _payload(body)
    return isinstance(p, dict) and p.get("ready") is True


def creator_of(a: Node, b: Node) -> Tuple[Node, Node]:
    """edge `PairRole`: the lexicographically smaller fedID founds the room."""
    assert a.fed_id and b.fed_id
    return (a, b) if a.fed_id < b.fed_id else (b, a)


# ── The stage ───────────────────────────────────────────────────────────────


class CrossChatStage:
    def __init__(
        self,
        a: Node,
        b: Node,
        clock: Optional[Clock] = None,
        deadlines: Optional[Deadlines] = None,
        log: Callable[[str], None] = print,
        nonce: Optional[str] = None,
    ) -> None:
        self.a, self.b = a, b
        self.clock = clock or RealClock()
        self.d = deadlines or Deadlines()
        self.log = log
        self.nonce = nonce or secrets.token_hex(4)
        self.report = StageReport(pair=[a.name, b.name])

    # -- plumbing --

    def _call(self, node: Node, method: str, path: str, body: Optional[Body] = None) -> HttpResult:
        r = node.transport.request(method, path, body, node.token)
        if r.status == 401 and node.token:
            # One re-login: a session minted before a backend restart is gone.
            self._login(node)
            r = node.transport.request(method, path, body, node.token)
        return r

    def _login(self, node: Node) -> HttpResult:
        r = node.transport.request(
            "POST", "/v1/auth/login", {"username": node.username, "password": node.password}, None
        )
        if r.ok:
            p = _payload(r.body)
            node.token = str(p.get("access_token") or "") if isinstance(p, dict) else ""
        return r

    def _step(self, name: str, layer: str, fn: Callable[[], str], enforced: bool = True) -> StepResult:
        started = self.clock.now()
        self.log(f"[cross-chat] {name} ...")
        try:
            detail = fn()
            result = StepResult(name, True, layer, detail, round(self.clock.now() - started, 1), enforced)
            self.log(f"[cross-chat] {name}: OK ({result.elapsed_s:.0f}s) {detail}")
        except StepFailed as exc:
            result = exc.result
            result.elapsed_s = round(self.clock.now() - started, 1)
            self.log(f"[cross-chat] {name}: FAILED [{result.layer}] after {result.elapsed_s:.0f}s: {result.detail}")
        self.report.steps.append(result)
        return result

    def _fail(self, step: str, layer: str, detail: str, evidence: Optional[List[str]] = None) -> StepFailed:
        return StepFailed(StepResult(step, False, layer, detail, evidence=list(evidence or [])))

    def _poll(self, deadline_s: float, attempt: Callable[[int], Optional[str]]) -> Optional[str]:
        """Call `attempt(i)` every poll_s until it returns a detail string or the deadline passes."""
        end = self.clock.now() + deadline_s
        i = 0
        while True:
            got = attempt(i)
            if got is not None:
                return got
            i += 1
            if self.clock.now() >= end:
                return None
            self.clock.sleep(min(self.d.poll_s, max(0.0, end - self.clock.now())))

    # -- steps --

    def ready(self, node: Node) -> str:
        last: List[HttpResult] = []

        def attempt(_: int) -> Optional[str]:
            h = node.transport.request("GET", "/v1/system/health", None, None)
            last[:] = [h]
            if not h.ok:
                return None
            lr = self._login(node)
            last[:] = [lr]
            return "health 200, owner session" if lr.ok and node.token else None

        got = self._poll(self.d.ready_s, attempt)
        if got is None:
            raise self._fail(
                f"ready:{node.name}",
                LAYER_LOCAL_API,
                f"{node.name}'s API never answered health + owner login within {self.d.ready_s:.0f}s: "
                f"{last[0].brief() if last else 'no attempt'}",
            )
        return got

    def contact_code(self, node: Node) -> str:
        last: List[HttpResult] = []

        def attempt(_: int) -> Optional[str]:
            r = self._call(node, "GET", "/v1/self/contact-code")
            last[:] = [r]
            p = _payload(r.body)
            if r.ok and isinstance(p, dict) and p.get("code") and p.get("key_id"):
                node.code, node.fed_id = str(p["code"]), str(p["key_id"])
                return (
                    f"fedID {node.fed_id}, {len(p.get('included_nodes') or [])} node(s) in the code, "
                    f"reachable_without_directory={p.get('reachable_without_directory')!r}"
                )
            return None

        got = self._poll(self.d.code_s, attempt)
        if got is None:
            raise self._fail(
                f"code:{node.name}",
                LAYER_CONTACTS,
                f"{node.name} could not produce its contact code: {last[0].brief() if last else 'no attempt'}",
            )
        return got

    def add(self, adder: Node, target: Node) -> str:
        step = f"add:{adder.name}->{target.name}"
        code, target_fed = target.code, target.fed_id
        assert code and target_fed
        trail: List[str] = []
        state = {"awaiting": False}

        def attempt(i: int) -> Optional[str]:
            if i == 0 or (state["awaiting"] and i % self.d.repost_every == 0) or not state["awaiting"]:
                r = self._call(adder, "POST", "/v1/contacts", {"key_id": code})
                trail.append(f"POST /v1/contacts -> {r.status} {r.reason_id}".rstrip())
                if r.status == 200:
                    return f"added ({'after awaiting the key body' if state['awaiting'] else 'immediately'})"
                if r.status == 202:
                    state["awaiting"] = True
                elif r.status == 0 or r.status >= 500:
                    pass  # retry: key pull unavailable / node busy
                else:
                    raise self._fail(step, LAYER_CONTACTS, f"the add was refused: {r.brief()}", trail)
            listed = self._call(adder, "GET", "/v1/contacts")
            if listed.ok and target_fed in contact_key_ids(listed.body):
                return "added (listed by GET /v1/contacts after awaiting the key body)"
            return None

        got = self._poll(self.d.add_s, attempt)
        if got is None:
            why = (
                "stuck in 202 contacts.awaiting_key_body: the target's key body never arrived over the mesh"
                if state["awaiting"]
                else "the add never succeeded"
            )
            raise self._fail(step, LAYER_CONTACTS, f"{why} within {self.d.add_s:.0f}s", trail[-6:])
        return got

    def one_sided(self, observer: Node, requester: Node) -> OneSidedReport:
        """REPORTED, NOT ENFORCED: can `observer` see `requester`'s add before adding back?"""
        rep = OneSidedReport(observer=observer.name, requester=requester.name, window_s=self.d.one_sided_s)

        def attempt(_: int) -> Optional[str]:
            contacts = self._call(observer, "GET", "/v1/contacts")
            if contacts.ok and requester.fed_id in contact_key_ids(contacts.body):
                rep.where.append("GET /v1/contacts lists the requester")
            invites = self._call(observer, "GET", "/v1/self/invites")
            if invites.ok:
                for inv in pending_invites(invites.body):
                    # The requester's own key, or ANY pair-room invite: before a
                    # mutual add nothing else could be inviting this person.
                    if inv.get("is_pair_room") is True or (
                        requester.fed_id and str(inv.get("proposer_key_id") or "") == requester.fed_id
                    ):
                        rep.where.append(f"GET /v1/self/invites holds {inv.get('proposal_id')}")
            rep.checked = rep.checked or contacts.ok or invites.ok
            return "visible" if rep.where else None

        got = self._poll(self.d.one_sided_s, attempt)
        rep.visible = bool(got) if rep.checked else None
        return rep

    def open_room(self, creator: Node, joiner: Node) -> str:
        step = "room"
        joiner_fed = joiner.fed_id
        assert creator.fed_id and joiner_fed
        trail: List[str] = []
        opened: List[JsonObject] = []

        def found(_: int) -> Optional[str]:
            r = self._call(creator, "POST", "/v1/chat", {"key_id": joiner_fed})
            trail.append(f"creator POST /v1/chat -> {r.status} {r.reason_id}".rstrip())
            p = _payload(r.body)
            if r.ok and isinstance(p, dict) and p.get("community_id"):
                opened[:] = [p]
                return str(p.get("state"))
            if r.status not in (0, 403) and r.status < 500:
                raise self._fail(step, LAYER_ROOM, f"the Creator could not open the pair room: {r.brief()}", trail)
            return None

        if self._poll(self.d.room_open_s, found) is None:
            raise self._fail(step, LAYER_ROOM, "the Creator's POST /v1/chat never opened the pair room", trail[-6:])
        cid = str(opened[0]["community_id"])
        self.report.community_id = cid
        trail.append(f"room {cid} state={opened[0].get('state')}")

        proposal: List[str] = []

        def invited(_: int) -> Optional[str]:
            r = self._call(joiner, "GET", "/v1/self/invites")
            for inv in pending_invites(r.body) if r.ok else []:
                if str(inv.get("group_id") or "") == cid:
                    proposal[:] = [str(inv.get("proposal_id"))]
                    return proposal[0]
            return None

        if self._poll(self.d.invite_s, invited) is None:
            raise self._fail(
                step,
                LAYER_ROOM,
                f"the Creator's pair-room invite for {cid} never reached the Joiner's GET /v1/self/invites "
                f"within {self.d.invite_s:.0f}s",
                trail[-6:],
            )
        acc = self._call(joiner, "POST", f"/v1/self/invites/{proposal[0]}/accept")
        trail.append(f"joiner accept {proposal[0]} -> {acc.status} {acc.reason_id}".rstrip())
        if not acc.ok:
            raise self._fail(step, LAYER_ROOM, f"the Joiner could not accept the invite: {acc.brief()}", trail[-6:])

        def both_ready(_: int) -> Optional[str]:
            states = []
            for n in (creator, joiner):
                r = self._call(n, "GET", f"/v1/chat/{cid}/messages")
                states.append(room_ready(r.body) if r.ok else False)
            return "both sides report the room ready" if all(states) else None

        if self._poll(self.d.room_open_s, both_ready) is None:
            raise self._fail(
                step,
                LAYER_ROOM,
                f"the invite was accepted but the room never became ready on both sides within "
                f"{self.d.room_open_s:.0f}s (the Creator's node must seat the Joiner, then key the room)",
                trail[-6:],
            )
        return f"room {cid}: invited, accepted ({proposal[0]}), ready on both sides"

    def exchange(self, a: Node, b: Node, cid: str) -> str:
        step = "messages"
        sent: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for src, dst in ((a, b), (b, a)):
            text = f"cross-chat {src.name}->{dst.name} {self.nonce}"
            last: List[HttpResult] = []

            def send(_: int, src: Node = src, text: str = text) -> Optional[str]:
                r = self._call(src, "POST", f"/v1/chat/{cid}/messages", {"body": text})
                last[:] = [r]
                p = _payload(r.body)
                if r.ok and isinstance(p, dict):
                    return str(p.get("attestation_id") or "")
                if 400 <= r.status < 500:
                    raise self._fail(step, LAYER_MESSAGE, f"{src.name} could not send: {r.brief()}")
                return None

            att = self._poll(self.d.send_s, send)
            if att is None:
                raise self._fail(
                    step,
                    LAYER_MESSAGE,
                    f"{src.name} could not send into {cid} within {self.d.send_s:.0f}s: "
                    f"{last[0].brief() if last else 'no attempt'}",
                )
            sent[(src.name, dst.name)] = (text, att)

        for (src_name, dst_name), (text, att_id) in sent.items():
            dst = a if dst_name == a.name else b
            seen: List[str] = []

            def received(_: int, dst: Node = dst, text: str = text, att: str = att_id) -> Optional[str]:
                r = self._call(dst, "GET", f"/v1/chat/{cid}/messages")
                for m in chat_messages(r.body) if r.ok else []:
                    same = (att and m.get("attestation_id") == att) or m.get("body") == text
                    if not same:
                        continue
                    if m.get("body") == text and m.get("mine") is False:
                        return "opened"
                    seen[:] = [
                        f"row {m.get('attestation_id')} present but unopened: "
                        f"{m.get('unopened_reason')} {m.get('unopened_detail') or ''}".rstrip()
                    ]
                return None

            if self._poll(self.d.receive_s, received) is None:
                raise self._fail(
                    step,
                    LAYER_MESSAGE,
                    f"{dst_name} never read {src_name}'s message within {self.d.receive_s:.0f}s"
                    + (f" ({seen[0]})" if seen else " (the row never arrived)"),
                )
        return "one message each way, each read and opened by the other side"

    # -- the whole stage --

    def run(self) -> StageReport:
        rep = self.report
        a, b = self.a, self.b
        plan: List[Tuple[str, str, Callable[[], str]]] = [
            (f"ready:{a.name}", LAYER_LOCAL_API, lambda: self.ready(a)),
            (f"ready:{b.name}", LAYER_LOCAL_API, lambda: self.ready(b)),
            (f"code:{a.name}", LAYER_CONTACTS, lambda: self.contact_code(a)),
            (f"code:{b.name}", LAYER_CONTACTS, lambda: self.contact_code(b)),
        ]
        for name, layer, fn in plan:
            if not self._step(name, layer, fn).ok:
                return self._finish()
        rep.fed_ids = {a.name: a.fed_id, b.name: b.fed_id}
        if a.fed_id == b.fed_id:
            rep.steps.append(StepResult("codes", False, LAYER_CONTACTS, f"both nodes report one fedID {a.fed_id}"))
            return self._finish()

        if not self._step(f"add:{a.name}->{b.name}", LAYER_CONTACTS, lambda: self.add(a, b)).ok:
            return self._finish()
        # BEFORE B adds back: the known gap, reported.
        rep.one_sided = self.one_sided(b, a)
        self.log(
            f"[cross-chat] one-sided request (REPORTED, NOT ENFORCED): {b.name} "
            + (
                "COULD see" if rep.one_sided.visible else "could NOT see" if rep.one_sided.visible is False else "could not be asked about"
            )
            + f" {a.name}'s request before adding back"
            + (f" via {'; '.join(rep.one_sided.where)}" if rep.one_sided.where else "")
        )
        self.log(f"[cross-chat]   {rep.one_sided.note}")
        if not self._step(f"add:{b.name}->{a.name}", LAYER_CONTACTS, lambda: self.add(b, a)).ok:
            return self._finish()

        creator, joiner = creator_of(a, b)
        rep.creator, rep.joiner = creator.name, joiner.name
        self.log(f"[cross-chat] PairRole: Creator={creator.name} ({creator.fed_id}), Joiner={joiner.name}")
        if not self._step("room", LAYER_ROOM, lambda: self.open_room(creator, joiner)).ok:
            return self._finish()
        assert rep.community_id
        cid = rep.community_id
        if not self._step("messages", LAYER_MESSAGE, lambda: self.exchange(a, b, cid)).ok:
            return self._finish()
        return self._finish()

    def _finish(self) -> StageReport:
        rep = self.report
        failed = [s for s in rep.steps if not s.ok and s.enforced]
        rep.ok = not failed and any(s.step == "messages" and s.ok for s in rep.steps)
        if failed:
            rep.failed_step, rep.failed_layer = failed[0].step, failed[0].layer
        return rep


# ── Log scan ────────────────────────────────────────────────────────────────

#: What explains a cross-node failure, in the node's own words.
SCAN_PATTERN = re.compile(r"contacts_chat|contacts: |chat: |membership: |handshake|link_seal_refused|rooting|ROOTED|did not root")


def scan_logs(paths: Iterable[Path], tail: int = 40) -> List[str]:
    hits: List[str] = []
    for p in paths:
        files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p] if p.exists() else []
        for f in files:
            if not (f.suffix == ".log" or ".log." in f.name or f.suffix == ".txt"):
                continue
            try:
                for line in f.read_text(errors="replace").splitlines():
                    if SCAN_PATTERN.search(line):
                        hits.append(f"{f.name}: {line.strip()[:300]}")
            except OSError:
                continue
    return hits[-tail:]


# ── CLI ─────────────────────────────────────────────────────────────────────


def _parse_node(spec: str, username: str, password: str, timeout_s: float) -> Node:
    name, _, url = spec.partition("=")
    if not name or not url:
        raise SystemExit(f"--node must be NAME=URL, got {spec!r}")
    return Node(name, HttpxTransport(url, timeout_s), username, password)


def _annotate(rep: StageReport) -> None:
    """GitHub annotations: the enforced verdict and the reported gap, each said once."""
    if rep.ok:
        print(f"::notice::cross-platform chat PASSED ({' <-> '.join(rep.pair)}): mutual add, pair room, a message each way")
    else:
        step = next((s for s in rep.steps if s.step == rep.failed_step), None)
        print(
            f"::error::cross-platform chat FAILED at step '{rep.failed_step}' [layer: {rep.failed_layer}]: "
            f"{step.detail if step else ''}"
        )
    o = rep.one_sided
    if o is not None:
        verdict = {True: "VISIBLE", False: "NOT visible", None: "not observable"}[o.visible]
        print(
            f"::notice::cross-platform chat — one-sided contact request (REPORTED, NOT ENFORCED): "
            f"{o.observer} saw {o.requester}'s request before adding back: {verdict}. KNOWN GAP "
            f"(expected today: NOT visible) — an incoming contact request has no reader yet."
        )


def summary_markdown(rep: StageReport) -> str:
    """The job-summary block: one row per step, then the reported-not-enforced gap."""
    lines = [
        f"### Cross-platform chat ({' <-> '.join(rep.pair)}, through the live canonical): "
        + ("PASS" if rep.ok else f"FAIL at `{rep.failed_step}` [{rep.failed_layer}]"),
        "",
        "| step | result | layer | seconds | detail |",
        "|---|---|---|---|---|",
    ]
    for st in rep.steps:
        detail = st.detail.replace("|", "/")[:240]
        lines.append(f"| {st.step} | {'ok' if st.ok else 'FAIL'} | {st.layer} | {st.elapsed_s:.0f} | {detail} |")
    o = rep.one_sided
    if o is not None:
        verdict = {True: "VISIBLE", False: "not visible", None: "not observable"}[o.visible]
        lines += [
            "",
            f"**Reported, not enforced** - {o.observer} saw {o.requester}'s contact request before "
            f"adding back: **{verdict}** (expected today: not visible). {o.note}",
        ]
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the stage between two live nodes")
    run.add_argument("--node", action="append", required=True, help="NAME=BASE_URL, exactly twice (A then B)")
    run.add_argument("--username", required=True)
    run.add_argument("--password", required=True)
    run.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    run.add_argument("--http-timeout", type=float, default=30.0)
    run.add_argument("--poll-secs", type=float, default=Deadlines.poll_s)
    run.add_argument("--summary", type=Path, default=None, help="append a markdown summary (GITHUB_STEP_SUMMARY)")
    scan = sub.add_parser("scan", help="print the node-log lines that explain a cross-node failure")
    scan.add_argument("--logs", action="append", required=True, help="NAME=PATH (file or directory)")
    scan.add_argument("--tail", type=int, default=40)
    scan.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.cmd == "scan":
        lines: List[str] = []
        for spec in args.logs:
            name, _, path = spec.partition("=")
            hits = scan_logs([Path(path)], args.tail)
            lines.append(f"── {name} ({path}): {len(hits)} relevant line(s), last {args.tail} ──")
            lines.extend(f"  {h}" for h in hits)
        text = "\n".join(lines)
        print(text)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + "\n")
        return 0

    if len(args.node) != 2:
        raise SystemExit("--node must be given exactly twice")
    a, b = (_parse_node(s, args.username, args.password, args.http_timeout) for s in args.node)
    stage = CrossChatStage(a, b, deadlines=Deadlines(poll_s=args.poll_secs))
    rep = stage.run()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rep.to_json())
    _annotate(rep)
    if args.summary:
        try:
            with open(args.summary, "a", encoding="utf-8") as fh:
                fh.write(summary_markdown(rep))
        except OSError as exc:
            print(f"(could not write the summary to {args.summary}: {exc})")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
