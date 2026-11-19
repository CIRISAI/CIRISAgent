"""DSDMA in the thought's language; agent-template text carries the agent-profile source (#1366, RATCHET am map).

RATCHET's Amharic context map (run on b3151d6df): every stage rendered Amharic except DSDMA (54/54 calls under 200
Ethiopic characters), whose stage instruction carried the ENGLISH language primer. The orchestrator hands DSDMA
``DMAMetadata``, never the processing context PDMA and CSDMA resolve against; gather_context stores that context on
the queue item (``initial_context``), where the message's language sits on ``initial_task_context`` -- and DSDMA
did not read it, so it fell to the deployment default.

And the agent template's own text (Ally's DSDMA domain knowledge, ASPDMA ``system_header`` and ``user_prompt_template``
framing, CSDMA ``system_prompt`` and framing) was labelled ``source: engine`` in the manifest. FSD
PROMPT_CONTEXT_PROVENANCE §4.3: it is ``agent_profile``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from ciris_engine.logic.dma.dsdma_base import BaseDSDMA, _format_domain_specific_knowledge
from ciris_engine.logic.utils.localization import get_language_guidance
from ciris_engine.schemas.context.prompt_provenance import SegmentSource
from ciris_engine.schemas.processors.dma import DMAMetadata
from tests.ciris_engine.logic.dma.compose_golden import make_csdma_result, make_dsdma_result
from tests.ciris_engine.logic.dma.test_thought_language_one_resolver import (
    _ethiopic,
    _processing_context,
    _recording_llm,
    _thought_from_message,
)

TEMPLATES = Path(__file__).parents[4] / "ciris_engine" / "ciris_templates"


def _template(name: str) -> Dict[str, Any]:
    data: Dict[str, Any] = yaml.safe_load((TEMPLATES / f"{name}.yaml").read_text(encoding="utf-8"))
    return data


def _capturing(dma: Any) -> Dict[str, Any]:
    """Record the manifest the evaluator's compose_prompt returns."""
    seen: Dict[str, Any] = {}
    compose = dma.compose_prompt

    def wrapped(*args: Any, **kwargs: Any) -> Tuple[List[Any], Any]:
        messages, manifest = compose(*args, **kwargs)
        seen["messages"], seen["manifest"] = messages, manifest
        return messages, manifest

    dma.compose_prompt = wrapped
    return seen


def _text(messages: List[Any], index: int) -> str:
    content = messages[index]["content"]
    return content if isinstance(content, str) else str(content[0]["text"])


def _segments(seen: Dict[str, Any], prefix: str) -> List[Any]:
    return [r for r in seen["manifest"].segments if r.segment_id.startswith(prefix)]


def _span(seen: Dict[str, Any], record: Any) -> str:
    return _text(seen["messages"], record.message_index)[record.span_start : record.span_end]


@pytest.fixture
def env_en(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployment default is English: the thought's own language must win."""
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")


async def _ally_dsdma_am(prompt_template: Any = None) -> Dict[str, Any]:
    """An `am` API message under the Ally template, its queue item shaped as gather_context leaves it."""
    ally = _template("default")["dsdma_kwargs"]
    dma = BaseDSDMA(
        domain_name="Ally",
        service_registry=Mock(),
        domain_specific_knowledge=ally["domain_specific_knowledge"],
        prompt_template=prompt_template,
    )
    task, item = _thought_from_message("am", tag="ally-dsdma")
    # gather_context.py: `thought_item.initial_context = thought_context.model_dump()` -- the processing context
    # replaces the thought's own context; the message's language is on its initial_task_context only.
    item = item.model_copy(update={"initial_context": _processing_context(task).model_dump()})
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(captured, make_dsdma_result())
    seen = _capturing(dma)
    await dma.evaluate(item, DMAMetadata())  # what dma_orchestrator.run_initial_dmas hands DSDMA
    seen["knowledge"] = _format_domain_specific_knowledge(ally["domain_specific_knowledge"])
    return seen


@pytest.mark.asyncio
async def test_am_thought_under_ally_renders_dsdma_with_the_am_primer_and_am_engine_text(env_en: None) -> None:
    seen = await _ally_dsdma_am()
    (primer,) = _segments(seen, "instr:language")
    assert _span(seen, primer) == get_language_guidance("am").strip()
    system = "\n".join(_text(seen["messages"], r.message_index) for r in seen["manifest"].segments)
    assert "ENGLISH OPERATING RULES" not in system
    # The engine's role and instructions, in Amharic (the am dsdma_base header), not the English file's.
    engine = "".join(_span(seen, r) for r in _segments(seen, "instr:system"))
    assert _ethiopic(engine) > 200
    assert "You are DSDMA" not in engine and "AGENT'S DOMAIN KNOWLEDGE" not in engine


@pytest.mark.asyncio
async def test_the_template_domain_knowledge_rides_verbatim_with_the_agent_profile_source(env_en: None) -> None:
    seen = await _ally_dsdma_am()
    (knowledge,) = _segments(seen, "sys:domain_knowledge")
    assert knowledge.source == SegmentSource.AGENT_PROFILE
    assert _span(seen, knowledge) == seen["knowledge"]
    # Only the template's own text is agent_profile: the engine header around it stays engine.
    assert {r.source for r in _segments(seen, "instr:system:")} == {SegmentSource.ENGINE}


@pytest.mark.asyncio
async def test_a_custom_dsdma_template_is_added_after_the_engine_header_not_in_its_place(env_en: None) -> None:
    custom = "Custom Ally framing for {domain_name}. Rules: {rules_summary_str}"
    seen = await _ally_dsdma_am(prompt_template=custom)
    engine = "".join(_span(seen, r) for r in _segments(seen, "instr:system"))
    assert _ethiopic(engine) > 200  # the localized engine header still renders
    pieces = _segments(seen, "instr:agent_template")
    assert pieces and {r.source for r in pieces} == {SegmentSource.AGENT_PROFILE}
    assert _span(seen, pieces[0]) == "Custom Ally framing for Ally. Rules: "
    (header,) = _segments(seen, "instr:system:0")
    assert header.message_index == pieces[0].message_index and header.span_end < pieces[0].span_start


def _aspdma(overrides: Any) -> Any:
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from tests.ciris_engine.logic.dma.compose_golden import pin_aspdma_context_builder

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry, prompt_overrides=overrides)
    pin_aspdma_context_builder(dma)
    return dma


async def _aspdma_seen(overrides: Any) -> Dict[str, Any]:
    from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
    from ciris_engine.schemas.dma.results import ASPDMALLMResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType
    from tests.ciris_engine.logic.dma.compose_golden import make_ethical_result

    dma = _aspdma(overrides)
    task, item = _thought_from_message("en", tag="ally-aspdma")
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = _recording_llm(
        captured, ASPDMALLMResult(selected_action=HandlerActionType.SPEAK, reasoning="ok", speak_content="ok")
    )
    seen = _capturing(dma)
    await dma.evaluate(
        EnhancedDMAInputs(
            original_thought=item,
            processing_context=_processing_context(task),
            ethical_pdma_result=make_ethical_result(),
            csdma_result=make_csdma_result(),
            dsdma_result=make_dsdma_result(),
            permitted_actions=[HandlerActionType.SPEAK, HandlerActionType.TASK_COMPLETE],
        )
    )
    return seen


@pytest.mark.asyncio
async def test_aspdma_template_header_and_framing_carry_the_agent_profile_source(env_en: None) -> None:
    ally = _template("default")["action_selection_pdma_overrides"]
    seen = await _aspdma_seen(ally)
    (header,) = _segments(seen, "instr:system")[:1]
    assert header.segment_id == "instr:system" and header.source == SegmentSource.AGENT_PROFILE
    assert _span(seen, header) == ally["system_header"]
    framing = [r for r in _segments(seen, "instr:framing")]
    assert framing and {r.source for r in framing} == {SegmentSource.AGENT_PROFILE}
    (request,) = _segments(seen, "request:framing")
    assert request.source == SegmentSource.USER_INPUT
    # The engine-owned fields after it stay engine.
    assert {r.source for r in _segments(seen, "instr:system:")} == {SegmentSource.ENGINE}


@pytest.mark.asyncio
async def test_aspdma_engine_header_stays_engine(env_en: None) -> None:
    seen = await _aspdma_seen(None)
    (header,) = [r for r in _segments(seen, "instr:system") if r.segment_id == "instr:system"]
    assert header.source == SegmentSource.ENGINE
    assert not _segments(seen, "instr:framing")


async def _csdma_seen(overrides: Any) -> Dict[str, Any]:
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    dma = CSDMAEvaluator(service_registry=Mock(), prompt_overrides=overrides)
    task, item = _thought_from_message("en", tag="ally-csdma")
    captured: Dict[str, Any] = {}
    dma.fetch_original_task = AsyncMock(return_value=task)
    dma.call_llm_structured = _recording_llm(captured, make_csdma_result())
    seen = _capturing(dma)
    await dma.evaluate(item, _processing_context(task))
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("template", ["default", "he-300-benchmark"])
async def test_csdma_template_overrides_carry_the_agent_profile_source(env_en: None, template: str) -> None:
    overrides = _template(template)["csdma_overrides"]
    seen = await _csdma_seen(overrides)
    framing = _segments(seen, "instr:framing")
    assert framing and {r.source for r in framing} == {SegmentSource.AGENT_PROFILE}
    assert {r.source for r in _segments(seen, "instr:user")} == {SegmentSource.ENGINE}
    prompts = _segments(seen, "sys:template_system_prompt")
    if "system_prompt" in overrides:
        (prompt,) = prompts
        assert prompt.source == SegmentSource.AGENT_PROFILE and _span(seen, prompt) == overrides["system_prompt"]
    else:
        assert not prompts
    assert {r.source for r in _segments(seen, "instr:system")} == {SegmentSource.ENGINE}
