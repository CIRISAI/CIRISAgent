"""The memory second passes build their prompts with PromptAssembler (CIRISAgent#1366 Phase 3; FSD §6).

Against goldens captured from the unmigrated tree (msaspdma_golden.py): MSASPDMA, RSASPDMA and FSASPDMA send the
same bytes, now with a manifest naming every segment. The verified WA grant is a ``wa_guidance`` segment with its
authz; the conscience's veto on a retry is a ``conscience_feedback`` segment carrying its veto id; ASPDMA's
reasoning and proposed node are its output, never instruction text; the candidate nodes (display names included)
are untrusted history.
"""

import hashlib
from typing import Any, Dict
from unittest.mock import patch

import pytest

from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, SegmentKind, TrustLevel
from tests.ciris_engine.logic.dma import msaspdma_golden as mg

SITES = ("msaspdma", "rsaspdma")
ALL = [(site, name) for site in SITES for name in mg.NAMES[site]]


def _mode(mode: AssemblyMode) -> Any:
    return patch("ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=mode)


@pytest.mark.asyncio
@pytest.mark.parametrize("site,name", ALL)
async def test_the_prompt_is_the_pre_migration_bytes_with_a_clean_manifest(site: str, name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await mg.capture(name, seen)
    assert messages == mg.load_golden(site)[name]
    manifest = seen["manifest"]
    assert manifest is not None and manifest.guard_violations == [] and manifest.stage.value == site
    for r in manifest.segments:  # spans point at the bytes sent
        content = messages[r.message_index]["content"]
        assert hashlib.sha256(content[r.span_start : r.span_end].encode()).hexdigest() == r.sha256
    kinds = {r.kind for r in manifest.segments}
    assert {SegmentKind.ACCORD, SegmentKind.STAGE_INSTRUCTION, SegmentKind.REQUEST, SegmentKind.DMA_OUTPUT} <= kinds
    if name.endswith("full"):
        assert {SegmentKind.SENDER_IDENTITY, SegmentKind.DISPLAY_NAME, SegmentKind.HISTORY} <= kinds
        assert manifest.retry_index == 1
        (fb,) = [r for r in manifest.segments if r.kind == SegmentKind.CONSCIENCE_FEEDBACK]
        assert fb.acct is not None and fb.acct.veto_id == "veto-golden-1"
    else:
        assert manifest.retry_index == 0 and SegmentKind.CONSCIENCE_FEEDBACK not in kinds


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["ms_full"])
async def test_the_verified_grant_is_wa_guidance_with_its_authz(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        await mg.capture(name, seen)
    (grant,) = [r for r in seen["manifest"].segments if r.kind == SegmentKind.WA_GUIDANCE]
    assert grant.authz is not None and grant.authz.grant_id == mg.GRANT.deferral_id and grant.authz.signature_verified
    assert grant.trust == TrustLevel.VERIFIED


@pytest.mark.asyncio
async def test_aspdma_output_and_candidates_are_never_instruction_text() -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await mg.capture("ms_addressed_full", seen)
    manifest = seen["manifest"]
    proposed = [r for r in manifest.segments if r.segment_id.startswith("slot:proposed_")]
    assert proposed and all(r.kind == SegmentKind.DMA_OUTPUT and r.trust == TrustLevel.UNTRUSTED for r in proposed)
    (candidates,) = [r for r in manifest.segments if r.segment_id == "candidate_nodes"]
    assert candidates.kind == SegmentKind.HISTORY and candidates.trust == TrustLevel.UNTRUSTED
    for r in manifest.segments:
        if r.kind == SegmentKind.STAGE_INSTRUCTION:
            text = messages[r.message_index]["content"][r.span_start : r.span_end]
            assert "user/wa-user-0eve" not in text and "eve the admin" not in text
