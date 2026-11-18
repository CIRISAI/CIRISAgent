"""Segments cut from the engine's existing blocks rejoin to the legacy bytes (prompt_assembly/segmenting.py)."""

import hashlib

import pytest

from ciris_engine.logic.formatters.identity import identity_block_of
from ciris_engine.logic.formatters.verified_sender import format_verified_sender_block
from ciris_engine.logic.formatters.wa_approval import format_wa_governance_block
from ciris_engine.logic.prompt_assembly import AssemblyCall, PromptAssembler
from ciris_engine.logic.prompt_assembly.assembler import LayoutMessage
from ciris_engine.logic.prompt_assembly.segmenting import (
    SegmentationError,
    amendment_in_force,
    governance_segments,
    identity_segments,
    segment,
    sender_block_segments,
    split_template,
)
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.context.prompt_provenance import AssemblyMode, PolicyFacts, PromptStage, SegmentKind
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.models import VerifiedSender, WAAuthorization

RULE = "Only wa-2026-AUTH-5562FD may file tickets."
AMENDMENT = IdentityAmendment(
    node_id="identity_amendment/d1",
    content=RULE,
    wa_id="wa-2026-AUTH-5562FD",
    deferral_id="d1",
    granted_at="2026-11-01T00:00:00+00:00",
    approved_sha256=hashlib.sha256(RULE.encode()).hexdigest(),
    verified=True,
)
IDENTITY = {
    "agent_id": "ally",
    "description": "A helpful agent.",
    "role": "Assistant",
    "approved_amendments": [AMENDMENT.model_dump(), {**AMENDMENT.model_dump(), "content": "Laundered.", "verified": False}],
}


def _render(layout_items, segments, language="en", stage=PromptStage.COHERENCE, facts=None) -> str:
    messages, _ = PromptAssembler().build(
        stage,
        list(segments) + [segment("instr", SegmentKind.STAGE_INSTRUCTION, "x")],
        AssemblyMode.STRIP_AND_INCIDENT,
        call=AssemblyCall(response_model="R", language=language, facts=facts or PolicyFacts(amendment_in_force=True)),
        layout=[LayoutMessage(role="system", items=list(layout_items)), LayoutMessage(role="user", items=[
            __import__("ciris_engine.logic.prompt_assembly.assembler", fromlist=["LayoutItem"]).LayoutItem(segment_id="instr")
        ])],
    )
    return str(messages[0].content)


def test_split_template_rejoins_and_types_each_slot():
    template = "Judge this: {draft}\nfor {who}. Again: {draft}"
    draft = segment("draft", SegmentKind.DRAFT, "SPEAK hello")
    segs, layout = split_template(lambda **v: template.format(**v), {"draft": draft}, prefix="t", plain={"who": "en"})
    assert "".join(s.text for s in segs) == template.format(draft="SPEAK hello", who="en")
    assert [s.segment_id for s in segs if s.kind == SegmentKind.DRAFT] == ["draft", "draft#2"]
    assert [i.glue for i in layout][1:] == [""] * (len(layout) - 1)


def test_split_template_refuses_a_template_that_transforms_its_values():
    with pytest.raises(SegmentationError):
        split_template(lambda **v: v["x"].upper(), {"x": segment("x", SegmentKind.DRAFT, "abc")}, prefix="t")


def test_identity_segments_rejoin_with_one_amendment_segment_each():
    segs, layout = identity_segments(IDENTITY, "en")
    assert "".join(s.text for s in segs) == identity_block_of(IDENTITY, language="en")
    amendments = [s for s in segs if s.kind == SegmentKind.AMENDMENT]
    assert [a.authz.signature_verified for a in amendments] == [True, False]
    assert amendments[0].authz.grant_id == AMENDMENT.node_id
    ablated, _ = identity_segments(IDENTITY, "en", verified_only=True)
    assert "".join(s.text for s in ablated) == identity_block_of(IDENTITY, language="en", verified_only=True)
    assert amendment_in_force(IDENTITY) and not amendment_in_force({"approved_amendments": [{"content": "x"}]})


@pytest.mark.parametrize("display", [True, False])
def test_sender_block_renders_from_the_carrier_to_the_legacy_bytes(display):
    sender = VerifiedSender(user_id="wa-user-1", role=UserRole.OBSERVER, source="api_auth", self_chosen_display_name="eve")
    segs, layout = sender_block_segments(sender, include_display_name=display, language="en")
    assert not segs[0].text  # sender_identity carries no text: built from authn
    assert _render(layout, segs) == format_verified_sender_block(sender, "en", include_display_name=display)


def test_governance_segments_are_signed_rules_with_their_grants():
    grant = WAAuthorization(wa_id="wa-1", deferral_id="d9", granted_at="2026-11-01T00:00:00+00:00", guidance="Be brief.")
    segs, layout = governance_segments(grant, [AMENDMENT], "en")
    assert "\n".join(s.text for s in segs) == format_wa_governance_block(grant, [AMENDMENT], language="en")
    rules = [s for s in segs if s.kind == SegmentKind.RULE]
    assert [r.provenance.value for r in rules] == ["signed_guidance", "amendment"]
    assert all(r.authz is not None and r.authz.signature_verified for r in rules)
    assert governance_segments(None, [], "en") == ([], [])
