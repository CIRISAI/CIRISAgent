"""WA-approved identity change, end to end: the agent may change its identity only on a Wise Authority's approval.

The path under test (CIRISAgent#1303):

1. An IDENTITY-scope MEMORIZE without WA authorization is refused
   (MemorizeHandler: "WA authorization required"), and nothing is stored.
2. The request defers to a Wise Authority, and the deferral is pending in
   ``GET /v1/wa/deferrals``.
3. The WA approves it through the real route,
   ``POST /v1/wa/deferrals/{id}/resolve``, which signs the resolution.
   ``resolve_deferral`` verifies it and creates a guidance task carrying
   ``TaskContext.wa_authorization``.
4. The guidance task's thoughts dispatch with ``wa_authorized=True``, so the
   approved IDENTITY-scope MEMORIZE goes through and the node is in the graph.

Before #1303, step 4 never happened: nothing in production set
``wa_authorized``, so a WA approval of an identity change could never take
effect. No QA module resolved a deferral through the API, which is how that
went unseen.

Mock LLM only. ``$memorize <id> CONCEPT IDENTITY`` is the identity change, and
the WA's guidance carries the same command, which the mock follows the way a
live model follows guidance (ciris_adapters/mock_llm/responses.py, STEP 1b).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import traceback
from typing import Any, Dict, List, Optional

import httpx
from rich.console import Console

from .filter_test_helper import FilterTestHelper

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
APPROVAL_TIMEOUT_SECONDS = 120.0


class WAIdentityApprovalTests:
    """A Wise Authority's approval authorizes the identity change it approved, and nothing else does."""

    def __init__(self, client: Any, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []
        self.base_url = getattr(client, "base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self.base_url = client._transport.base_url
        self.token = getattr(client, "api_key", None)
        if hasattr(client, "_transport") and hasattr(client._transport, "api_key"):
            self.token = client._transport.api_key
        self.sse_helper: Optional[FilterTestHelper] = None
        suffix = secrets.token_hex(4)
        self.refused_node = f"qa_wa_identity_refused_{suffix}"
        self.approved_node = f"qa_wa_identity_approved_{suffix}"
        self.deferral_id: Optional[str] = None
        self._last_lookup: List[Dict[str, Any]] = []

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[cyan] Testing WA-approved identity change (defer → approve → identity MEMORIZE)[/cyan]")
        if self.token:
            self.sse_helper = FilterTestHelper(self.base_url, self.token, verbose=False)
            try:
                self.sse_helper.start_monitoring()
            except Exception as e:  # noqa: BLE001 - SSE only shortens waits
                logger.warning(f"Could not start SSE monitoring: {e}")
                self.sse_helper = None

        tests = [
            ("Identity MEMORIZE without WA approval is refused", self.test_unapproved_identity_write_is_refused),
            ("The identity change defers to a Wise Authority", self.test_identity_change_defers),
            ("The WA approves through the signed resolve route", self.test_wa_approves),
            ("The approved identity change is applied", self.test_approved_identity_write_lands),
            ("Approval authorized only its own change", self.test_approval_did_not_leak),
        ]
        try:
            for name, test_func in tests:
                try:
                    await test_func()
                    self.results.append({"test": name, "status": "✅ PASS", "error": None})
                    self.console.print(f" [OK] {name}")
                except Exception as e:  # noqa: BLE001 - one failure must not hide the rest
                    self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                    self.console.print(f" [FAIL] {name}: {str(e)[:240]}")
                    if self.console.is_terminal:
                        self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")
        finally:
            if self.sse_helper:
                self.sse_helper.stop_monitoring()
        self._print_summary()
        return self.results

    # ------------------------------------------------------------------ helpers

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _settle(self) -> None:
        if self.sse_helper:
            self.sse_helper.wait_for_task_complete(timeout=15.0)
            await asyncio.sleep(1.0)
            self.sse_helper.task_complete_seen = False
            self.sse_helper.completed_tasks.clear()

    async def _interact(self, message: str) -> Dict[str, Any]:
        await self._settle()
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.post(f"{self.base_url}/v1/agent/interact", headers=self._headers(), json={"message": message})
        assert r.status_code == 200, f"interact answered {r.status_code}: {r.text[:300]}"
        if self.sse_helper and not self.sse_helper.task_complete_seen:
            self.sse_helper.wait_for_task_complete(timeout=45.0)
        data: Dict[str, Any] = r.json()["data"]
        return data

    async def _query(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.post(f"{self.base_url}/v1/memory/query", headers=self._headers(), json=body)
        assert r.status_code == 200, f"POST /v1/memory/query {body} answered {r.status_code}: {r.text[:200]}"
        nodes: List[Dict[str, Any]] = r.json()["data"] or []
        return nodes

    @staticmethod
    def _content(node: Dict[str, Any]) -> Optional[str]:
        attributes = node.get("attributes") or {}
        content = attributes.get("content") if isinstance(attributes, dict) else None
        return str(content) if content is not None else None

    async def _stored(self, marker: str, scope: str) -> List[Dict[str, Any]]:
        """Nodes at ``scope`` whose id is ``marker`` or whose content contains it.

        A flat MEMORIZE (what live models emit, and what the mock now emits too)
        carries no node id: the engine assigns a uuid and the requested name
        travels as the content. So the node is found by content, by both a text
        search and a scope listing, and deduplicated by id.
        """
        seen: Dict[str, Dict[str, Any]] = {}
        for body in ({"query": marker, "limit": 200}, {"scope": scope, "limit": 1000}):
            for node in await self._query(body):
                if node.get("id") == marker or marker in (self._content(node) or ""):
                    seen[str(node.get("id"))] = node
        self._last_lookup = list(seen.values())
        return [n for n in seen.values() if str(n.get("scope", "")).lower() == scope]

    async def _stored_anywhere(self, marker: str) -> List[Dict[str, Any]]:
        return await self._stored(marker, "identity") + await self._stored(marker, "local")

    async def _diagnose(self, marker: str) -> str:
        """What the graph holds, for a failure message that says why."""
        identity = await self._query({"scope": "identity", "limit": 1000})
        sample = [(n.get("id"), n.get("type"), self._content(n)) for n in identity[-5:]]
        return (
            f"matches for {marker!r} at any scope: {[(n.get('id'), n.get('scope')) for n in self._last_lookup]}; "
            f"{len(identity)} identity-scope nodes, newest: {sample}"
        )

    async def _pending_deferrals(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as http:
            r = await http.get(f"{self.base_url}/v1/wa/deferrals", headers=self._headers())
        assert r.status_code == 200, f"GET /v1/wa/deferrals answered {r.status_code}: {r.text[:200]}"
        deferrals: List[Dict[str, Any]] = r.json()["data"]["deferrals"]
        return deferrals

    # -------------------------------------------------------------------- tests

    async def test_unapproved_identity_write_is_refused(self) -> None:
        data = await self._interact(f"$memorize {self.refused_node} CONCEPT IDENTITY")
        await asyncio.sleep(2.0)
        stored = await self._stored_anywhere(self.refused_node)
        assert not stored, (
            f"the unapproved identity MEMORIZE was stored: {stored} (reply: {data.get('response', '')[:200]})"
        )
        # This absence is meaningful only because the approved write below DOES
        # land through the same path (an IDENTITY-scope MEMORIZE from the mock).
        # Before #1303's mock fix every mock $memorize went in at LOCAL, so this
        # check passed without the gate ever running.

    async def test_identity_change_defers(self) -> None:
        before = {d["deferral_id"] for d in await self._pending_deferrals()}
        await self._interact(f"$defer Identity change requires Wise Authority approval: {self.approved_node}")
        deadline = asyncio.get_event_loop().time() + 60.0
        new: List[Dict[str, Any]] = []
        while asyncio.get_event_loop().time() < deadline:
            new = [d for d in await self._pending_deferrals() if d["deferral_id"] not in before]
            if new:
                break
            await asyncio.sleep(POLL_SECONDS)
        assert new, "the $defer did not produce a pending deferral in GET /v1/wa/deferrals"
        self.deferral_id = new[0]["deferral_id"]

    async def test_wa_approves(self) -> None:
        assert self.deferral_id, "no deferral to approve (previous test failed)"
        async with httpx.AsyncClient(timeout=60.0) as http:
            r = await http.post(
                f"{self.base_url}/v1/wa/deferrals/{self.deferral_id}/resolve",
                headers=self._headers(),
                json={"resolution": "approve", "guidance": f"$memorize {self.approved_node} CONCEPT IDENTITY"},
            )
        assert r.status_code == 200, f"resolve answered {r.status_code}: {r.text[:300]}"
        assert self.deferral_id not in {d["deferral_id"] for d in await self._pending_deferrals()}, (
            "the deferral is still pending after approval"
        )

    async def test_approved_identity_write_lands(self) -> None:
        assert self.deferral_id, "no approved deferral (previous test failed)"
        deadline = asyncio.get_event_loop().time() + APPROVAL_TIMEOUT_SECONDS
        node: Optional[Dict[str, Any]] = None
        while asyncio.get_event_loop().time() < deadline:
            found = await self._stored(self.approved_node, "identity")
            if found:
                node = found[0]
                break
            await asyncio.sleep(POLL_SECONDS)
        assert node is not None, (
            f"the WA-approved identity change never landed: {self.approved_node} is not in the graph at "
            f"IDENTITY scope {APPROVAL_TIMEOUT_SECONDS:.0f}s after approval. {await self._diagnose(self.approved_node)}"
        )
        assert str(node.get("scope", "")).lower() == "identity", f"stored at the wrong scope: {node}"

    async def test_approval_did_not_leak(self) -> None:
        """The approval authorized its own guidance task only; an ordinary request is still refused."""
        await self._interact(f"$memorize {self.refused_node} CONCEPT IDENTITY")
        await asyncio.sleep(2.0)
        assert not await self._stored_anywhere(self.refused_node), (
            "after a WA approval, an unrelated IDENTITY-scope MEMORIZE went through: the authorization leaked"
        )

    def _print_summary(self) -> None:
        passed = sum(1 for r in self.results if "PASS" in r["status"])
        self.console.print(f"\n[bold]WA Identity Approval Tests: {passed}/{len(self.results)} passed[/bold]")
        for r in self.results:
            if "FAIL" in r["status"]:
                self.console.print(f"  - {r['test']}: {r['error']}")
