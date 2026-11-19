"""The pipeline-position paragraph is its own segment at every stage, in every language (CIRISAgent#1366 item 12).

Each stage's English template carries a top-level ``pipeline_position`` field: where the stage sits and what it
cannot see. The call site hands that field in as a ``pipeline_position`` segment (system trust, standing, engine
source) between the field it used to sit inside and the rest of that field (``*_tail``), so the English bytes are
unchanged (the goldens replay byte for byte).

It used to be carved out of the rendered ``stage_instruction`` by matching its English heading, so a translated
template (which translates the heading) got no segment and its manifest misdescribed the call. Here every stage is
checked in English, under a template whose paragraph is translated, and against an agent-template override.
"""

import hashlib
import re
from contextlib import ExitStack
from typing import Any, Awaitable, Callable, Dict, List, Tuple
from unittest.mock import patch

import pytest
import yaml

from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader, ConsciencePrompts
from ciris_engine.logic.dma.base_dma import BaseDMA
from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader
from ciris_engine.logic.prompt_assembly import assembler as assembler_module
from ciris_engine.logic.prompt_assembly.assembler import PromptAssembler
from ciris_engine.schemas.context.prompt_provenance import (
    AssemblyMode,
    Lifecycle,
    PromptStage,
    SegmentKind,
    SegmentSource,
    TrustLevel,
)
from ciris_engine.schemas.dma.prompts import PromptCollection
from tests.ciris_engine.logic.conscience import conscience_golden as kg
from tests.ciris_engine.logic.dma import aspdma_golden as ag
from tests.ciris_engine.logic.dma import evaluator_golden as eg
from tests.ciris_engine.logic.dma import msaspdma_golden as mg
from tests.ciris_engine.logic.dma import tsaspdma_golden as tg
from tests.fixtures.synthetic_locale import CONSCIENCE_PROMPTS, DMA_PROMPTS, prompts_dir_without_field

_HEADING = re.compile(r"pipeline position", re.IGNORECASE)


async def _conscience(name: str) -> None:
    await kg.capture(name, "plain")


CAPTURES: Dict[PromptStage, Callable[[], Awaitable[Any]]] = {
    PromptStage.PDMA: lambda: eg.capture("pdma_plain"),
    PromptStage.CSDMA: lambda: eg.capture("csdma_plain"),
    PromptStage.DSDMA: lambda: eg.capture("dsdma_plain"),
    PromptStage.IDMA: lambda: eg.capture("idma_plain"),
    PromptStage.ASPDMA: lambda: ag.capture("first_pass"),
    PromptStage.TSASPDMA: lambda: tg.capture("tool_plain"),
    PromptStage.MSASPDMA: lambda: mg.capture("ms_plain"),
    PromptStage.RSASPDMA: lambda: mg.capture("rs_plain"),
    PromptStage.FSASPDMA: lambda: mg.capture("fs_plain"),
    PromptStage.DSASPDMA: lambda: mg.capture("ds_plain"),
    PromptStage.COHERENCE: lambda: _conscience("coherence"),
    PromptStage.EPISTEMIC: lambda: _conscience("epistemic"),
    PromptStage.ENTROPY: lambda: _conscience("entropy"),
    PromptStage.OPTVETO: lambda: _conscience("optveto"),
}

#: Each stage's template: (loader family, template name).
TEMPLATES: Dict[PromptStage, Tuple[str, str]] = {
    PromptStage.PDMA: ("dma", "pdma_ethical"),
    PromptStage.CSDMA: ("dma", "csdma_common_sense"),
    PromptStage.DSDMA: ("dma", "dsdma_base"),
    PromptStage.IDMA: ("dma", "idma"),
    PromptStage.ASPDMA: ("dma", "action_selection_pdma"),
    PromptStage.TSASPDMA: ("dma", "tsaspdma"),
    PromptStage.MSASPDMA: ("dma", "msaspdma"),
    PromptStage.RSASPDMA: ("dma", "rsaspdma"),
    PromptStage.FSASPDMA: ("dma", "fsaspdma"),
    PromptStage.DSASPDMA: ("dma", "dsaspdma"),
    PromptStage.COHERENCE: ("conscience", "coherence_conscience"),
    PromptStage.EPISTEMIC: ("conscience", "epistemic_humility_conscience"),
    PromptStage.ENTROPY: ("conscience", "entropy_conscience"),
    PromptStage.OPTVETO: ("conscience", "optimization_veto_conscience"),
}

#: A translated paragraph, heading included: what a localized template will carry. Nothing parses it.
TRANSLATED = "POSICIÓN EN LA CADENA ({name}): esta etapa corre en su sitio; no ve lo que no se le muestra."

#: What an agent template's override would put under the field's name, if anything read it from there.
OVERRIDE = "OVERRIDDEN POSITION — must never reach a prompt"


def test_every_stage_is_covered() -> None:
    assert set(CAPTURES) == set(PromptStage) == set(TEMPLATES)


def _english_field(stage: PromptStage) -> str:
    family, name = TEMPLATES[stage]
    if family == "dma":
        text = DMAPromptLoader(language="en").load_prompt_template(name).pipeline_position
    else:
        text = ConsciencePromptLoader(language="en").load_prompts(name).pipeline_position
    assert text, f"{name}: no pipeline_position field"
    return text


def _text(message: Any) -> str:
    content = message.content
    return content if isinstance(content, str) else content[0].text


async def _built(stage: PromptStage, *patches: Any) -> List[Tuple[List[Any], Any]]:
    """Every (messages, manifest) the assembler built while the stage's call site ran."""
    built: List[Tuple[List[Any], Any]] = []
    original = PromptAssembler.build

    def spy(self: PromptAssembler, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        built.append(result)
        return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(PromptAssembler, "build", spy))
        stack.enter_context(
            patch.object(assembler_module, "current_guard_mode", return_value=AssemblyMode.FAIL_CLOSED)
        )
        for p in patches:
            stack.enter_context(p)
        await CAPTURES[stage]()
    return [b for b in built if b[1].stage == stage]


def _assert_one_position_over(calls: List[Tuple[List[Any], Any]], stage: PromptStage, expected: str) -> None:
    assert calls, f"no {stage.value} call was assembled"
    for messages, manifest in calls:
        assert manifest.guard_violations == []
        positions = [r for r in manifest.segments if r.kind == SegmentKind.PIPELINE_POSITION]
        assert len(positions) == 1, [(r.segment_id, r.kind.value) for r in manifest.segments]
        record = positions[0]
        assert record.trust == TrustLevel.SYSTEM
        assert record.source == SegmentSource.ENGINE
        assert record.lifecycle == Lifecycle.STANDING
        body = _text(messages[record.message_index])[record.span_start : record.span_end]
        assert hashlib.sha256(body.encode()).hexdigest() == record.sha256
        # The span covers exactly the field's text.
        assert body == expected
        # ... and the paragraph is not (also) described as stage_instruction bytes.
        for r in manifest.segments:
            if r.kind == SegmentKind.STAGE_INSTRUCTION:
                text = _text(messages[r.message_index])[r.span_start : r.span_end]
                assert expected not in text, r.segment_id
                assert not _HEADING.search(text), r.segment_id


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
async def test_english_the_manifest_carries_one_pipeline_position_segment_over_the_field(stage: PromptStage) -> None:
    _assert_one_position_over(await _built(stage), stage, _english_field(stage))


def _translated_dma(real: Callable[..., PromptCollection]) -> Callable[..., PromptCollection]:
    def load(self: DMAPromptLoader, template_name: str) -> PromptCollection:
        collection = real(self, template_name)
        if not collection.pipeline_position:
            return collection
        return collection.model_copy(update={"pipeline_position": TRANSLATED.format(name=template_name)})

    return load


def _translated_conscience(real: Callable[..., ConsciencePrompts]) -> Callable[..., ConsciencePrompts]:
    def load(self: ConsciencePromptLoader, conscience_type: str) -> ConsciencePrompts:
        prompts = real(self, conscience_type)
        if not prompts.pipeline_position:
            return prompts
        return prompts.model_copy(update={"pipeline_position": TRANSLATED.format(name=conscience_type)})

    return load


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
async def test_a_translated_paragraph_is_still_one_segment_over_the_field(stage: PromptStage) -> None:
    """A template whose paragraph (heading included) is translated: the segment is found by field, not by words."""
    calls = await _built(
        stage,
        patch.object(DMAPromptLoader, "load_prompt_template", _translated_dma(DMAPromptLoader.load_prompt_template)),
        patch.object(ConsciencePromptLoader, "load_prompts", _translated_conscience(ConsciencePromptLoader.load_prompts)),
    )
    _assert_one_position_over(calls, stage, TRANSLATED.format(name=TEMPLATES[stage][1]))


def _overridden(real: Callable[..., None]) -> Callable[..., None]:
    """Every DMA's agent-template overrides also name ``pipeline_position``."""

    def load(self: BaseDMA, overrides: Any = None) -> None:
        real(self, overrides)
        if isinstance(self.prompts, PromptCollection):
            self.prompts = self.prompts.model_copy(update={"pipeline_position": OVERRIDE})
        else:
            self.prompts = {**self.prompts, "pipeline_position": OVERRIDE}

    return load


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
async def test_no_template_override_can_replace_the_paragraph(stage: PromptStage) -> None:
    """Read from the engine template, never from an agent template's overrides (the consciences take none)."""
    calls = await _built(stage, patch.object(BaseDMA, "_load_prompts", _overridden(BaseDMA._load_prompts)))
    _assert_one_position_over(calls, stage, _english_field(stage))
    for messages, _ in calls:
        assert not any(OVERRIDE in _text(m) for m in messages)


def test_the_csdma_header_override_replaces_the_header_never_the_position() -> None:
    """CSDMA's ``system_prompt`` replaces its header (both header fields), as before; the position stays."""
    from unittest.mock import Mock

    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    dma = CSDMAEvaluator(service_registry=Mock(), prompt_overrides={"system_prompt": "PERSONA HEADER."})
    english = DMAPromptLoader(language="en").load_prompt_template("csdma_common_sense")
    text = dma._system_message_text("summary", "thought")
    assert text.startswith("PERSONA HEADER.\n\n" + str(english.pipeline_position) + "\n\n")
    assert str(english.system_guidance_header_tail) not in text


LANGUAGES = ["es", "am", "ar", "zh", "yo"]


def _position(stage: PromptStage, language: str, prompts_dir: Any = None) -> str:
    family, name = TEMPLATES[stage]
    root = None if prompts_dir is None else str(prompts_dir)
    if family == "dma":
        return DMAPromptLoader(prompts_dir=root, language=language).pipeline_position(name)
    _, position, _ = ConsciencePromptLoader(prompts_dir=root, language=language).get_system_prompt_parts(name)
    return position


def _shipped_locale_field(stage: PromptStage, language: str) -> Any:
    """The field as the shipped locale file carries it (None: no file, or no such field)."""
    family, name = TEMPLATES[stage]
    source = DMA_PROMPTS if family == "dma" else CONSCIENCE_PROMPTS
    path = source / "localized" / language / f"{name}.yml"
    if not path.exists():
        return None
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("pipeline_position")


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
def test_a_locale_without_the_field_gets_the_english_paragraph(stage: PromptStage, language: str, tmp_path: Any) -> None:
    """A locale copy lacking the field falls back to the English one, field by field.

    Synthetic: the shipped translation with ``pipeline_position`` removed, so the fallback is exercised however
    far the i18n lane has translated the field.
    """
    family, name = TEMPLATES[stage]
    source = DMA_PROMPTS if family == "dma" else CONSCIENCE_PROMPTS
    synthetic = prompts_dir_without_field(source, tmp_path / "prompts", language, "pipeline_position")
    if (synthetic / "localized" / language / f"{name}.yml").exists():
        # The premise: the locale's own copy is loaded, and it lacks the field.
        if family == "dma":
            loaded = DMAPromptLoader(prompts_dir=str(synthetic), language=language).load_prompt_template(name)
        else:
            loaded = ConsciencePromptLoader(prompts_dir=str(synthetic), language=language).load_prompts(name)
        assert loaded.pipeline_position is None
    # Else no localized copy of this template ships: the English template loads whole, field included.
    assert _position(stage, language, synthetic) == _english_field(stage)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
def test_a_locale_that_translates_the_field_renders_its_own(stage: PromptStage, language: str) -> None:
    """Where the shipped locale carries a translated paragraph, that is what renders, not the English one."""
    own = _shipped_locale_field(stage, language)
    if own is None:
        # No translation shipped (e.g. a conscience with no localized copy): English is the correct answer.
        assert _position(stage, language) == _english_field(stage)
        return
    assert own != _english_field(stage), f"{language}/{TEMPLATES[stage][1]}: the 'translation' is the English text"
    assert _position(stage, language) == own
