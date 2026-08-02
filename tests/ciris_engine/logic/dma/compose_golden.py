"""Deterministic fixtures + capture harness for compose_messages golden-bytes tests (#972).

Protocol
--------
1. BEFORE the #972 seam extraction, this module was executed as a script
   (``python -m tests.ciris_engine.logic.dma.compose_golden``) against the
   unmodified tree. It drives each DMA's ``evaluate()`` path with fully
   deterministic fixture inputs, intercepts ``call_llm_structured`` to record
   the composed ``messages`` list (no LLM is ever called), and snapshots the
   result to ``golden/<dma>_messages.json``.
2. AFTER the extraction, ``test_compose_messages_golden.py`` replays the same
   fixtures through (a) the ``evaluate()`` path and (b) the new
   ``compose_messages()`` seams directly, asserting byte equality against the
   pre-refactor snapshots.

Determinism
-----------
- All fixture ids/timestamps are fixed constants.
- ``CIRIS_PREFERRED_LANGUAGE`` is pinned to ``en``.
- The disk-loaded prompt *content* helpers (accord / localized accord /
  language guidance / prohibition guidance) are patched to short sentinel
  strings so the snapshots stay small and machine-independent. The patches are
  applied identically at capture time and replay time, so byte equality still
  proves the composition logic (block ordering, interpolation, concatenation)
  is unchanged. Sentinels are NON-EMPTY so the optional append branches are
  exercised.
- Persistence access (``fetch_original_task``, ASPDMA context pre-caching) is
  replaced with fixed fixtures - that is data *gathering*, not composition.
"""

from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Tuple
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import (
    ActionSelectionDMAResult,
    ASPDMALLMResult,
    CSDMAResult,
    DSDMAResult,
    EthicalDMAResult,
    IDMAResult,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict

GOLDEN_DIR = Path(__file__).parent / "golden"

DMA_NAMES = ("pdma", "csdma", "idma", "dsdma", "aspdma", "dsaspdma")

_FIXED_TS = "2026-01-01T00:00:00+00:00"
_THOUGHT_TEXT = "Should the agent reply with a summary of the weather report?"


# ---------------------------------------------------------------------------
# Deterministic environment (identical at capture time and replay time)
# ---------------------------------------------------------------------------


def _sentinel_accord(mode: str = "default") -> str:
    return f"<GOLDEN-ACCORD mode={mode}>"


def _sentinel_localized_accord(lang: Any = None) -> str:
    return f"<GOLDEN-LOCALIZED-ACCORD lang={lang}>"


def _sentinel_language_guidance(lang_code: str) -> str:
    return f"<GOLDEN-LANGUAGE-GUIDANCE lang={lang_code}>"


def _sentinel_prohibition_guidance(lang_code: str) -> str:
    return f"<GOLDEN-PROHIBITION-GUIDANCE lang={lang_code}>"


@contextmanager
def deterministic_prompt_environment() -> Iterator[None]:
    """Pin language + prompt-content loaders for byte-reproducible composition.

    Patch targets cover every import style used by the DMAs:
    - lazy in-function imports resolve from the defining module at call time;
    - module-top ``from x import y`` imports need the per-module name patched.
    """
    with ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ", {"CIRIS_PREFERRED_LANGUAGE": "en"}))
        # Source modules (covers all lazy in-function imports).
        stack.enter_context(patch("ciris_engine.logic.utils.constants.get_accord_text", _sentinel_accord))
        stack.enter_context(
            patch("ciris_engine.logic.utils.constants.get_localized_accord_text", _sentinel_localized_accord)
        )
        stack.enter_context(
            patch("ciris_engine.logic.utils.localization.get_language_guidance", _sentinel_language_guidance)
        )
        stack.enter_context(
            patch("ciris_engine.logic.utils.localization.get_prohibition_guidance", _sentinel_prohibition_guidance)
        )
        # Module-top imported names.
        stack.enter_context(patch("ciris_engine.logic.dma.idma.get_accord_text", _sentinel_accord))
        stack.enter_context(
            patch("ciris_engine.logic.dma.action_selection_pdma.get_localized_accord_text", _sentinel_localized_accord)
        )
        stack.enter_context(
            patch("ciris_engine.logic.dma.dsaspdma.get_localized_accord_text", _sentinel_localized_accord)
        )
        yield


# ---------------------------------------------------------------------------
# Fixed fixtures
# ---------------------------------------------------------------------------


def make_task() -> Task:
    return Task(
        task_id="golden-task-001",
        channel_id="golden-channel",
        description="Summarize today's weather report for the user",
        created_at=_FIXED_TS,
        updated_at=_FIXED_TS,
    )


def make_system_snapshot() -> SystemSnapshot:
    return SystemSnapshot(
        agent_identity={
            "agent_id": "golden_agent",
            "description": "Deterministic golden-fixture agent",
            "role": "Test fixture for compose_messages golden tests",
        },
        channel_id="golden-channel",
        agent_version="0.0.0-golden",
        system_counts={"total_tasks": 1, "total_thoughts": 1, "pending_tasks": 0, "pending_thoughts": 0},
    )


def make_context() -> SimpleNamespace:
    """Context object with a ``system_snapshot`` attribute (PDMA/CSDMA/IDMA)."""
    return SimpleNamespace(system_snapshot=make_system_snapshot())


def make_queue_item() -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text=_THOUGHT_TEXT, metadata={}),
        thought_depth=1,
    )


def make_dsdma_queue_item() -> ProcessingQueueItem:
    """DSDMA (no DMAInputData path) reads identity from ``initial_context``."""
    return ProcessingQueueItem(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text=_THOUGHT_TEXT, metadata={}),
        thought_depth=1,
        initial_context={"system_snapshot": make_system_snapshot().model_dump()},
    )


def make_thought() -> Thought:
    return Thought(
        thought_id="golden-thought-001",
        source_task_id="golden-task-001",
        content=_THOUGHT_TEXT,
        status=ThoughtStatus.PROCESSING,
        thought_type=ThoughtType.STANDARD,
        thought_depth=1,
        created_at=_FIXED_TS,
        updated_at=_FIXED_TS,
        context=ThoughtContext(task_id="golden-task-001", round_number=1, depth=1, correlation_id="golden-corr"),
    )


def make_ethical_result() -> EthicalDMAResult:
    return EthicalDMAResult(
        action=HandlerActionType.SPEAK,
        rationale="Golden fixture: replying is ethically unproblematic.",
        weight_alignment_score=0.8,
        ethical_alignment_score=0.9,
    )


def make_csdma_result() -> CSDMAResult:
    return CSDMAResult(plausibility_score=0.9, flags=["golden_flag"], reasoning="Golden fixture: plausible.")


def make_dsdma_result() -> DSDMAResult:
    return DSDMAResult(
        domain="golden_domain", domain_alignment=0.8, flags=[], reasoning="Golden fixture: aligned with domain."
    )


def make_enhanced_inputs() -> EnhancedDMAInputs:
    return EnhancedDMAInputs(
        original_thought=make_thought(),
        processing_context={"system_snapshot": make_system_snapshot().model_dump()},
        ethical_pdma_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
        permitted_actions=[
            HandlerActionType.OBSERVE,
            HandlerActionType.SPEAK,
            HandlerActionType.PONDER,
            HandlerActionType.DEFER,
            HandlerActionType.TASK_COMPLETE,
        ],
    )


def make_defer_aspdma_result() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=DeferParams(
            reason="Golden fixture: needs wise-authority input",
            context={"stakes": "high", "topics": ["weather", "safety"]},
        ),
        rationale="Golden fixture: deferring for classification.",
    )


def pin_aspdma_context_builder(dma: Any) -> None:
    """Pin ASPDMA's context-builder cached state (data gathering, not composition)."""
    dma.context_builder.pre_cache_context = AsyncMock(return_value=0)
    dma.context_builder._tools_cached = True
    dma.context_builder._cached_task = None
    dma.context_builder._cached_installable_tools = ""


# ---------------------------------------------------------------------------
# Capture via evaluate() (works identically before and after the extraction)
# ---------------------------------------------------------------------------


def _recording_llm(captured: Dict[str, Any], result: Any) -> AsyncMock:
    async def _record(**kwargs: Any) -> Tuple[Any, Any]:
        captured["messages"] = kwargs["messages"]
        return (result, None)

    return AsyncMock(side_effect=_record)


async def capture_pdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    dma = EthicalPDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_ethical_result())  # type: ignore[method-assign]
    await dma.evaluate(make_queue_item(), make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_csdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    dma = CSDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_csdma_result())  # type: ignore[method-assign]
    await dma.evaluate(make_queue_item(), make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_idma() -> List[JSONDict]:
    from ciris_engine.logic.dma.idma import IDMAEvaluator

    dma = IDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        IDMAResult(
            k_eff=3.0,
            correlation_risk=0.2,
            phase="healthy",
            fragility_flag=False,
            reasoning="Golden fixture: diverse sources.",
        ),
    )
    await dma.evaluate(
        make_queue_item(),
        make_context(),
        ethical_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
    )
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_dsdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    dma = BaseDSDMA(
        domain_name="golden_domain",
        service_registry=Mock(),
        domain_specific_knowledge={
            "rules_summary": "Golden rules: always be deterministic.",
            "escalation_paths": ["wise_authority", "human_operator"],
        },
    )
    dma.fetch_original_task = AsyncMock(return_value=make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(captured, make_dsdma_result())  # type: ignore[method-assign]
    await dma.evaluate(make_dsdma_queue_item())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_aspdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        ASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Golden fixture: speak.",
            speak_content="Golden fixture response.",
        ),
    )
    await dma.evaluate(make_enhanced_inputs())
    return captured["messages"]  # type: ignore[no-any-return]


async def capture_dsaspdma() -> List[JSONDict]:
    from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator, DSASPDMALLMResult
    from ciris_engine.schemas.services.deferral_taxonomy import DeferralNeedCategory, DeferralOperationalReason

    dma = DSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(  # type: ignore[method-assign]
        captured,
        DSASPDMALLMResult(
            reason_summary="Golden fixture deferral",
            operational_reason=list(DeferralOperationalReason)[0],
            primary_need_category=list(DeferralNeedCategory)[0],
        ),
    )
    await dma.evaluate(make_defer_aspdma_result(), make_queue_item(), context=None)
    return captured["messages"]  # type: ignore[no-any-return]


_CAPTURE_FNS = {
    "pdma": capture_pdma,
    "csdma": capture_csdma,
    "idma": capture_idma,
    "dsdma": capture_dsdma,
    "aspdma": capture_aspdma,
    "dsaspdma": capture_dsaspdma,
}


async def capture_via_evaluate(name: str) -> List[JSONDict]:
    """Run the named DMA's evaluate() path and return the composed messages."""
    with deterministic_prompt_environment():
        return await _CAPTURE_FNS[name]()


# ---------------------------------------------------------------------------
# Golden snapshot IO
# ---------------------------------------------------------------------------


def canonical_json(messages: List[JSONDict]) -> str:
    """Canonical byte-comparable serialization of a message list."""
    return json.dumps(messages, ensure_ascii=False, sort_keys=True, indent=2)


def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}_messages.json"


def load_golden(name: str) -> List[JSONDict]:
    with open(golden_path(name), encoding="utf-8") as f:
        loaded: List[JSONDict] = json.load(f)
    return loaded


def write_golden(name: str, messages: List[JSONDict]) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    with open(golden_path(name), "w", encoding="utf-8") as f:
        f.write(canonical_json(messages))
        f.write("\n")


def _main() -> None:
    import asyncio

    for name in DMA_NAMES:
        messages = asyncio.run(capture_via_evaluate(name))
        write_golden(name, messages)
        print(f"captured {name}: {len(messages)} messages -> {golden_path(name)}")


if __name__ == "__main__":
    _main()
