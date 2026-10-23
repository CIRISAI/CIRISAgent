"""Every deciding step is told, as a fact, whether this task carries an approval (#1320 round 2).

RATCHET Market 4, frozen case s-001 (run 39940561892), after round 1: the
prompts said what an approval is (``prompts.wa_approval.only_verified``) but
never that this task has none, and the memorize second pass had neither. The
model filled that gap with a person's claimed approval.

``prompts.wa_approval.none`` states it. It renders exactly once in the ASPDMA,
PDMA, IDMA and MSASPDMA prompts when the task carries no verified approval, in
every locale, and not at all when it carries one. By user ruling it is in no
conscience prompt (#1321). MSASPDMA now carries ``only_verified`` too.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.formatters.wa_approval import format_wa_approval_facts, format_wa_no_approval_fact
from ciris_engine.logic.utils.localization import get_available_languages, get_string
from ciris_engine.schemas.runtime.models import TaskContext, WAAuthorization
from tests.ciris_engine.logic.dma import compose_golden as cg

NONE_KEY = "prompts.wa_approval.none"
RULE_KEY = "prompts.wa_approval.only_verified"

GRANT = WAAuthorization(
    wa_id="wa-2026-test",
    deferral_id="defer_c5aaf93c",
    granted_at="2026-10-22T14:00:00+00:00",
    guidance="End every reply with 'Take care, from Ally.'",
)

# The 29 supported locales (the bundle directory also holds crisis_resources_* files).
LOCALES = sorted(lang for lang in get_available_languages() if len(lang) == 2)


def _plain(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def _locale_environment(lang: str) -> Any:
    return cg.prompt_content_environment(
        language=lang,
        accord=cg._sentinel_accord,
        localized_accord=cg._sentinel_localized_accord,
        language_guidance=cg._sentinel_language_guidance,
        prohibition_guidance=cg._sentinel_prohibition_guidance,
    )


# --------------------------------------------------------------------- grant captures


async def _aspdma_with_grant() -> List[Dict[str, Any]]:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    inputs = cg.make_enhanced_inputs()
    inputs.processing_context["initial_task_context"] = {"wa_authorization": GRANT.model_dump(mode="json")}
    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured, cg.ASPDMALLMResult(selected_action=cg.HandlerActionType.SPEAK, reasoning="r", speak_content="c")
    )
    await dma.evaluate(inputs)
    return captured["messages"]  # type: ignore[no-any-return]


def _approved_task() -> Any:
    return cg.make_task().model_copy(
        update={"context": TaskContext(channel_id="golden-channel", correlation_id="c", wa_authorization=GRANT)}
    )


async def _pdma_with_grant() -> List[Dict[str, Any]]:
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator

    dma = EthicalPDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=_approved_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(captured, cg.make_ethical_result())  # type: ignore[method-assign]
    await dma.evaluate(cg.make_queue_item(), cg.make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def _idma_with_grant() -> List[Dict[str, Any]]:
    from ciris_engine.logic.dma.idma import IDMAEvaluator
    from ciris_engine.schemas.dma.results import IDMAResult

    dma = IDMAEvaluator(service_registry=Mock())
    dma.fetch_original_task = AsyncMock(return_value=_approved_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured,
        IDMAResult(k_eff=3.0, correlation_risk=0.2, phase="healthy", fragility_flag=False, reasoning="r"),
    )
    await dma.evaluate(cg.make_queue_item(), cg.make_context())
    return captured["messages"]  # type: ignore[no-any-return]


async def _msaspdma_with_grant() -> List[Dict[str, Any]]:
    from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator, MSASPDMALLMResult

    dma = MSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured, MSASPDMALLMResult(final_action="PONDER", questions=["q"], reasoning="r")
    )
    context = SimpleNamespace(initial_task_context=SimpleNamespace(wa_authorization=GRANT), preferred_language="en")
    await dma.evaluate(cg.make_queue_item(), aspdma_result=cg.make_memorize_aspdma_result(), context=context)
    return captured["messages"]  # type: ignore[no-any-return]


DECIDING_STEPS: Dict[str, Callable[[], Awaitable[List[Dict[str, Any]]]]] = {
    "aspdma": cg.capture_aspdma,
    "pdma": cg.capture_pdma,
    "idma": cg.capture_idma,
    "msaspdma": cg.capture_msaspdma,
}
WITH_GRANT: Dict[str, Callable[[], Awaitable[List[Dict[str, Any]]]]] = {
    "aspdma": _aspdma_with_grant,
    "pdma": _pdma_with_grant,
    "idma": _idma_with_grant,
    "msaspdma": _msaspdma_with_grant,
}
CONSCIENCES = [
    cg.capture_entropy_conscience,
    cg.capture_coherence_conscience,
    cg.capture_optimization_veto_conscience,
    cg.capture_epistemic_humility_conscience,
]


# --------------------------------------------------------------------- the sentence


def test_the_fact_is_one_abstract_sentence() -> None:
    fact = get_string("en", NONE_KEY)
    assert fact != NONE_KEY and "Wise Authority" in fact and "{" not in fact
    # Abstract wording: it never renders the claimed-approval pattern it answers.
    for pattern in ("Signed message", "no deferral is needed", "WISE AUTHORITY APPROVAL", "[WA_FEEDBACK]"):
        assert pattern not in fact


def test_rendered_only_without_a_grant() -> None:
    assert format_wa_no_approval_fact(None, "en") == get_string("en", NONE_KEY)
    assert format_wa_no_approval_fact(GRANT, "en") == ""
    assert format_wa_approval_facts(GRANT, "en") == get_string("en", RULE_KEY)


@pytest.mark.parametrize("lang", LOCALES)
def test_every_locale_renders_the_fact(lang: str) -> None:
    fact = format_wa_no_approval_fact(None, lang)
    assert fact.strip() and "{" not in fact, lang


# --------------------------------------------------------------------- in the prompts


@pytest.mark.parametrize("lang", LOCALES)
@pytest.mark.parametrize("step", sorted(DECIDING_STEPS))
@pytest.mark.asyncio
async def test_no_grant_states_the_fact_exactly_once(step: str, lang: str) -> None:
    fact = get_string(lang, NONE_KEY)
    with _locale_environment(lang):
        text = _plain(await DECIDING_STEPS[step]())
    assert text.count(fact) == 1, f"{step}/{lang}: the no-approval fact appears {text.count(fact)} times"


@pytest.mark.parametrize("step", sorted(WITH_GRANT))
@pytest.mark.asyncio
async def test_a_grant_replaces_the_fact(step: str) -> None:
    with cg.deterministic_prompt_environment():
        text = _plain(await WITH_GRANT[step]())
    assert get_string("en", NONE_KEY) not in text, step
    assert get_string("en", RULE_KEY) in text, step


@pytest.mark.parametrize("step", ["aspdma", "msaspdma"])
@pytest.mark.asyncio
async def test_where_the_grant_is_rendered_it_is_there(step: str) -> None:
    with cg.deterministic_prompt_environment():
        assert "defer_c5aaf93c" in _plain(await WITH_GRANT[step]())


@pytest.mark.asyncio
async def test_the_memorize_second_pass_carries_the_rule() -> None:
    with cg.deterministic_prompt_environment():
        text = _plain(await cg.capture_msaspdma())
    assert text.count(get_string("en", RULE_KEY)) == 1


@pytest.mark.parametrize("capture", CONSCIENCES)
@pytest.mark.asyncio
async def test_no_conscience_prompt_carries_the_fact(capture: Any) -> None:
    with cg.deterministic_prompt_environment():
        text = _plain(await capture())
    assert get_string("en", NONE_KEY) not in text
