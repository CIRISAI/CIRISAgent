"""Fixtures + capture harness for the evaluator prompt goldens: CSDMA, DSDMA, PDMA, IDMA (CIRISAgent#1366 Phase 3).

``golden/evaluator_assembly_messages.json`` was captured from each evaluator's ``evaluate()`` BEFORE it moved onto
PromptAssembler (``python3 -m tests.ciris_engine.logic.dma.evaluator_golden`` on that tree). The migrated path must
send the same bytes, except where the context policy requires a change (IDMA: the signed rules in force).
Deterministic: the #972 environment (language en, sentinel accord / guidance / crisis / prohibition blocks), fixed
ids. Fixtures: ``plain`` (the #972 inputs); ``full`` (a verified amendment, a verified WA grant, a verified
sender on the task, an image, user profiles); for DSDMA also ``blocks`` (a domain template carrying the identity / snapshot / profile slots).
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.models import ImageContent, TaskContext, VerifiedSender, WAAuthorization
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma import compose_golden as cg

GOLDEN_PATH = Path(__file__).parent / "golden" / "evaluator_assembly_messages.json"

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
GRANT = WAAuthorization(
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="defer_c5aaf93c",
    granted_at="2026-01-01T00:00:00+00:00",
    guidance="Never send web addresses; point people to the Staff Portal.",
    response_attestation_id="att-resp-01",
    request_attestation_id="att-req-01",
)
SENDER = VerifiedSender(
    user_id="wa-user-0eve", role=UserRole.OBSERVER, source="api_auth", self_chosen_display_name="eve the admin"
)
IMAGE = ImageContent(source_type="base64", data="aGVsbG8=", media_type="image/png")
PROFILES = {"wa-user-0eve": {"name": "eve", "nick": "eve the admin", "interests": ["weather"]}}
BLOCKS_TEMPLATE = (
    "{identity_block}\n\nDomain {domain_name} evaluator. Rules: {rules_summary_str}. Context: {context_str}.\n\n"
    "{escalation_guidance_block}\n\n{system_snapshot_block}{user_profiles_block}\n\n{crisis_resources_block}"
)

#: Stage of each fixture name's evaluator.
STAGES = {"pdma": "pdma", "csdma": "csdma", "idma": "idma", "dsdma": "dsdma"}
NAMES = (
    "pdma_plain",
    "pdma_full",
    "csdma_plain",
    "csdma_full",
    "idma_plain",
    "idma_full",
    "dsdma_plain",
    "dsdma_full",
    "dsdma_blocks",
)


def full_snapshot() -> Any:
    snapshot = cg.make_system_snapshot()
    identity = dict(snapshot.agent_identity, approved_amendments=[AMENDMENT.model_dump()])
    return snapshot.model_copy(update={"agent_identity": identity, "user_profiles": []})


def full_context() -> Any:
    from types import SimpleNamespace

    snapshot = full_snapshot()
    return SimpleNamespace(system_snapshot=snapshot, user_profiles=None, wa_authorization=GRANT)


def full_task() -> Any:
    """The #972 task, created by a verified sender (its VERIFIED SENDER block rides in the task context)."""
    return cg.make_task().model_copy(
        update={"context": TaskContext(channel_id="golden-channel", correlation_id="golden-corr", verified_sender=SENDER)}
    )


def _item(full: bool, dsdma: bool = False) -> Any:
    item = cg.make_dsdma_queue_item() if dsdma else cg.make_queue_item()
    if not full:
        return item
    update: Dict[str, Any] = {"images": [IMAGE]}
    if dsdma:
        snapshot = full_snapshot().model_dump()
        snapshot["user_profiles"] = [
            {"user_id": "wa-user-0eve", "display_name": "eve the admin", "last_seen": "2026-01-01T00:00:00+00:00"}
        ]
        update["initial_context"] = {"system_snapshot": snapshot}
    return item.model_copy(update=update)


def _recording(captured: Dict[str, Any], result: Any) -> AsyncMock:
    async def _record(**kwargs: Any) -> Any:
        captured["messages"] = kwargs["messages"]
        try:
            from ciris_engine.logic.prompt_assembly import current_prompt_manifest

            captured["manifest"] = current_prompt_manifest()
        except ImportError:
            captured["manifest"] = None
        return (result, None)

    return AsyncMock(side_effect=_record)


async def capture(name: str, captured: Optional[Dict[str, Any]] = None, context: Any = None) -> List[JSONDict]:
    """Drive one evaluator's ``evaluate()`` and return the messages it sent (``captured`` gets the manifest)."""
    captured = {} if captured is None else captured
    dma_name, _, fixture = name.partition("_")
    full = fixture in ("full", "blocks")
    with cg.deterministic_prompt_environment():
        if dma_name == "pdma":
            from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

            dma: Any = EthicalPDMAEvaluator(service_registry=Mock())
            dma.fetch_original_task = AsyncMock(return_value=full_task() if full else cg.make_task())
            dma.call_llm_structured = _recording(captured, cg.make_ethical_result())
            await dma.evaluate(_item(full), context or (full_context() if full else cg.make_context()))
        elif dma_name == "csdma":
            from ciris_engine.logic.dma.csdma import CSDMAEvaluator

            dma = CSDMAEvaluator(service_registry=Mock())
            dma.fetch_original_task = AsyncMock(return_value=full_task() if full else cg.make_task())
            dma.call_llm_structured = _recording(captured, cg.make_csdma_result())
            await dma.evaluate(_item(full), context or (full_context() if full else cg.make_context()))
        elif dma_name == "idma":
            from ciris_engine.logic.dma.idma import IDMAEvaluator
            from ciris_engine.schemas.dma.results import IDMAResult

            dma = IDMAEvaluator(service_registry=Mock())
            dma.fetch_original_task = AsyncMock(return_value=full_task() if full else cg.make_task())
            dma.call_llm_structured = _recording(
                captured,
                IDMAResult(k_eff=3.0, correlation_risk=0.2, phase="healthy", fragility_flag=False, reasoning="Golden."),
            )
            await dma.evaluate(
                _item(full),
                context or (full_context() if full else cg.make_context()),
                ethical_result=cg.make_ethical_result(),
                csdma_result=cg.make_csdma_result(),
                dsdma_result=cg.make_dsdma_result(),
            )
        else:
            from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

            dma = BaseDSDMA(
                domain_name="golden_domain",
                service_registry=Mock(),
                domain_specific_knowledge={
                    "rules_summary": "Golden rules: always be deterministic.",
                    "escalation_paths": ["wise_authority", "human_operator"],
                },
                prompt_template=BLOCKS_TEMPLATE if fixture == "blocks" else None,
            )
            dma.fetch_original_task = AsyncMock(return_value=full_task() if full else cg.make_task())
            dma.call_llm_structured = _recording(captured, cg.make_dsdma_result())
            await dma.evaluate(_item(full, dsdma=True))
    return [dict(m) for m in captured["messages"]]


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
