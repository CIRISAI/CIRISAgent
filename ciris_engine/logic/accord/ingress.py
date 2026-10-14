"""Accord-row ingress: hand a v2 accord row to the node, unchanged (CC 4.2.1.1, CIRISAgent#1231).

A holder's signed row can arrive anywhere a message can — a Discord channel, the
API. The agent recognises the CEG signed-object envelope of kind
``accord_invocation`` (the v2 ``ciris.accord_invoke.v2`` / ``ciris.accord_lifecycle.v1``
rows CIRISVerify 20.x signs, #1227) and forwards the exact bytes it received to
the folded node's ``POST /v1/accord/message``. The node verifies the hybrid
signatures against its pinned roster, replicates, and latches, confirms or
releases. The agent does no crypto and never writes the latch.

Recognition is structural only: the envelope's ``schema`` and ``kind``. Whether
the row is authentic is the node's question, and an inauthentic row is the
node's 401, reported back, not something the agent second-guesses.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import httpx

from ciris_engine.logic.utils.halt_latch import NODE_FOLD_PORT
from ciris_engine.schemas.runtime.accord_halt import ACCORD_INVOCATION_KIND, CEG_SIGNED_OBJECT_SCHEMA, AccordRowForward

logger = logging.getLogger(__name__)

ACCORD_MESSAGE_URL = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/accord/message"

#: A row is a few KiB (roster + invocation + hybrid signatures). Anything far
#: larger is not a row, and is not parsed.
MAX_ACCORD_ROW_BYTES = 256 * 1024

#: The node verifies hybrid signatures and may replicate first: allow it time.
ACCORD_FORWARD_TIMEOUT_SECONDS = 10.0

_FENCE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def extract_accord_row(content: str) -> Optional[str]:
    """The row's exact text when `content` is an accord-row envelope, else None.

    Accepts the bare JSON object, or the object inside one Markdown code fence
    (how chat clients paste it). Returns the object's text as received — the
    bytes the node will see — never a re-serialisation.
    """
    if not content or len(content) > MAX_ACCORD_ROW_BYTES:
        return None
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("schema") != CEG_SIGNED_OBJECT_SCHEMA or obj.get("kind") != ACCORD_INVOCATION_KIND:
        return None
    if not isinstance(obj.get("body"), dict):
        return None
    return text


async def forward_accord_row(row: str) -> AccordRowForward:
    """POST the row, byte for byte, to the node and report its verdict."""
    try:
        async with httpx.AsyncClient(timeout=ACCORD_FORWARD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                ACCORD_MESSAGE_URL, content=row.encode("utf-8"), headers={"content-type": "application/json"}
            )
    except Exception as e:  # noqa: BLE001 - reported, never raised into message handling
        logger.error(f"Accord row not delivered to the node: {type(e).__name__}: {e}")
        return AccordRowForward(delivered=False, error=f"{type(e).__name__}: {e}")

    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = None
    verdict = body if isinstance(body, dict) else {}

    def _opt_bool(key: str) -> Optional[bool]:
        value = verdict.get(key)
        return value if isinstance(value, bool) else None

    def _opt_str(key: str) -> Optional[str]:
        value = verdict.get(key)
        return None if value is None else str(value)

    result = AccordRowForward(
        delivered=True,
        status_code=response.status_code,
        accepted=_opt_bool("accepted"),
        invocation_kind=_opt_str("invocation_kind"),
        invocation_id=_opt_str("invocation_id"),
        halted=_opt_bool("halted"),
        confirmed=_opt_bool("confirmed"),
        released=_opt_bool("released"),
        refusal=_opt_str("refusal"),
        error=None if response.status_code == 200 else (_opt_str("error") or _opt_str("detail") or response.text[:500]),
    )
    logger.warning(
        f"Accord row forwarded to the node: HTTP {result.status_code}, kind={result.invocation_kind}, "
        f"id={result.invocation_id}, halted={result.halted}, released={result.released}, refusal={result.refusal}"
    )
    return result


__all__ = ["ACCORD_MESSAGE_URL", "MAX_ACCORD_ROW_BYTES", "extract_accord_row", "forward_accord_row"]
