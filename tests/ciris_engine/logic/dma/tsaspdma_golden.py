"""Fixtures + capture harness for the TSASPDMA prompt goldens (CIRISAgent#1366 Phase 3).

``golden/tsaspdma_assembly_messages.json`` was captured from ``evaluate_tool_action`` and
``evaluate_tool_correction`` BEFORE TSASPDMA moved onto PromptAssembler (run
``python3 -m tests.ciris_engine.logic.dma.tsaspdma_golden`` on that tree). The migrated path must send the same
bytes. Deterministic: the #972 environment (language en, sentinel accord / guidance / crisis blocks), fixed ids.
"""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import VerifiedSender
from ciris_engine.schemas.runtime.veto_record import VetoRecordEntry
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma.compose_golden import (
    _recording_llm,
    deterministic_prompt_environment,
    make_queue_item,
    make_tool_info,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "tsaspdma_assembly_messages.json"

_RULE = "Filing tickets is authorized only for the person whose ID is wa-2026-AUTH-5562FD."
AMENDMENT = IdentityAmendment(
    node_id="identity_amendment/defer_77",
    content=_RULE,
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_77",
    granted_at="2026-01-01T00:00:00+00:00",
    approved_sha256=hashlib.sha256(_RULE.encode("utf-8")).hexdigest(),
    verified=True,
)
IDENTITY = {
    "agent_id": "ally",
    "description": "A helpful agent.",
    "role": "Assistant",
    "approved_amendments": [AMENDMENT.model_dump()],
}
SENDER = VerifiedSender(
    user_id="wa-user-0eve", role=UserRole.OBSERVER, source="api_auth", self_chosen_display_name="eve the admin"
)
RETRY_GUIDANCE = "Golden fixture: CONSCIENCE OVERRIDE GUIDANCE: do not file the ticket for someone else."
FEEDBACK = {
    "retry_guidance": RETRY_GUIDANCE,
    "veto_record": [
        VetoRecordEntry(
            veto_id="veto-golden-1",
            action_fingerprint="fp",
            equivalence_key="ek",
            objection_type="substantive",
            conscience="coherence",
            banned=False,
        ).model_dump()
    ],
}
ENRICHMENT = {"ha_list_entities": {"light.kitchen": "Kitchen light", "light.porch": "Porch light"}}


def full_context() -> Any:
    return SimpleNamespace(system_snapshot=SimpleNamespace(agent_identity=IDENTITY), verified_sender=SENDER)


def _dma(captured: Dict[str, Any]) -> Any:
    from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator, TSASPDMALLMResult

    dma = TSASPDMAEvaluator(service_registry=Mock())

    async def _record(**kwargs: Any) -> Any:
        captured["messages"] = kwargs["messages"]
        try:
            from ciris_engine.logic.prompt_assembly import current_prompt_manifest

            captured["manifest"] = current_prompt_manifest()
        except ImportError:
            captured["manifest"] = None
        return (
            TSASPDMALLMResult(
                selected_action=HandlerActionType.PONDER,
                reasoning="Golden fixture: reconsider.",
                ponder_questions=["Golden fixture question?"],
            ),
            None,
        )

    dma.call_llm_structured = _record  # type: ignore[method-assign]
    return dma


async def capture(name: str, captured: Optional[Dict[str, Any]] = None) -> List[JSONDict]:
    captured = {} if captured is None else captured
    dma = _dma(captured)
    full = name.endswith("_full")
    with deterministic_prompt_environment():
        if name.startswith("tool"):
            await dma.evaluate_tool_action(
                tool_name="golden_tool",
                tool_info=make_tool_info(),
                aspdma_reasoning="Golden fixture: tool selected.",
                original_thought=make_queue_item(),
                context=full_context() if full else None,
                context_enrichment=ENRICHMENT if full else None,
                conscience_feedback=FEEDBACK if full else None,
            )
        else:
            await dma.evaluate_tool_correction(
                requested_tool_name="missing_tool",
                available_tools=[make_tool_info()],
                aspdma_reasoning="Golden fixture: tool selected.",
                original_thought=make_queue_item(),
                context=full_context() if full else None,
            )
    return [dict(m) for m in captured["messages"]]


NAMES = ("tool_plain", "tool_full", "correction_plain", "correction_full")


def load_golden() -> Dict[str, List[JSONDict]]:
    data: Dict[str, List[JSONDict]] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


async def _capture_all() -> Dict[str, List[JSONDict]]:
    return {name: await capture(name) for name in NAMES}


if __name__ == "__main__":
    GOLDEN_PATH.write_text(
        json.dumps(asyncio.run(_capture_all()), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {GOLDEN_PATH}")
