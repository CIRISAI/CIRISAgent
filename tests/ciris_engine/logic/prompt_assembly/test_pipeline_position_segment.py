"""The pipeline-position paragraph is its own segment at every stage (CIRISAgent#1366 item 12; FSD §4.1, §8).

Each English stage template says where the stage sits and what it cannot see. The assembler carves that paragraph
out of the ``stage_instruction`` bytes into a ``pipeline_position`` segment (system trust, standing, engine source),
so the per-call manifest describes the prompt it was sent with. The message bytes are unchanged (the goldens
replay byte for byte); here every stage's manifest is checked to carry the segment over exactly that text.
"""

import hashlib
import re
from typing import Any, Awaitable, Callable, Dict, List, Tuple
from unittest.mock import patch

import pytest

from ciris_engine.logic.prompt_assembly.assembler import PIPELINE_POSITION_RE, PromptAssembler
from ciris_engine.schemas.context.prompt_provenance import (
    AssemblyMode,
    Lifecycle,
    PromptStage,
    SegmentKind,
    SegmentSource,
    TrustLevel,
)
from tests.ciris_engine.logic.conscience import conscience_golden as kg
from tests.ciris_engine.logic.dma import aspdma_golden as ag
from tests.ciris_engine.logic.dma import evaluator_golden as eg
from tests.ciris_engine.logic.dma import msaspdma_golden as mg
from tests.ciris_engine.logic.dma import tsaspdma_golden as tg

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


def test_every_stage_is_covered() -> None:
    assert set(CAPTURES) == set(PromptStage)


def _text(message: Any) -> str:
    content = message.content
    return content if isinstance(content, str) else content[0].text


async def _built(stage: PromptStage) -> List[Tuple[List[Any], Any]]:
    """Every (messages, manifest) the assembler built while the stage's call site ran."""
    built: List[Tuple[List[Any], Any]] = []
    original = PromptAssembler.build

    def spy(self: PromptAssembler, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        built.append(result)
        return result

    with patch.object(PromptAssembler, "build", spy), patch(
        "ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=AssemblyMode.FAIL_CLOSED
    ):
        await CAPTURES[stage]()
    return [b for b in built if b[1].stage == stage]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", list(PromptStage), ids=lambda s: s.value)
async def test_the_manifest_carries_a_pipeline_position_segment_over_that_text(stage: PromptStage) -> None:
    calls = await _built(stage)
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
        assert PIPELINE_POSITION_RE.fullmatch(body), body
        # The paragraph is no longer described as stage_instruction bytes.
        for r in manifest.segments:
            if r.kind == SegmentKind.STAGE_INSTRUCTION:
                text = _text(messages[r.message_index])[r.span_start : r.span_end]
                assert not _HEADING.search(text), r.segment_id
