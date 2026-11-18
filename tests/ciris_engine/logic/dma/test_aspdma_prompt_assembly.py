"""ASPDMA builds its prompt with PromptAssembler (CIRISAgent#1366 Phase 3; FSD §6).

Against goldens captured from the unmigrated tree (aspdma_golden.py): every fixture sends the same bytes, now
with a manifest naming each segment. On a conscience retry the veto is a ``conscience_feedback`` segment with its
veto id (required on every retry, #1366 item 1); a verified WA grant is a ``wa_guidance`` segment carrying its
authz; each approved amendment is its own segment; the image rides after the text.
"""

import hashlib
from typing import Any
from unittest.mock import patch

import pytest

from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, SegmentKind
from tests.ciris_engine.logic.dma import aspdma_golden as ag


def _qa() -> Any:
    return patch(
        "ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=AssemblyMode.FAIL_CLOSED
    )


def _text(content: Any) -> str:
    return content if isinstance(content, str) else content[0]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(ag.CAPTURES))
async def test_the_prompt_is_the_pre_migration_bytes_with_a_clean_manifest(name: str) -> None:
    with _qa():
        messages = await ag.capture(name)
    assert messages == ag.load_golden()[name]
    manifest = ag.LAST["manifest"]
    assert manifest is not None and manifest.stage.value == "aspdma" and manifest.guard_violations == []
    for r in manifest.segments:
        content = _text(messages[r.message_index]["content"])
        assert hashlib.sha256(content[r.span_start : r.span_end].encode()).hexdigest() == r.sha256
    kinds = {r.kind for r in manifest.segments}
    assert {SegmentKind.ACCORD, SegmentKind.IDENTITY_BASE, SegmentKind.REQUEST, SegmentKind.DMA_OUTPUT} <= kinds
    retry = name.startswith("retry")
    assert (manifest.retry_index > 0) is retry
    assert (SegmentKind.CONSCIENCE_FEEDBACK in kinds) is retry


@pytest.mark.asyncio
async def test_the_retry_veto_and_the_governed_carriers() -> None:
    with _qa():
        await ag.capture("retry")
    (fb,) = [r for r in ag.LAST["manifest"].segments if r.kind == SegmentKind.CONSCIENCE_FEEDBACK]
    assert fb.acct is not None
    with _qa():
        messages = await ag.capture("governed")
    segments = ag.LAST["manifest"].segments
    (grant,) = [r for r in segments if r.kind == SegmentKind.WA_GUIDANCE]
    assert grant.authz is not None and grant.authz.grant_id == ag.GRANT.deferral_id and grant.authz.signature_verified
    (amendment,) = [r for r in segments if r.kind == SegmentKind.AMENDMENT]
    assert amendment.authz is not None and amendment.authz.grant_id == ag.AMENDMENT.node_id
    assert messages[-1]["content"][1]["type"] == "image_url"  # the image after the text block
