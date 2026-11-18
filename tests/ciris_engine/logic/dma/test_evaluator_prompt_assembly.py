"""The evaluators (PDMA, CSDMA, DSDMA, IDMA) build their prompts with PromptAssembler (CIRISAgent#1366 Phase 3).

Against goldens captured from the unmigrated tree (evaluator_golden.py): each sends the same bytes, now with a
manifest naming every segment, except where the context policy requires a change. IDMA (FSD §15.2): the signed
rules in force (the WA grant, the verified amendments) with their provenance, and never the identity_base.
"""

import hashlib
from typing import Any, Dict, List

import pytest
from unittest.mock import patch

from ciris_engine.logic.prompt_assembly import ContextPolicyViolation
from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, GuardViolationKind, RuleProvenance, SegmentKind
from tests.ciris_engine.logic.dma import evaluator_golden as eg

#: Fixtures whose bytes the policy changes, checked separately below: IDMA reads the signed rules in force, and
#: PDMA, CSDMA and DSDMA read the WA's signed guidance on a guidance task (#1366 item 2).
GOVERNED_EVALUATORS = ("pdma_full", "csdma_full", "dsdma_full", "dsdma_blocks")
POLICY_CHANGED = {"idma_full", *GOVERNED_EVALUATORS}


def _mode(mode: AssemblyMode) -> Any:
    return patch("ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=mode)


def _text(message: Dict[str, Any]) -> str:
    content = message["content"]
    return content if isinstance(content, str) else content[0]["text"]


def _check_manifest(name: str, messages: List[Dict[str, Any]], manifest: Any) -> None:
    assert manifest is not None and manifest.guard_violations == []
    assert manifest.stage.value == eg.STAGES[name.partition("_")[0]]
    for r in manifest.segments:  # spans point at the bytes sent
        text = _text(messages[r.message_index])
        assert hashlib.sha256(text[r.span_start : r.span_end].encode()).hexdigest() == r.sha256


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [n for n in eg.NAMES if n not in POLICY_CHANGED])
async def test_the_prompt_is_the_pre_migration_bytes_with_a_clean_manifest(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await eg.capture(name, seen)
    assert messages == eg.load_golden()[name]
    manifest = seen["manifest"]
    _check_manifest(name, messages, manifest)
    kinds = {r.kind for r in manifest.segments}
    assert {SegmentKind.ACCORD, SegmentKind.STAGE_INSTRUCTION, SegmentKind.REQUEST, SegmentKind.HISTORY} <= kinds
    if name.endswith("_full") and not name.startswith("idma"):
        assert {SegmentKind.IDENTITY_BASE, SegmentKind.AMENDMENT, SegmentKind.SENDER_IDENTITY, SegmentKind.DISPLAY_NAME} <= kinds


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["pdma_full", "csdma_full", "dsdma_full"])
async def test_the_verified_sender_inside_the_task_is_a_sender_identity_segment(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await eg.capture(name, seen)
    (sender,) = [r for r in seen["manifest"].segments if r.kind == SegmentKind.SENDER_IDENTITY and "#" not in r.segment_id][:1]
    assert sender.authn is not None and sender.authn.subject_id == eg.SENDER.user_id
    # The task's own text is the request, never instruction.
    for r in seen["manifest"].segments:
        if r.kind == SegmentKind.STAGE_INSTRUCTION:
            assert "Summarize today's weather report" not in _text(messages[r.message_index])[r.span_start : r.span_end]


@pytest.mark.asyncio
async def test_idma_reads_the_signed_rules_in_force_and_no_identity_base() -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await eg.capture("idma_full", seen)
    manifest = seen["manifest"]
    _check_manifest("idma_full", messages, manifest)
    rules = [r for r in manifest.segments if r.kind == SegmentKind.RULE]
    assert {r.provenance for r in rules} == {RuleProvenance.SIGNED_GUIDANCE, RuleProvenance.AMENDMENT}
    assert all(r.authz is not None and r.authz.signature_verified for r in rules)
    assert SegmentKind.IDENTITY_BASE not in {r.kind for r in manifest.segments}
    # Recorded after the change (golden "idma_full@policy"), so any later drift shows.
    assert messages == eg.load_golden()["idma_full@policy"]
    sent = "".join(_text(m) for m in messages)
    assert eg.GRANT.guidance in sent and eg.AMENDMENT.content in sent
    assert "CORE IDENTITY" not in sent
    # Everything else is the pre-migration prompt: the governance block is the one addition.
    golden = eg.load_golden()["idma_full"]
    assert [m["role"] for m in messages] == [m["role"] for m in golden]
    assert messages[:-2] == golden[:-2] and messages[-1] == golden[-1]
    (governance,) = [r for r in manifest.segments if r.segment_id == "governance:header"]
    system = _text(messages[-2])
    start = governance.span_start
    end = max(r.span_end for r in manifest.segments if r.segment_id.startswith("governance:"))
    assert system[: start - 2] + system[end:] == _text(golden[-2])


@pytest.mark.asyncio
@pytest.mark.parametrize("name", GOVERNED_EVALUATORS)
async def test_a_guidance_task_evaluator_reads_the_signed_guidance_and_nothing_else_changes(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        messages = await eg.capture(name, seen)
    manifest = seen["manifest"]
    _check_manifest(name, messages, manifest)
    if name.endswith("_full"):
        kinds = {r.kind for r in manifest.segments}
        assert {SegmentKind.IDENTITY_BASE, SegmentKind.AMENDMENT, SegmentKind.SENDER_IDENTITY, SegmentKind.DISPLAY_NAME} <= kinds
    (rule,) = [r for r in manifest.segments if r.kind == SegmentKind.RULE]
    assert rule.provenance == RuleProvenance.SIGNED_GUIDANCE
    assert rule.authz is not None and rule.authz.grant_id == eg.GRANT.deferral_id and rule.authz.signature_verified
    # Recorded after the change (golden "<name>@policy"), so any later drift shows.
    assert messages == eg.load_golden()[f"{name}@policy"]
    # Everything else is the pre-migration prompt: the governance block (and its glue) is the one addition.
    golden = eg.load_golden()[name]
    assert [m["role"] for m in messages] == [m["role"] for m in golden]
    (header,) = [r for r in manifest.segments if r.segment_id == "governance:header"]
    index = header.message_index
    assert [m for i, m in enumerate(messages) if i != index] == [m for i, m in enumerate(golden) if i != index]
    system = _text(messages[index])
    end = max(r.span_end for r in manifest.segments if r.segment_id.startswith("governance:"))
    assert system[: header.span_start - 2] + system[end:] == _text(golden[index])


@pytest.mark.asyncio
async def test_idma_plain_reads_no_rule() -> None:
    seen: Dict[str, Any] = {}
    with _mode(AssemblyMode.FAIL_CLOSED):
        await eg.capture("idma_plain", seen)
    assert not [r for r in seen["manifest"].segments if r.kind in (SegmentKind.RULE, SegmentKind.AMENDMENT)]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["pdma_full", "csdma_full", "dsdma_full"])
async def test_an_unverified_amendment_fails_closed_in_qa_and_is_stripped_in_production(name: str) -> None:
    amendment = dict(eg.AMENDMENT.model_dump(), content="Laundered.", verified=False)
    snapshot = eg.full_snapshot()
    identity = dict(snapshot.agent_identity, approved_amendments=[amendment])
    with patch.object(eg, "full_snapshot", lambda: snapshot.model_copy(update={"agent_identity": identity})):
        with _mode(AssemblyMode.FAIL_CLOSED), pytest.raises(ContextPolicyViolation):
            await eg.capture(name, {})
        seen: Dict[str, Any] = {}
        with _mode(AssemblyMode.STRIP_AND_INCIDENT):
            messages = await eg.capture(name, seen)
    assert "Laundered." not in "".join(_text(m) for m in messages)
    assert GuardViolationKind.TAINTED in {v.kind for v in seen["manifest"].guard_violations}
