"""The announce bundle: is this node discoverable on the federation, row by row?

CIRISAgent#1144 Lesson 1. Setup-complete writes the owner->node binding at
`cohort_scope: self` -- a row no peer may hold -- so a node that has not
announced is P2P-only: it cannot be placed in ANY community audience and every
room row is withheld at the other side. We read that for a day as a delivery
bug three stages downstream. `POST /v1/federation/announce` (node read-API,
owner-session gated, idempotent) re-signs the binding at federation scope and,
from ciris-server 0.5.197, walks the bundle a peer needs and returns it:

    bundle                  the rows, each `role` / `key_id` / `cohort_scope`
    bundle_expected         3 for a fabric node, 5 with one agent
    federation_discoverable every expected row is federation-visible

Assert `federation_discoverable` and `bundle_expected == 5` at setup-complete
and put the bundle in the report. Every non-ok outcome names WHICH side is
short, in the runner's own words, so a red here never reads as delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx

#: An agent node's bundle: owner key, node key, owner->node binding,
#: owner->agent (stewardship) binding, agent key.
AGENT_NODE_BUNDLE_ROWS = 5

#: Cohort scopes, narrowest to widest (persist v40 crossing scopes).
_SCOPE_RANK = {"self": 0, "family": 1, "community": 2, "affiliations": 3, "species": 4, "biosphere": 5, "federation": 6}

#: The node read-API's fixed port (tools/qa_runner/server.py NODE_HTTP_PORT).
DEFAULT_NODE_URL = "http://127.0.0.1:4243"


@dataclass
class AnnouncedRow:
    role: str
    key_id: str
    attestation_id: Optional[str] = None
    cohort_scope: Optional[str] = None

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "AnnouncedRow":
        return cls(
            role=str(raw.get("role", "?")),
            key_id=str(raw.get("key_id", "?")),
            attestation_id=(str(raw["attestation_id"]) if raw.get("attestation_id") else None),
            cohort_scope=(str(raw["cohort_scope"]) if raw.get("cohort_scope") else None),
        )

    def render(self) -> str:
        scope = self.cohort_scope or "-"
        att = f" att={self.attestation_id[:8]}…" if self.attestation_id else ""
        return f"{self.role:14s} {scope:11s} {self.key_id}{att}"


@dataclass
class AnnounceBundleCheck:
    """One announce round-trip, classified. `passed` is the assertion verdict."""

    #: ok | incomplete | not_reported | no_federation_id | unauthorized | unreachable | error
    status: str
    message: str
    http_status: Optional[int] = None
    expected: Optional[int] = None
    discoverable: Optional[bool] = None
    rows: List[AnnouncedRow] = field(default_factory=list)
    promoted_attestation_id: Optional[str] = None
    #: The verdict after collapsing to the widest placement per (role, key).
    effective_discoverable: Optional[bool] = None
    #: Rows the server counted that a wider row of the same (role, key) shadows.
    shadowed_rows: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "ok"

    @property
    def asserted(self) -> bool:
        """True when the server reported a bundle and the verdict is real."""
        return self.status in ("ok", "incomplete")

    def render(self) -> str:
        head = f"announce bundle: {self.status} -- {self.message}"
        if not self.rows:
            return head
        lines = [head, f"  rows ({len(self.rows)}/{self.expected if self.expected is not None else '?'}):"]
        lines += [f"    {r.render()}" for r in self.rows]
        return "\n".join(lines)

    def details(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "http_status": self.http_status,
            "bundle_expected": self.expected,
            "federation_discoverable": self.discoverable,
            "bundle": [r.__dict__ for r in self.rows],
            "promoted_owner_binding_attestation_id": self.promoted_attestation_id,
            "effective_discoverable": self.effective_discoverable,
            "shadowed_rows": self.shadowed_rows,
        }


async def check_announce_bundle(
    client: httpx.AsyncClient,
    node_url: str = DEFAULT_NODE_URL,
    headers: Optional[Mapping[str, str]] = None,
    *,
    expected_rows: int = AGENT_NODE_BUNDLE_ROWS,
    timeout: float = 30.0,
) -> AnnounceBundleCheck:
    """POST the (idempotent) announce and classify what came back.

    `headers` must carry the owner's bearer: the endpoint is owner-session
    gated (SYSTEM_ADMIN, no delegate actor). A 401/403 is reported as
    `unauthorized` -- the harness's session was not accepted by the NODE --
    which is a harness gap to name, not a delivery fault to chase.
    """
    url = f"{node_url.rstrip('/')}/v1/federation/announce"
    try:
        resp = await client.post(url, headers=dict(headers or {}), timeout=timeout)
    except httpx.HTTPError as exc:
        return AnnounceBundleCheck(
            status="unreachable",
            message=f"{url} not reachable ({type(exc).__name__}: {exc}); the node read-API on 4243 is not "
            "forwarded/served from here, so the bundle cannot be asserted",
        )
    if resp.status_code in (401, 403):
        return AnnounceBundleCheck(
            status="unauthorized",
            http_status=resp.status_code,
            message=f"the node refused the harness session ({resp.status_code}: {resp.text[:160]}); "
            "announce needs the OWNER's session -- the bundle was not asserted",
        )
    if resp.status_code == 404:
        return AnnounceBundleCheck(
            status="unreachable",
            http_status=404,
            message=f"{url} is 404 -- the node fold is not serving the federation surface",
        )
    if resp.status_code == 503 and "federation id" in resp.text.lower():
        # The node's own words: announcing is the OWNER stating their ownership
        # at a federation-wide audience, which needs the owner's signing key --
        # a federation ID. The wizard mints one (`POST /v1/self/identity`) before
        # it announces; a flow that skipped the mint cannot announce at all.
        return AnnounceBundleCheck(
            status="no_federation_id",
            http_status=503,
            message="the owner has no federation ID on this node, so it cannot announce: the mint step "
            "(POST /v1/self/identity) did not run before this check -- the node stays P2P-only",
        )
    if resp.status_code != 200:
        return AnnounceBundleCheck(
            status="error",
            http_status=resp.status_code,
            message=f"announce returned {resp.status_code}: {resp.text[:200]}",
        )
    try:
        body = resp.json()
    except ValueError:
        return AnnounceBundleCheck(status="error", http_status=200, message=f"announce returned non-JSON: {resp.text[:160]}")
    if not isinstance(body, Mapping) or "bundle_expected" not in body:
        return AnnounceBundleCheck(
            status="not_reported",
            http_status=200,
            message="announce succeeded but reported no bundle -- ciris-server < 0.5.197; discoverability not asserted",
            promoted_attestation_id=(str(body.get("promoted_owner_binding_attestation_id")) if isinstance(body, Mapping) and body.get("promoted_owner_binding_attestation_id") else None),
        )
    rows = [AnnouncedRow.from_json(r) for r in body.get("bundle", []) if isinstance(r, Mapping)]
    expected = int(body.get("bundle_expected", 0))
    discoverable = bool(body.get("federation_discoverable", False))
    promoted = body.get("promoted_owner_binding_attestation_id")
    check = AnnounceBundleCheck(
        status="ok",
        message="",
        http_status=200,
        expected=expected,
        discoverable=discoverable,
        rows=rows,
        promoted_attestation_id=str(promoted) if promoted else None,
    )
    # WHAT A PEER ACTUALLY WALKS. The server enumerates every live owner-authored
    # `delegates_to` onto an agent key as its own agent. On a single-key node
    # (node key == agent key) the owner->node binding IS the owner->agent
    # binding, and a widening leaves the pre-promotion `self` row live beside
    # the federation one -- so the raw report counts the same agent twice and
    # calls the node undiscoverable on a row no peer ever receives (CC 5.2 keeps
    # `self` rows home). Collapse per (role, key) to the widest placement and
    # judge THAT; the server's own verdict is kept beside it, never hidden.
    widest: Dict[Tuple[str, str], AnnouncedRow] = {}
    for r in rows:
        k = (r.role, r.key_id)
        cur = widest.get(k)
        if cur is None or _SCOPE_RANK.get(r.cohort_scope or "", -1) > _SCOPE_RANK.get(cur.cohort_scope or "", -1):
            widest[k] = r
    effective_rows = list(widest.values())
    shadowed = [r for r in rows if widest[(r.role, r.key_id)] is not r]
    effective_discoverable = all(
        r.cohort_scope in (None, "federation") for r in effective_rows
    ) and len(effective_rows) >= expected_rows
    check.effective_discoverable = effective_discoverable
    check.shadowed_rows = [r.render() for r in shadowed]

    shortfalls: List[str] = []
    if len(effective_rows) < expected_rows:
        missing = sorted({"owner_key", "node_key", "owner_binding", "agent_binding", "agent_key"} - {r.role for r in effective_rows})
        shortfalls.append(
            f"{len(effective_rows)} distinct rows, not {expected_rows}: missing {', '.join(missing) or 'a row the node did not enumerate'}"
        )
    narrow = [r for r in effective_rows if r.cohort_scope not in (None, "federation")]
    if narrow:
        shortfalls.append(
            "not federation-visible: " + ", ".join(f"{r.role}@{r.cohort_scope}" for r in narrow)
        )
    if shortfalls:
        check.status = "incomplete"
        check.message = "; ".join(shortfalls) + " -- this node is P2P-only: peers cannot place it in any community audience"
        return check

    note = ""
    if shadowed or expected != expected_rows or not discoverable:
        bindings = [r for r in shadowed if r.attestation_id]
        keys = [r for r in shadowed if not r.attestation_id]
        note = (
            f" [server reports bundle_expected={expected}, federation_discoverable={str(discoverable).lower()}: "
            f"{len(bindings)} superseded {'/'.join(sorted({r.cohort_scope or '-' for r in bindings})) or '-'}-scoped binding(s) "
            f"and {len(keys)} duplicate key row(s) counted as an extra agent -- a peer never receives a self row; "
            "CIRISServer#541 announce_bundle double-count]"
        )
    check.message = (
        f"{len(effective_rows)}/{expected_rows} distinct rows federation-visible"
        + (" (re-announce: binding already at federation scope)" if promoted is None else f" (owner binding promoted: {promoted})")
        + note
    )
    return check
