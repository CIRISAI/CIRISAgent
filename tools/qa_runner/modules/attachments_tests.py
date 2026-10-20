"""Attachments QA: does a file the user attaches reach the agent, and is a refusal visible?

Drives `POST /v1/agent/interact` with real files built by
`tools.qa_runner.attachment_fixtures`: a PDF, a DOCX and a text file each carry
a fresh sentinel in their text, plus a PNG. It checks two things for every file:

1. **The outcome the client sees** (`data.attachments`): accepted, or refused
   with the expected reason id. A file is never dropped silently.
2. **That the content reached the model.** Under the mock LLM the reply carries
   `[DOCUMENT_TOKENS:<sentinel>]` and `[MULTIMODAL_DETECTED:N]` markers
   (ciris_adapters/mock_llm). Under a live model the reply must quote the
   sentinel.

The same fixtures are the acceptance bar for the migration to substrate-native
agent chat (CIRISAgent#1300): post them as room attachments and the
content-reached-the-model checks carry over unchanged.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from rich.console import Console

from .. import attachment_fixtures as fx
from .filter_test_helper import FilterTestHelper
from .interact_outcome import interact_timed_out, is_still_processing_text

logger = logging.getLogger(__name__)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ASK = "Reply with the archive code word written in the attached file, exactly as it is written."


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class AttachmentsTests:
    """Attachment delivery and refusal visibility on the inline interact path."""

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
        self.policy: Dict[str, Any] = {}

    async def run(self) -> List[Dict[str, Any]]:
        self.console.print("\n[cyan] Testing attachments (images + documents)[/cyan]")
        if self.token:
            self.sse_helper = FilterTestHelper(self.base_url, self.token, verbose=False)
            try:
                self.sse_helper.start_monitoring()
            except Exception as e:  # noqa: BLE001 - SSE only shortens waits
                logger.warning(f"Could not start SSE monitoring: {e}")
                self.sse_helper = None

        tests = [
            ("Attachment policy is served", self.test_policy),
            ("PDF text reaches the agent", self.test_pdf),
            ("DOCX text reaches the agent", self.test_docx),
            ("Plain text reaches the agent", self.test_text),
            ("Unlabelled DOCX is typed by extension", self.test_octet_stream_docx),
            ("Image and document together", self.test_image_and_document),
            ("Refusals are reported, never silent", self.test_refusals),
            ("Oversized document is refused as too_large", self.test_too_large),
        ]
        try:
            for name, test_func in tests:
                try:
                    await test_func()
                    self.results.append({"test": name, "status": "✅ PASS", "error": None})
                    self.console.print(f" [OK] {name}")
                except Exception as e:  # noqa: BLE001 - one failing test must not stop the rest
                    self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                    self.console.print(f" [FAIL] {name}: {str(e)[:200]}")
                    if self.console.is_terminal:
                        self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")
        finally:
            if self.sse_helper:
                self.sse_helper.stop_monitoring()
        self._print_summary()
        return self.results

    # ------------------------------------------------------------------ helpers

    async def _settle(self) -> None:
        """Let the previous interaction's task finish, so this one gets a fresh task."""
        if self.sse_helper:
            self.sse_helper.wait_for_task_complete(timeout=10.0)
            await asyncio.sleep(1.0)
            self.sse_helper.task_complete_seen = False
            self.sse_helper.completed_tasks.clear()

    async def _interact(self, message: str, images: Optional[List[Dict[str, str]]] = None,
                        documents: Optional[List[Dict[str, str]]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """(reply text, attachment outcomes). Falls back to history when interact times out."""
        await self._settle()
        submitted = datetime.now(timezone.utc)
        body: Dict[str, Any] = {"message": message}
        if images:
            body["images"] = images
        if documents:
            body["documents"] = documents
        async with httpx.AsyncClient(timeout=120.0) as http:
            response = await http.post(f"{self.base_url}/v1/agent/interact",
                                       headers={"Authorization": f"Bearer {self.token}"}, json=body)
        assert response.status_code == 200, f"interact answered {response.status_code}: {response.text[:300]}"
        data = response.json()["data"]
        outcomes = data.get("attachments")
        assert isinstance(outcomes, list), f"interact response has no 'attachments' list: {sorted(data)}"
        text = data.get("response", "")

        if interact_timed_out(data) and self.sse_helper and self.sse_helper.wait_for_task_complete(timeout=90.0):
            history = await self.client.agent.get_history(limit=10)
            for msg in history.messages:
                stamp = getattr(msg, "timestamp", None) or getattr(msg, "created_at", None)
                if isinstance(stamp, str):
                    stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if msg.is_agent and stamp and stamp > submitted and not is_still_processing_text(msg.content):
                    text = msg.content
                    break
        if self.sse_helper and not self.sse_helper.task_complete_seen:
            self.sse_helper.wait_for_task_complete(timeout=30.0)
        return text, outcomes

    @staticmethod
    def _is_mock(reply: str) -> bool:
        return "[MOCK LLM]" in reply

    def _assert_reached(self, reply: str, sentinel: str) -> None:
        if self._is_mock(reply):
            assert "[DOCUMENT_TOKENS:" in reply and sentinel in reply, (
                f"the document's text did not reach the model (no {sentinel} in the mock's DOCUMENT_TOKENS): "
                f"{reply[:300]}"
            )
        else:
            assert sentinel in reply, f"live reply does not quote the code word {sentinel}: {reply[:300]}"

    @staticmethod
    def _outcome(outcomes: List[Dict[str, Any]], kind: str, index: int) -> Dict[str, Any]:
        for o in outcomes:
            if o.get("kind") == kind and o.get("index") == index:
                return o
        raise AssertionError(f"no outcome for {kind} #{index}: {outcomes}")

    async def _one_document(self, data: bytes, media_type: str, filename: str, sentinel: str) -> None:
        reply, outcomes = await self._interact(ASK, documents=[{"data": _b64(data), "media_type": media_type,
                                                                 "filename": filename}])
        outcome = self._outcome(outcomes, "document", 0)
        assert outcome["status"] == "accepted", f"{filename} was refused: {outcome}"
        assert outcome.get("extracted_chars"), f"{filename} accepted with no text: {outcome}"
        self._assert_reached(reply, sentinel)

    # -------------------------------------------------------------------- tests

    async def test_policy(self) -> None:
        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.get(f"{self.base_url}/v1/agent/attachments/policy",
                                      headers={"Authorization": f"Bearer {self.token}"})
        assert response.status_code == 200, f"policy answered {response.status_code}: {response.text[:200]}"
        self.policy = response.json()["data"]
        for key in ("image_types", "image_max_bytes", "max_images", "document_types", "document_max_bytes",
                    "max_documents", "max_extracted_chars"):
            assert key in self.policy, f"policy is missing {key}: {self.policy}"
        # A build without its PDF/DOCX parser libraries is the "agent can't see my file" bug.
        missing = [t for t in (PDF, DOCX) if t not in self.policy["document_types"]]
        assert not missing, f"this build cannot read {missing}: document parser libraries are missing"

    async def test_pdf(self) -> None:
        sentinel = fx.new_sentinel()
        await self._one_document(fx.pdf(fx.sentence(sentinel)), PDF, "notes.pdf", sentinel)

    async def test_docx(self) -> None:
        sentinel = fx.new_sentinel()
        await self._one_document(fx.docx(fx.sentence(sentinel)), DOCX, "notes.docx", sentinel)

    async def test_text(self) -> None:
        sentinel = fx.new_sentinel()
        await self._one_document(fx.text(fx.sentence(sentinel)), "text/plain", "notes.txt", sentinel)

    async def test_octet_stream_docx(self) -> None:
        """The desktop/iOS pickers label unknown files application/octet-stream (CIRISClient#217)."""
        sentinel = fx.new_sentinel()
        await self._one_document(fx.docx(fx.sentence(sentinel)), "application/octet-stream", "notes.docx", sentinel)

    async def test_image_and_document(self) -> None:
        sentinel = fx.new_sentinel()
        reply, outcomes = await self._interact(
            ASK,
            images=[{"data": _b64(fx.png()), "media_type": "image/png", "filename": "swatch.png"}],
            documents=[{"data": _b64(fx.pdf(fx.sentence(sentinel))), "media_type": PDF, "filename": "notes.pdf"}],
        )
        assert self._outcome(outcomes, "image", 0)["status"] == "accepted", outcomes
        assert self._outcome(outcomes, "document", 0)["status"] == "accepted", outcomes
        if self._is_mock(reply):
            assert "[MULTIMODAL_DETECTED:1]" in reply, f"the image did not reach the model: {reply[:300]}"
        self._assert_reached(reply, sentinel)

    async def test_refusals(self) -> None:
        reply, outcomes = await self._interact(
            "Here are some files.",
            images=[
                {"data": _b64(fx.png()), "media_type": "image/jpeg", "filename": "mislabelled.jpg"},
                {"data": _b64(b"\x00\x00\x00\x18ftypheic"), "media_type": "image/heic", "filename": "photo.heic"},
            ],
            documents=[{"data": _b64(b"PK\x03\x04sheet"), "media_type": "application/vnd.ms-excel",
                        "filename": "budget.xlsx"}],
        )
        expected = {("image", 0): "type_mismatch", ("image", 1): "unsupported_type",
                    ("document", 0): "unsupported_type"}
        for (kind, index), reason in expected.items():
            outcome = self._outcome(outcomes, kind, index)
            assert outcome["status"] == "refused" and outcome["reason"] == reason, (
                f"{kind} #{index}: expected refused/{reason}, got {outcome}"
            )
        if self._is_mock(reply):
            assert "[ATTACHMENT_REFUSED:3]" in reply, f"the agent was not told about the refusals: {reply[:300]}"

    async def test_too_large(self) -> None:
        limit = int(self.policy.get("document_max_bytes") or 10 * 1024 * 1024)
        _, outcomes = await self._interact(
            "Here is a large file.",
            documents=[{"data": _b64(b"a" * (limit + 1)), "media_type": "text/plain", "filename": "big.txt"}],
        )
        outcome = self._outcome(outcomes, "document", 0)
        assert outcome["status"] == "refused" and outcome["reason"] == "too_large", outcome
        assert outcome.get("limit_bytes") == limit, outcome

    def _print_summary(self) -> None:
        passed = sum(1 for r in self.results if "PASS" in r["status"])
        self.console.print(f"\n[bold]Attachments Tests: {passed}/{len(self.results)} passed[/bold]")
        for r in self.results:
            if "FAIL" in r["status"]:
                self.console.print(f"  - {r['test']}: {r['error']}")
