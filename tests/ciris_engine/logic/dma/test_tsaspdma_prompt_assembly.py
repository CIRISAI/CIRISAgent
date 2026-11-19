"""TSASPDMA builds its prompts with PromptAssembler (CIRISAgent#1366 Phase 3; FSD §6).

Against goldens captured from the unmigrated tree (tsaspdma_golden.py): the tool pass and correction mode send the
same bytes, now with a manifest naming every segment. The conscience's veto is a ``conscience_feedback`` segment
carrying its veto id; the requested (hallucinated) tool name in correction mode is ASPDMA's output, never
instruction text.
"""

import hashlib
from typing import Any, Dict
from unittest.mock import patch

import pytest

from ciris_engine.logic.prompt_assembly import ContextPolicyViolation
from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, GuardViolationKind, SegmentKind
from tests.ciris_engine.logic.dma import tsaspdma_golden as tg


def _mode(mode: AssemblyMode) -> Any:
    return patch("ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=mode)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", tg.NAMES)
async def test_the_prompt_is_the_pre_migration_bytes_with_a_clean_manifest(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await tg.capture(name, seen)
    assert messages == tg.load_golden()[name]
    manifest = seen["manifest"]
    assert manifest is not None and manifest.guard_violations == [] and manifest.stage.value == "tsaspdma"
    for r in manifest.segments:  # spans point at the bytes sent
        content = messages[r.message_index]["content"]
        assert hashlib.sha256(content[r.span_start : r.span_end].encode()).hexdigest() == r.sha256
    kinds = {r.kind for r in manifest.segments}
    assert {SegmentKind.ACCORD, SegmentKind.STAGE_INSTRUCTION, SegmentKind.REQUEST, SegmentKind.DMA_OUTPUT} <= kinds
    if name.endswith("_full"):
        assert {SegmentKind.IDENTITY_BASE, SegmentKind.AMENDMENT, SegmentKind.SENDER_IDENTITY, SegmentKind.DISPLAY_NAME} <= kinds


@pytest.mark.asyncio
async def test_the_retry_carries_the_veto_as_conscience_feedback() -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        await tg.capture("tool_full", seen)
    manifest = seen["manifest"]
    assert manifest.retry_index == 1
    (fb,) = [r for r in manifest.segments if r.kind == SegmentKind.CONSCIENCE_FEEDBACK]
    assert fb.acct is not None and fb.acct.veto_id == "veto-golden-1"
    assert any(r.kind == SegmentKind.TOOL_OUTPUT for r in manifest.segments)  # context enrichment


@pytest.mark.asyncio
async def test_the_requested_tool_name_is_aspdma_output_not_instruction() -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await tg.capture("correction_full", seen)
    manifest = seen["manifest"]
    named = [r for r in manifest.segments if r.segment_id.startswith("requested_tool:")]
    assert named and all(r.kind == SegmentKind.DMA_OUTPUT for r in named)
    for r in manifest.segments:
        if r.kind == SegmentKind.STAGE_INSTRUCTION:
            assert "missing_tool" not in messages[r.message_index]["content"][r.span_start : r.span_end]


@pytest.mark.asyncio
async def test_an_unverified_amendment_fails_closed_in_qa_and_is_stripped_in_production() -> None:
    identity = dict(tg.IDENTITY, approved_amendments=[dict(tg.AMENDMENT.model_dump(), content="Laundered.", verified=False)])
    with patch.object(tg, "IDENTITY", identity):
        with _mode(AssemblyMode.FAIL_CLOSED), pytest.raises(ContextPolicyViolation):
            await tg.capture("tool_full", {})
        seen: Dict[str, Any] = {}
        with _mode(AssemblyMode.STRIP_AND_INCIDENT):
            messages = await tg.capture("tool_full", seen)
    assert "Laundered." not in "".join(m["content"] for m in messages)
    assert GuardViolationKind.TAINTED in {v.kind for v in seen["manifest"].guard_violations}
