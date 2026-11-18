"""Fixtures + capture harness for the memory second-pass prompt goldens (CIRISAgent#1366 Phase 3).

``golden/{msaspdma,rsaspdma,fsaspdma}_assembly_messages.json`` were captured from ``evaluate_memorize_action``,
``evaluate_recall_action`` and ``evaluate_forget_action`` BEFORE the three memory second passes moved onto
PromptAssembler (run ``python3 -m tests.ciris_engine.logic.dma.msaspdma_golden`` on that tree). The migrated path
must send the same bytes. Deterministic: the #972 environment (language en, sentinel accord / guidance / crisis
blocks), fixed ids.

Fixtures per verb: ``plain`` (no context) and ``full``: a snapshot with a user profile and the channel (candidate
nodes), a verified sender, a verified WA grant and the conscience's retry feedback. ``ms_addressed_full``
additionally gives MEMORIZE a proposed node (the proposed_* slots carry ASPDMA's output).
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from ciris_engine.schemas.actions.parameters import ForgetParams, MemorizeParams, RecallParams
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.dma.results import UNADDRESSED_NODE_ID, ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import VerifiedSender, WAAuthorization
from ciris_engine.schemas.runtime.veto_record import VetoRecordEntry
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma.compose_golden import deterministic_prompt_environment, make_queue_item

GOLDEN_DIR = Path(__file__).parent / "golden"

SENDER = VerifiedSender(
    user_id="wa-user-0eve", role=UserRole.OBSERVER, source="api_auth", self_chosen_display_name="eve the admin"
)
GRANT = WAAuthorization(
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_c5aaf93c",
    granted_at="2026-01-01T00:00:00+00:00",
    guidance="Store the user's preferred name in identity scope.",
    response_attestation_id="att-resp-01",
    request_attestation_id="att-req-01",
)
RETRY_GUIDANCE = "Golden fixture: CONSCIENCE OVERRIDE GUIDANCE: do not store facts about someone else."
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


def full_context() -> Any:
    profile = SimpleNamespace(
        user_id="wa-user-0eve", display_name="eve the admin", memorized_attributes={"preferred_name": "Eve"}
    )
    snapshot = SimpleNamespace(user_profiles=[profile], channel_id="golden-channel", agent_identity=None)
    return SimpleNamespace(system_snapshot=snapshot, verified_sender=SENDER, wa_authorization=GRANT)


def _aspdma_result(verb: str, addressed: bool = False) -> ActionSelectionDMAResult:
    params: Any
    if verb == "ms":
        node = GraphNode(
            id="user/wa-user-0eve" if addressed else UNADDRESSED_NODE_ID,
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={"favorite_color": "chartreuse"},
        )
        params, action = MemorizeParams(channel_id="golden-channel", node=node), HandlerActionType.MEMORIZE
    elif verb == "rs":
        params, action = RecallParams(channel_id="golden-channel", query="favorite color"), HandlerActionType.RECALL
    else:
        node = GraphNode(id="user/wa-user-0eve", type=NodeType.USER, scope=GraphScope.LOCAL, attributes={})
        params, action = ForgetParams(channel_id="golden-channel", node=node, reason="asked"), HandlerActionType.FORGET
    return ActionSelectionDMAResult(
        selected_action=action, action_parameters=params, rationale=f"Golden fixture: {verb} selected."
    )


def _dma(verb: str, captured: Dict[str, Any]) -> Any:
    from ciris_engine.logic.dma.fsaspdma import FSASPDMAEvaluator, FSASPDMALLMResult
    from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator, MSASPDMALLMResult
    from ciris_engine.logic.dma.rsaspdma import RSASPDMAEvaluator, RSASPDMALLMResult

    cls, result = {
        "ms": (MSASPDMAEvaluator, MSASPDMALLMResult(final_action="PONDER", questions=["Golden?"])),
        "rs": (RSASPDMAEvaluator, RSASPDMALLMResult(final_action="PONDER", questions=["Golden?"])),
        "fs": (FSASPDMAEvaluator, FSASPDMALLMResult(final_action="PONDER", questions=["Golden?"])),
    }[verb]
    dma = cls(service_registry=Mock())

    async def _record(**kwargs: Any) -> Any:
        captured["messages"] = kwargs["messages"]
        try:
            from ciris_engine.logic.prompt_assembly import current_prompt_manifest

            captured["manifest"] = current_prompt_manifest()
        except ImportError:
            captured["manifest"] = None
        return result, None

    dma.call_llm_structured = _record  # type: ignore[method-assign]
    return dma


async def capture(name: str, captured: Optional[Dict[str, Any]] = None) -> List[JSONDict]:
    """``name`` is ``<verb>_<fixture>``: verb ms / rs / fs; fixture plain, full or (ms) addressed_full."""
    captured = {} if captured is None else captured
    verb, fixture = name.split("_", 1)
    dma = _dma(verb, captured)
    full = fixture.endswith("full")
    with deterministic_prompt_environment():
        await dma.evaluate(
            make_queue_item(),
            aspdma_result=_aspdma_result(verb, addressed=fixture == "addressed_full"),
            context=full_context() if full else None,
            conscience_feedback=FEEDBACK if full else None,
        )
    return [dict(m) for m in captured["messages"]]


NAMES: Dict[str, tuple[str, ...]] = {
    "msaspdma": ("ms_plain", "ms_full", "ms_addressed_full"),
    "rsaspdma": ("rs_plain", "rs_full"),
    "fsaspdma": ("fs_plain", "fs_full"),
}


def golden_path(site: str) -> Path:
    return GOLDEN_DIR / f"{site}_assembly_messages.json"


def load_golden(site: str) -> Dict[str, List[JSONDict]]:
    data: Dict[str, List[JSONDict]] = json.loads(golden_path(site).read_text(encoding="utf-8"))
    return data


async def _capture_all() -> Dict[str, Dict[str, List[JSONDict]]]:
    return {site: {name: await capture(name) for name in names} for site, names in NAMES.items()}


if __name__ == "__main__":
    for site, goldens in asyncio.run(_capture_all()).items():
        golden_path(site).write_text(
            json.dumps(goldens, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {golden_path(site)}")
