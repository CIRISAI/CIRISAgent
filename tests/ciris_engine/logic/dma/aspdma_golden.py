"""Fixtures + capture harness for the ASPDMA prompt goldens (CIRISAgent#1366 Phase 3).

``golden/aspdma_assembly_messages.json`` was captured BEFORE ASPDMA moved onto PromptAssembler (run
``python3 -m tests.ciris_engine.logic.dma.aspdma_golden`` on that tree): the #972/#986 compose fixtures (first
pass, conscience retry, exhausted bounce, ponder notes) plus a governed thought (verified amendment, a verified
WA grant, the format-retry block, an image). The migrated path must send the same bytes.
"""

import asyncio
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterator, List
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import ImageContent, WAAuthorization
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma import compose_golden as cg

GOLDEN_PATH = Path(__file__).parent / "golden" / "aspdma_assembly_messages.json"

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
IMAGE = ImageContent(source_type="base64", data="aGVsbG8=", media_type="image/png")

LAST: Dict[str, Any] = {}


def _recording_llm(captured: Dict[str, Any], result: Any) -> AsyncMock:
    async def _record(**kwargs: Any) -> Any:
        captured["messages"] = kwargs["messages"]
        try:
            from ciris_engine.logic.prompt_assembly import current_prompt_manifest

            LAST["manifest"] = current_prompt_manifest()
        except ImportError:
            LAST["manifest"] = None
        return (result, None)

    return AsyncMock(side_effect=_record)


async def capture_governed() -> List[JSONDict]:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.dma.results import ASPDMALLMResult

    inputs = cg.make_enhanced_inputs()
    snapshot = cg.make_system_snapshot().model_dump()
    snapshot["agent_identity"] = dict(snapshot["agent_identity"], approved_amendments=[AMENDMENT.model_dump()])
    inputs.processing_context = {
        "system_snapshot": snapshot,
        "wa_authorization": GRANT.model_dump(),
    }
    inputs.images = [IMAGE]
    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(selected_action=HandlerActionType.SPEAK, reasoning="r", speak_content="Golden fixture response."),
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


CAPTURES: Dict[str, Callable[[], Awaitable[List[JSONDict]]]] = {
    "first_pass": cg.capture_aspdma,
    "retry": cg.capture_aspdma_retry,
    "retry_observation": cg.capture_aspdma_retry_observation,
    "bounce_advisory": cg.capture_aspdma_bounce_advisory,
    "ponder_notes": cg.capture_aspdma_ponder_notes,
    "governed": capture_governed,
}


@contextmanager
def recording() -> Iterator[None]:
    with patch.object(cg, "_recording_llm", _recording_llm), cg.deterministic_prompt_environment():
        yield


async def capture(name: str) -> List[JSONDict]:
    LAST.clear()
    with recording():
        messages = await CAPTURES[name]()
    return json.loads(json.dumps(messages))


def load_golden() -> Dict[str, List[JSONDict]]:
    data: Dict[str, List[JSONDict]] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


async def _capture_all() -> Dict[str, List[JSONDict]]:
    return {name: await capture(name) for name in CAPTURES}


if __name__ == "__main__":
    GOLDEN_PATH.write_text(
        json.dumps(asyncio.run(_capture_all()), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {GOLDEN_PATH}")
