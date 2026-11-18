"""Every byte a stage is sent is accounted for by a typed segment (CIRISAgent#1366; FSD/PROMPT_CONTEXT_PROVENANCE.md §6, §8).

1. ASPDMA renders the VERIFIED SENDER block inside its original-task block: the manifest records it as a
   ``sender_identity`` segment and the self-chosen name as a ``display_name`` segment, as the other DMAs do.
2. A guidance task (a Wise Authority resolved a deferral; its signed guidance is in force): every DMA and the
   memorize second pass carry the guidance as a ``rule`` segment with provenance ``signed_guidance`` and the
   grant's authz; MSASPDMA also carries the agent's identity.
"""

import hashlib
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest

from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, RuleProvenance, SegmentKind, TrustLevel
from ciris_engine.schemas.runtime.models import TaskContext
from tests.ciris_engine.logic.dma import compose_golden as cg
from tests.ciris_engine.logic.dma import evaluator_golden as eg
from tests.ciris_engine.logic.dma import msaspdma_golden as mg


def _qa() -> Any:
    return patch(
        "ciris_engine.logic.prompt_assembly.assembler.current_guard_mode", return_value=AssemblyMode.FAIL_CLOSED
    )


def _text(message: Dict[str, Any]) -> str:
    content = message["content"]
    return content if isinstance(content, str) else content[0]["text"]


def _spans_hash(messages: List[Dict[str, Any]], manifest: Any) -> None:
    assert manifest is not None and manifest.guard_violations == []
    for r in manifest.segments:
        text = _text(messages[r.message_index])
        assert hashlib.sha256(text[r.span_start : r.span_end].encode()).hexdigest() == r.sha256


async def _aspdma_with_sender() -> "tuple[List[Dict[str, Any]], Any]":
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.dma.results import ASPDMALLMResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    dma.context_builder._cached_task = cg.make_task().model_copy(
        update={"context": TaskContext(channel_id="golden-channel", correlation_id="c", verified_sender=eg.SENDER)}
    )
    captured: Dict[str, Any] = {}

    async def _record(**kwargs: Any) -> Any:
        from ciris_engine.logic.prompt_assembly import current_prompt_manifest

        captured["messages"] = kwargs["messages"]
        captured["manifest"] = current_prompt_manifest()
        return ASPDMALLMResult(selected_action=HandlerActionType.SPEAK, reasoning="r", speak_content="ok"), None

    dma.call_llm_structured = _record  # type: ignore[method-assign]
    with cg.deterministic_prompt_environment(), _qa():
        await dma.evaluate(cg.make_enhanced_inputs())
    return [dict(m) for m in captured["messages"]], captured["manifest"]


@pytest.mark.asyncio
async def test_aspdma_sender_block_is_its_own_segments() -> None:
    messages, manifest = await _aspdma_with_sender()
    _spans_hash(messages, manifest)
    by_kind = {r.kind: r for r in manifest.segments}
    sender = by_kind[SegmentKind.SENDER_IDENTITY]
    assert sender.authn is not None and sender.authn.subject_id == eg.SENDER.user_id and sender.trust == TrustLevel.VERIFIED
    name = by_kind[SegmentKind.DISPLAY_NAME]
    assert name.trust == TrustLevel.UNTRUSTED
    content = _text(messages[sender.message_index])
    assert content[sender.span_start : sender.span_end].startswith("=== VERIFIED SENDER")
    assert eg.SENDER.self_chosen_display_name in content[name.span_start : name.span_end]
    # No other segment carries the sender block's bytes.
    for r in manifest.segments:
        if r.kind not in (SegmentKind.SENDER_IDENTITY, SegmentKind.DISPLAY_NAME):
            body = _text(messages[r.message_index])[r.span_start : r.span_end]
            assert "=== VERIFIED SENDER" not in body and f"id: {eg.SENDER.user_id}" not in body


def _signed_guidance(manifest: Any) -> Any:
    rules = [
        r for r in manifest.segments if r.kind == SegmentKind.RULE and r.provenance == RuleProvenance.SIGNED_GUIDANCE
    ]
    assert len(rules) == 1, [(r.segment_id, r.kind) for r in manifest.segments]
    return rules[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["pdma_full", "csdma_full", "dsdma_full", "idma_full"])
async def test_guidance_task_every_evaluator_reads_the_signed_guidance(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _qa():
        messages = await eg.capture(name, seen)
    manifest = seen["manifest"]
    _spans_hash(messages, manifest)
    rule = _signed_guidance(manifest)
    assert rule.authz is not None and rule.authz.grant_id == eg.GRANT.deferral_id and rule.authz.signature_verified
    assert rule.trust == TrustLevel.VERIFIED
    body = _text(messages[rule.message_index])[rule.span_start : rule.span_end]
    assert eg.GRANT.guidance in body


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["pdma_plain", "csdma_plain", "dsdma_plain"])
async def test_no_guidance_no_rule(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _qa():
        await eg.capture(name, seen)
    assert not [r for r in seen["manifest"].segments if r.kind == SegmentKind.RULE]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["ms_full", "ms_addressed_full"])
async def test_guidance_task_msaspdma_reads_identity_and_signed_guidance(name: str) -> None:
    seen: Dict[str, Any] = {}
    with _qa():
        messages = await mg.capture(name, seen)
    manifest = seen["manifest"]
    _spans_hash(messages, manifest)
    rule = _signed_guidance(manifest)
    assert rule.authz is not None and rule.authz.grant_id == mg.GRANT.deferral_id
    assert SegmentKind.IDENTITY_BASE in {r.kind for r in manifest.segments}
