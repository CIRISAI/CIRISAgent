"""One language per thought, from the message to every stage (#1366 follow-up).

RATCHET's context-map runs sent API messages with ``context.metadata.language =
"am"``. The consciences rendered Amharic; the DMAs rendered English (0 Ethiopic
characters out of 18,410 in the PDMA stage instruction). The thought carried the
language (the task's ``preferred_language``, inherited onto the thought's
context), but the DMAs looked for it on ``ProcessingQueueItem.preferred_language``
(no such field) and in a ``ProcessingThoughtContext`` (which keeps the task on
``initial_task_context``), so they fell to the user's profile -- whose
``preferred_language`` defaults to "en". The consciences read the thought's
inner context and got "am".

Every stage now resolves through ``resolve_thought_language``. These tests drive
a thought built the way the observer builds one from an API message whose
metadata says "am", for a user whose profile says "en", with the deployment
default "en" -- and assert each stage's own template text is Amharic. The
accord, language guidance, prohibition guidance and crisis resources are pinned
to ASCII sentinels (the polyglot accord always carries Ethiopic, which would make
the check vacuous), so any Ethiopic left can only come from the stage's template.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.adapters.base_observer import _resolve_observer_task_language
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.utils.localization import (
    get_preferred_language,
    resolve_thought_language,
    thought_language_scope,
)
from ciris_engine.logic.utils.task_thought_factory import create_seed_thought_for_task, create_task
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.context.prompt_provenance import PromptStage
from ciris_engine.schemas.dma.results import CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.runtime.processing_context import ProcessingThoughtContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, UserProfile
from ciris_engine.schemas.types import JSONDict
from tests.ciris_engine.logic.dma.compose_golden import (
    deterministic_prompt_environment,
    make_csdma_result,
    make_dsdma_result,
    make_ethical_result,
    pin_aspdma_context_builder,
)


# English templates carry a few Ethiopic characters of their own (PDMA's polyglot heading "ህሊና"); an am
# template carries thousands. A stage counts as rendered in Amharic only above this floor.
_AM_SYSTEM_FLOOR = 100


def _ethiopic(text: str) -> int:
    return sum(1 for ch in text if "ሀ" <= ch <= "፿")


def _text(messages: List[JSONDict], role: str) -> str:
    parts: List[str] = []
    for message in messages:
        if message.get("role") != role:
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(str(block.get("text", "")) for block in content if isinstance(block, dict))
    return "\n".join(parts)


def _snapshot() -> SystemSnapshot:
    """The QA user's profile says "en" (the UserProfile default) -- the message's "am" must win."""
    return SystemSnapshot(
        agent_identity={"agent_id": "lang_agent", "description": "Localization fixture", "role": "Fixture"},
        channel_id="api_lang",
        agent_version="0.0.0-lang",
        system_counts={"total_tasks": 1, "total_thoughts": 1, "pending_tasks": 0, "pending_thoughts": 0},
        user_profiles=[
            UserProfile(user_id="qa_user", display_name="QA", created_at=datetime.now(timezone.utc))
        ],
    )


def _thought_from_message(language: str, tag: str = "lang") -> Tuple[Task, ProcessingQueueItem]:
    """Task + seed thought exactly as the observer builds them from an API message."""
    msg = IncomingMessage(
        message_id=f"msg-{tag}",
        author_id="qa_user",
        author_name="QA",
        content="What should I know about the weather today?",
        channel_id="api_lang",
        preferred_language=language,  # the API route's context.metadata.language
    )
    task = create_task(
        description=f"Respond to message from QA in #api_lang: '{msg.content}'",
        channel_id="api_lang",
        agent_occurrence_id="default",
        correlation_id=msg.message_id,
        status=TaskStatus.ACTIVE,
        task_id=f"task-{tag}",
        user_id="qa_user",
        preferred_language=_resolve_observer_task_language(msg),
    )
    thought = create_seed_thought_for_task(task=task)
    return task, ProcessingQueueItem.from_thought(thought, task_images=[])


def _processing_context(task: Task) -> ProcessingThoughtContext:
    """What ContextBuilder.build_thought_context hands every DMA."""
    snapshot = _snapshot()
    return ProcessingThoughtContext(
        system_snapshot=snapshot,
        user_profiles={p.user_id: p for p in snapshot.user_profiles},
        initial_task_context=task.context,
    )


def _recording_llm(captured: Dict[str, Any], result: Any) -> AsyncMock:
    async def _record(**kwargs: Any) -> Tuple[Any, Any]:
        captured["messages"] = kwargs["messages"]
        return (result, None)

    return AsyncMock(side_effect=_record)


async def _pdma(task: Task, item: ProcessingQueueItem, evaluator: Any = None) -> List[JSONDict]:
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    dma = evaluator or EthicalPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(captured, make_ethical_result())
    await dma.evaluate(item, _processing_context(task))
    return captured["messages"]  # type: ignore[no-any-return]


async def _csdma(task: Task, item: ProcessingQueueItem) -> List[JSONDict]:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    dma = CSDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(captured, make_csdma_result())
    await dma.evaluate(item, _processing_context(task))
    return captured["messages"]  # type: ignore[no-any-return]


async def _idma(task: Task, item: ProcessingQueueItem) -> List[JSONDict]:
    from ciris_engine.logic.dma.idma import IDMAEvaluator
    from ciris_engine.schemas.dma.results import IDMAResult

    dma = IDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(
        captured, IDMAResult(k_eff=3.0, correlation_risk=0.2, phase="healthy", fragility_flag=False, reasoning="ok")
    )
    await dma.evaluate(
        item,
        _processing_context(task),
        ethical_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
    )
    return captured["messages"]  # type: ignore[no-any-return]


async def _dsdma(task: Task, item: ProcessingQueueItem) -> List[JSONDict]:
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA
    from ciris_engine.schemas.processors.dma import DMAMetadata

    dma = BaseDSDMA(domain_name="lang_domain", service_registry=Mock(), domain_specific_knowledge={})
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(captured, make_dsdma_result())
    # DSDMA's no-DMAInputData path reads the snapshot off the thought's initial context.
    initial = item.initial_context.model_dump() if hasattr(item.initial_context, "model_dump") else {}
    dsdma_item = item.model_copy(update={"initial_context": {**initial, "system_snapshot": _snapshot().model_dump()}})
    await dma.evaluate(dsdma_item, DMAMetadata())
    return captured["messages"]  # type: ignore[no-any-return]


async def _aspdma(task: Task, item: ProcessingQueueItem) -> List[JSONDict]:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
    from ciris_engine.schemas.dma.results import ASPDMALLMResult

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(
        captured, ASPDMALLMResult(selected_action=HandlerActionType.SPEAK, reasoning="ok", speak_content="ok")
    )
    inputs = EnhancedDMAInputs(
        original_thought=item,
        processing_context=_processing_context(task),
        ethical_pdma_result=make_ethical_result(),
        csdma_result=make_csdma_result(),
        dsdma_result=make_dsdma_result(),
        permitted_actions=[HandlerActionType.SPEAK, HandlerActionType.PONDER, HandlerActionType.TASK_COMPLETE],
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


STAGES = {"pdma": _pdma, "csdma": _csdma, "dsdma": _dsdma, "idma": _idma, "aspdma": _aspdma}


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", sorted(STAGES))
async def test_message_language_reaches_every_dma(stage: str) -> None:
    """Message metadata "am", profile "en", deployment default "en": the stage renders its am template."""
    with deterministic_prompt_environment():
        assert get_preferred_language() == "en"
        task, item = _thought_from_message("am")
        messages = await STAGES[stage](task, item)
    system = _text(messages, "system")
    assert _ethiopic(system) > _AM_SYSTEM_FLOOR, f"{stage}: system prompt rendered without the am template"
    # dsdma_base's localized user template is base-verbatim (no translation to carry yet).
    if stage != "dsdma":
        user = _text(messages, "user")
        assert _ethiopic(user) > 0, f"{stage}: user prompt rendered without the am template"


CONSCIENCES = {
    "entropy": ("EntropyConscience", PromptStage.ENTROPY, "entropy_conscience", "text"),
    "coherence": ("CoherenceConscience", PromptStage.COHERENCE, "coherence_conscience", "text"),
    "optimization_veto": (
        "OptimizationVetoConscience",
        PromptStage.OPTVETO,
        "optimization_veto_conscience",
        "action_description",
    ),
    "epistemic_humility": (
        "EpistemicHumilityConscience",
        PromptStage.EPISTEMIC,
        "epistemic_humility_conscience",
        "action_description",
    ),
}


@pytest.mark.parametrize("name", sorted(CONSCIENCES))
def test_message_language_reaches_every_conscience(name: str) -> None:
    from ciris_engine.logic.conscience import core
    from ciris_engine.logic.conscience.core import ConscienceConfig

    cls_name, stage, conscience_type, draft_slot = CONSCIENCES[name]
    with deterministic_prompt_environment():
        task, item = _thought_from_message("am")
        conscience = getattr(core, cls_name)(
            service_registry=Mock(), config=ConscienceConfig(), time_service=Mock(), sink=None
        )
        context = ConscienceCheckContext(thought=item, task=task, system_snapshot=_snapshot())
        language = conscience._resolve_language(context)
        assert language == "am"
        # As OptimizationVetoConscience.check passes it (its one universal prompt carries the locale as a slot).
        plain_slots = {"user_locale": language} if name == "optimization_veto" else None
        prompt = conscience._assemble(
            stage,
            context,
            conscience_type=conscience_type,
            draft_slot=draft_slot,
            draft_text="The weather today is mild.",
            image_context=None,
            response_model=EthicalDMAResult,
            user_message="What should I know about the weather today?",
            plain_slots=plain_slots,
        )
    if name == "optimization_veto":
        # One universal polyglot prompt by design (no localized copies); the thought's locale rides its slot.
        user = "\n".join(str(m.content) for m in prompt.messages if m.role == "user")
        assert "User's preferred locale: am" in user
        return
    system = "\n".join(str(m.content) for m in prompt.messages if m.role == "system")
    assert _ethiopic(system) > _AM_SYSTEM_FLOOR, f"{name}: conscience rendered without the am template"


def test_profile_en_and_message_am_resolve_am() -> None:
    """The explicit per-message choice outranks the stored profile: it is the user's latest word."""
    task, item = _thought_from_message("am")
    context = _processing_context(task)
    assert context.system_snapshot.user_profiles[0].preferred_language == "en"
    assert resolve_thought_language(item, context) == "am"
    # Through the context alone too (the ProcessingThoughtContext keeps the task on initial_task_context).
    assert resolve_thought_language(None, context) == "am"


@pytest.mark.asyncio
async def test_concurrent_thoughts_in_different_languages_do_not_bleed() -> None:
    """One shared PDMA evaluator, an am and an es thought interleaved across awaits."""
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
    from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

    def header_lines(language: str) -> List[str]:
        header = DMAPromptLoader(language=language).load_prompt_template("pdma_ethical").system_guidance_header or ""
        return [line.strip() for line in header.splitlines() if len(line.strip()) > 20 and "{" not in line]

    am_lines, es_lines = header_lines("am"), header_lines("es")
    # A line of each locale's own header that the other locale does not carry (the first is polyglot).
    am_position = next(line for line in am_lines if line not in es_lines)
    es_position = next(line for line in es_lines if line not in am_lines)

    with deterministic_prompt_environment():
        dma = EthicalPDMAEvaluator(service_registry=Mock())
        am_task, am_item = _thought_from_message("am", "am")
        es_task, es_item = _thought_from_message("es", "es")
        gate = asyncio.Event()
        captured: Dict[str, List[JSONDict]] = {}

        async def fetch(task_id: str, _occ: str = "default") -> Task:
            if task_id == am_task.task_id:
                await gate.wait()  # the am thought resumes only after the es thought has composed
                return am_task
            return es_task

        async def record(**kwargs: Any) -> Tuple[Any, Any]:
            captured[kwargs["thought_id"]] = kwargs["messages"]
            if kwargs["thought_id"] == es_item.thought_id:
                gate.set()
                await asyncio.sleep(0)  # still in flight while the am thought composes
            return (make_ethical_result(), None)

        dma.fetch_original_task = fetch  # type: ignore[method-assign]
        dma.call_llm_structured = AsyncMock(side_effect=record)  # type: ignore[method-assign]
        await asyncio.gather(
            dma.evaluate(am_item, _processing_context(am_task)),
            dma.evaluate(es_item, _processing_context(es_task)),
        )

    am_system = _text(captured[am_item.thought_id], "system")
    es_system = _text(captured[es_item.thought_id], "system")
    assert am_position in am_system and es_position not in am_system
    assert es_position in es_system and am_position not in es_system
    assert _ethiopic(es_system) < _AM_SYSTEM_FLOOR
    assert dma.thought_language == get_preferred_language(), "the evaluator kept a thought's language"


@pytest.mark.asyncio
async def test_language_scope_is_task_local() -> None:
    """Two concurrent scopes across awaits each read only their own language."""
    seen: Dict[str, List[str]] = {"am": [], "es": []}

    async def stage(language: str) -> None:
        from ciris_engine.logic.utils.localization import current_thought_language

        with thought_language_scope(language):
            for _ in range(3):
                await asyncio.sleep(0)
                seen[language].append(current_thought_language())

    await asyncio.gather(stage("am"), stage("es"))
    assert seen == {"am": ["am"] * 3, "es": ["es"] * 3}
