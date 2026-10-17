"""Claim the local node the way the first-run wizard does: one implementation.

EVERY NODE IS ALWAYS CLAIMED. An agent cannot run without a named human for its
node, and an unowned node ships no trace to any canonical. The wizard
(KMP SetupViewModel) does it in this order, before it completes setup:

  1. mint the owner's federation ID     POST <brain>/v1/self/identity {"label"}
  2. claim the node with its PIN         POST <node>/v1/setup/claim-remote
  3. complete setup                      POST <brain>/v1/setup/complete

The PIN: the node mints a one-time claim PIN at boot while it is UNOWNED and
writes it to `<node home>/claim_pin` (the node's home is the backend's
CIRIS_HOME). Setup must run after the claim: the claim is what creates the
user. `/v1/setup/complete` mints no user; it reads the node-claimed owner
(`_resolve_node_owner`) and answers 409 node_unclaimed when there is none.

Used by the QA runner's own setup (tools/qa_runner/server.py, every QA boot,
live and mock) and by the setup_e2e module. Fail closed: no PIN, or a claim
that does not answer 200, is a failure, never an unowned node.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from tools.qa_runner.announce_bundle import DEFAULT_NODE_URL

CLAIM_PIN_FILE = "claim_pin"

#: The QA runner's setup user. A real first-run user, like any wizard user; the
#: traces say they are QA through `run_kind`, never through the name.
QA_HARNESS_USER = "qa-harness-user"


@dataclass
class ClaimOutcome:
    """What one wizard-order claim did. `ok` only when the node answered 200 to the claim."""

    ok: bool
    step: str
    detail: str
    pin_file: Optional[Path] = None
    owner: Optional[str] = None
    federation_key_id: Optional[str] = None
    node_code_prefix: str = ""
    response_keys: List[str] = field(default_factory=list)


def _parse_pin(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            return ""
        return str(obj.get("pin") or obj.get("claim_pin") or "")
    return raw


def find_claim_pin(
    homes: Iterable[Optional[str]], since: Optional[float] = None
) -> Tuple[Optional[str], Optional[Path]]:
    """The first readable PIN in `<home>/claim_pin`, written at or after `since` when given.

    `since` keeps a PIN a previous run left behind (the node removes the file
    when it is claimed; a crashed run does not) from being read as this boot's.
    """
    for home in homes:
        if not home:
            continue
        candidate = Path(home) / CLAIM_PIN_FILE
        try:
            if since is not None and candidate.stat().st_mtime < since:
                continue
            pin = _parse_pin(candidate.read_text(encoding="utf-8"))
        except OSError:
            continue
        if pin:
            return pin, candidate
    return None, None


async def wait_for_claim_pin(
    homes: Iterable[Optional[str]], timeout_s: float, since: Optional[float] = None, poll_s: float = 0.5
) -> Tuple[Optional[str], Optional[Path]]:
    """Wait for the node's compose to reach its claim phase and write the PIN."""
    homes = list(homes)
    deadline = time.monotonic() + timeout_s
    while True:
        pin, path = find_claim_pin(homes, since)
        if pin is not None or time.monotonic() >= deadline:
            return pin, path
        await asyncio.sleep(poll_s)


#: How long the node may take to start answering after its PIN appears. The PIN
#: is written during compose; the read-API on :4243 binds after it, and the
#: brain's proxy answers 502/503 in between (Staged QA on #1276).
NODE_READY_TIMEOUT_S = 60.0

#: A node still booting, never a refusal. A 4xx is the node's answer: never retried.
_BOOT_WINDOW_STATUSES = frozenset({502, 503})
_BOOT_WINDOW_ERRORS = (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException)


async def request_through_boot_window(
    client: httpx.AsyncClient, method: str, url: str, ready_timeout_s: float = NODE_READY_TIMEOUT_S, **kwargs: Any
) -> httpx.Response:
    """One request, retried with backoff while the node is still coming up.

    Retries 502/503 and connection-level failures until `ready_timeout_s`, then
    returns the last response (or raises the last error): the caller fails
    closed on it. Any other status, 4xx included, returns at once.
    """
    deadline = time.monotonic() + ready_timeout_s
    delay = 0.5
    while True:
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code not in _BOOT_WINDOW_STATUSES or time.monotonic() >= deadline:
                return response
        except _BOOT_WINDOW_ERRORS:
            if time.monotonic() >= deadline:
                raise
        await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        delay = min(delay * 2, 4.0)


async def mint_federation_id(
    client: httpx.AsyncClient, base_url: str, label: str, ready_timeout_s: float = NODE_READY_TIMEOUT_S
) -> Tuple[bool, Dict[str, Any], str]:
    """Wizard step 1: the owner's federation ID, through the brain (which proxies it to the node)."""
    response = await request_through_boot_window(
        client, "POST", f"{base_url}/v1/self/identity", ready_timeout_s, json={"label": label}, timeout=60.0
    )
    if response.status_code != 200:
        return False, {}, f"Status code: {response.status_code}: {response.text[:300]}"
    data = response.json()
    return True, data if isinstance(data, dict) else {}, ""


async def claim_node(
    client: httpx.AsyncClient,
    base_url: str,
    pin: str,
    owner_username: str,
    owner_password: str,
    node_url: str = DEFAULT_NODE_URL,
    ready_timeout_s: float = NODE_READY_TIMEOUT_S,
) -> ClaimOutcome:
    """Wizard step 2: claim-remote with the node's own NodeCode and its PIN."""
    # The node's own NodeCode (served on the federation surface, proxied by the brain).
    r = await request_through_boot_window(
        client, "GET", f"{base_url}/v1/federation/node-code", ready_timeout_s, timeout=30.0
    )
    if r.status_code != 200:
        r = await request_through_boot_window(
            client, "GET", f"{node_url}/v1/federation/node-code", ready_timeout_s, timeout=30.0
        )
    r.raise_for_status()
    body = r.json()
    payload = body.get("data", body) if isinstance(body, dict) else {}
    node_code = str(payload.get("node_code") or payload.get("code") or "")
    if not node_code:
        return ClaimOutcome(False, "claim", f"no node_code in {str(body)[:200]}")

    claim = {
        "node_code": node_code,
        "claim_pin": pin,
        "cohort_scope": "self",
        # A self-claim's NodeCode may carry no transport hint; the target IS this node.
        "target_url": node_url,
        "owner_username": owner_username,
        "owner_password": owner_password,
    }
    # claim-remote is a NODE route; the brain's own /v1/setup router shadows
    # the prefix, so it is posted to the node directly.
    response = await request_through_boot_window(
        client, "POST", f"{node_url}/v1/setup/claim-remote", ready_timeout_s, json=claim, timeout=120.0
    )
    if response.status_code != 200:
        return ClaimOutcome(
            False,
            "claim",
            f"Status code: {response.status_code}: {response.text[:400]}",
            node_code_prefix=node_code[:24],
        )
    data = response.json()
    data = data if isinstance(data, dict) else {}
    return ClaimOutcome(
        True,
        "claim",
        "node claimed",
        owner=str(data.get("owner") or data.get("responsible_user_key_id") or "") or None,
        node_code_prefix=node_code[:24],
        response_keys=sorted(data.keys()),
    )


async def claim_like_the_wizard(
    client: httpx.AsyncClient,
    base_url: str,
    homes: Iterable[Optional[str]],
    owner_username: str,
    owner_password: str,
    *,
    pin_timeout_s: float = 120.0,
    since: Optional[float] = None,
    node_url: str = DEFAULT_NODE_URL,
    ready_timeout_s: float = NODE_READY_TIMEOUT_S,
) -> ClaimOutcome:
    """Wizard steps 1 and 2, in order, fail closed. Call BEFORE /v1/setup/complete."""
    homes = list(homes)
    pin, pin_file = await wait_for_claim_pin(homes, pin_timeout_s, since)
    if pin is None:
        looked = ", ".join(str(Path(h) / CLAIM_PIN_FILE) for h in homes if h)
        return ClaimOutcome(
            False,
            "pin",
            "No claim PIN readable -- the node minted none (already ROOT-owned: setup ran against a database "
            f"that already has an owner, or setup completed before the claim) or wrote it elsewhere; looked in: {looked}",
        )
    try:
        minted, data, error = await mint_federation_id(client, base_url, owner_username, ready_timeout_s)
        if not minted:
            return ClaimOutcome(False, "mint", error, pin_file=pin_file)
        outcome = await claim_node(client, base_url, pin, owner_username, owner_password, node_url, ready_timeout_s)
    except Exception as exc:  # noqa: BLE001 - a failed claim is a failure, never an unowned node
        return ClaimOutcome(False, "claim", f"{type(exc).__name__}: {exc}", pin_file=pin_file)
    outcome.pin_file = pin_file
    outcome.federation_key_id = str(data.get("key_id") or "") or None
    return outcome


__all__ = [
    "CLAIM_PIN_FILE",
    "ClaimOutcome",
    "QA_HARNESS_USER",
    "claim_like_the_wizard",
    "claim_node",
    "find_claim_pin",
    "mint_federation_id",
    "request_through_boot_window",
    "wait_for_claim_pin",
]
