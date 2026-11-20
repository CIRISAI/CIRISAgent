"""The four consciences' prompts as typed segments, built by PromptAssembler (FSD/PROMPT_CONTEXT_PROVENANCE.md §6, §6a).

Each conscience hands :func:`assemble_conscience_prompt` what it already rendered: its prompt template and slot
values, the accord, the draft under judgement. The segments keep the legacy layout and bytes:

    system: accord | system: stage instruction | system: CORE IDENTITY (+ amendments) |
    user:   (ablated)     VERIFIED SENDER?  action record?  governance?  approval rule?  [WITHHELD]  template
            (non-ablated) governance?  action record?  VERIFIED SENDER?  template (with the user's message)

What the policy changes, and nothing else:

- entropy and the optimization veto receive the request as a stub (``WITHHELD request — ...``), never its bytes,
  and the verified sender (id, role, source; never the display name) whenever a trusted rule is in force;
- only signed rules count: a rule stated in chat has no segment and no stub at any stage (decision 2026-11-18);
- coherence and epistemic humility receive the verified governance block whenever a trusted rule is in force (the
  policy requires a verified ``rule`` segment at every judge then, FSD §14), not only on an evidence re-review;
- an amendment whose signature did not verify grants nothing: production strips it and records an incident.
"""

from typing import Any, Dict, List, NamedTuple, Optional

from ciris_engine.logic.prompt_assembly import AssemblyCall, PromptAssembler
from ciris_engine.logic.prompt_assembly.assembler import LayoutItem, LayoutMessage
from ciris_engine.logic.prompt_assembly.segmenting import (
    governance_segments,
    governed_amendments,
    identity_segments,
    items,
    pipeline_position_segment,
    policy_facts,
    authn_sender_block_segments,
    sender_authn,
    SegmentationError,
    sender_block_segments,
    split_template,
)
from ciris_engine.schemas.context.prompt_provenance import (
    ManifestThoughtKind,
    PromptManifest,
    PromptSegment,
    PromptStage,
    SegmentKind,
    SegmentSource,
    StubFacts,
    StubTransform,
)
from ciris_engine.schemas.runtime.models import VerifiedSender
from ciris_engine.schemas.services.llm import LLMMessage

#: The sentinel ``_extract_user_message`` returns when no user message is known: engine text, not a request.
UNKNOWN_USER_MESSAGE = "unknown"
TRUNCATION_MARK = "...[truncated]"

ABLATED = frozenset({PromptStage.ENTROPY, PromptStage.OPTVETO})


class ConsciencePrompt(NamedTuple):
    messages: List[LLMMessage]
    manifest: PromptManifest
    user_prompt: str
    sees_governance: bool


def _request_segment(text: str, sender_authn_carrier: Any, ablated: bool) -> PromptSegment:
    truncated = text.endswith(TRUNCATION_MARK)
    return PromptSegment(
        segment_id="request",
        kind=SegmentKind.REQUEST,
        source=SegmentSource.USER_INPUT,
        text=text,
        truncated=truncated,
        authn=sender_authn_carrier,
        stub_facts=StubFacts(
            responds_to_draft=True, transforms=[StubTransform.TRUNCATED] if truncated and ablated else []
        )
        if ablated
        else None,
    )


def assemble_conscience_prompt(
    stage: PromptStage,
    *,
    conscience_type: str,
    context: Any,
    language: str,
    accord_text: str,
    draft_slot: str,
    draft_text: str,
    image_context: Optional[str],
    user_message: Optional[str],
    response_model: str,
    plain_slots: Optional[Dict[str, str]] = None,
    approval_rule: str = "",
    assembler: Optional[PromptAssembler] = None,
) -> ConsciencePrompt:
    """Segments, layout, guard and manifest for one conscience call."""
    from ciris_engine.logic.conscience.prompt_loader import get_conscience_prompt_loader
    from ciris_engine.logic.formatters.verified_sender import (
        UNVERIFIED_SENDER,
        WA_SENDER_SOURCE,
        engine_sender_authn,
        verified_sender_of,
    )
    from ciris_engine.logic.formatters.wa_approval import wa_authorization_of
    from ciris_engine.logic.infrastructure.handlers.action_record import action_record_for_task

    ablated = stage in ABLATED
    loader = get_conscience_prompt_loader(language=language)
    thought = getattr(context, "thought", None)
    task_id = getattr(thought, "source_task_id", None)
    task_id = task_id if isinstance(task_id, str) else None
    thought_id = getattr(thought, "thought_id", None)
    thought_id = thought_id if isinstance(thought_id, str) else None
    identity = getattr(context, "agent_identity", None)
    authorization = wa_authorization_of(context)
    sender = getattr(context, "verified_sender", None)
    if not isinstance(sender, VerifiedSender):
        sender = verified_sender_of(thought, getattr(context, "task", None))
    facts = policy_facts(authorization, identity)

    segments: List[PromptSegment] = []
    layout: List[LayoutMessage] = []

    def message(role: str, segs: List[PromptSegment], its: List[LayoutItem]) -> None:
        if segs:
            segments.extend(segs)
            layout.append(LayoutMessage(role="system" if role == "system" else "user", items=its))

    accord = PromptSegment(segment_id="accord", kind=SegmentKind.ACCORD, source=SegmentSource.ENGINE, text=accord_text)
    message("system", [accord], items([accord], ""))
    # The stage instruction, its pipeline position as its own segment (from its own prompt field, #1366 item 12),
    # then the rest of the instruction: blank-line joined, the bytes of ``get_system_prompt`` (still called: it is
    # the render seam the compose dump records).
    system_prompt = loader.get_system_prompt(conscience_type)
    head, position, tail = loader.get_system_prompt_parts(conscience_type)
    system_locale, position_locale, user_locale = loader.prompt_locales(conscience_type)
    if "\n\n".join(part for part in (head, position, tail) if part) != system_prompt:
        raise SegmentationError(f"{conscience_type}: system prompt parts do not rejoin to the system prompt")
    instr = [
        seg
        for seg in (
            PromptSegment(
                segment_id="instr:system",
                kind=SegmentKind.STAGE_INSTRUCTION,
                source=SegmentSource.ENGINE,
                text=head,
                locale=system_locale,
            ),
            pipeline_position_segment(position).model_copy(update={"locale": position_locale}),
            PromptSegment(
                segment_id="instr:system:after_position",
                kind=SegmentKind.STAGE_INSTRUCTION,
                source=SegmentSource.ENGINE,
                text=tail,
                locale=system_locale,
            ),
        )
        if seg.text
    ]
    message("system", instr, items(instr, "\n\n", ""))
    message("system", *identity_segments(identity, language, verified_only=ablated))

    # The user message, block by block.
    blocks: Dict[str, tuple[List[PromptSegment], List[LayoutItem]]] = {}
    # Entropy and the optimization veto get the verified id, role and source (never the display name) whenever a
    # trusted rule is in force (context_policy.yaml ``sender_identity: trusted_rule_in_force``, 2026-11-18): a
    # signed rule may name who it binds, and only the verified sender can be checked against it.
    if ablated and facts.trusted_rule_in_force:
        engine = engine_sender_authn(context)
        if engine is not None:
            # A task the engine created (its recorded origin, set by the creating code): the engine, or the Wise
            # Authority whose verified resolution created a guidance task.
            source = SegmentSource.SIGNED_ROW if engine.verifier == WA_SENDER_SOURCE else SegmentSource.ENGINE
            blocks["sender"] = authn_sender_block_segments(engine, source, language=language)
        else:
            # No verified sender: the required sender_identity says exactly that (id unknown, role not verified).
            # Never SYSTEM: absence of a sender is not evidence the engine sent it.
            blocks["sender"] = sender_block_segments(
                sender or UNVERIFIED_SENDER, include_display_name=False, language=language
            )
    elif not ablated and sender is not None:
        blocks["sender"] = sender_block_segments(sender, include_display_name=True, language=language)
    occurrence = getattr(thought, "agent_occurrence_id", None) or "default"
    record = action_record_for_task(
        task_id, occurrence if isinstance(occurrence, str) else "default", language, factual=True
    )
    if record:
        rec = PromptSegment(
            segment_id="action_record",
            kind=SegmentKind.ACTION_RECORD,
            source=SegmentSource.ENGINE,
            text=record,
            origin_task_id=task_id,
        )
        blocks["record"] = ([rec], items([rec], ""))
    governance = governance_segments(authorization, governed_amendments(identity), language)
    if governance[0]:
        blocks["governance"] = governance
    if approval_rule:
        rule = PromptSegment(
            segment_id="instr:approval_rule", kind=SegmentKind.STAGE_INSTRUCTION, source=SegmentSource.ENGINE,
            text=approval_rule,
        )
        blocks["approval_rule"] = ([rule], items([rule], ""))

    authn = sender_authn(sender) if sender is not None else None
    known_request = user_message is not None and user_message != UNKNOWN_USER_MESSAGE
    if ablated and known_request:
        req = _request_segment(str(user_message), authn, ablated=True)
        blocks["withheld"] = ([req], items([req], ""))

    draft = PromptSegment(
        segment_id="draft",
        kind=SegmentKind.DRAFT,
        source=SegmentSource.LLM_OUTPUT,
        text=draft_text,
        origin_thought_id=thought_id,
    )
    slots: Dict[str, PromptSegment] = {draft_slot: draft}
    plain = dict(plain_slots or {})
    if image_context:
        slots["image_context"] = PromptSegment(
            segment_id="instr:image_context",
            kind=SegmentKind.STAGE_INSTRUCTION,
            source=SegmentSource.ENGINE,
            text=image_context,
        )
    if not ablated and user_message is not None:
        if known_request:
            slots["user_message"] = _request_segment(user_message, authn, ablated=False)
        else:
            plain["user_message"] = user_message

    def render(**values: str) -> str:
        image = values.pop("image_context", None)
        return loader.get_user_prompt(conscience_type, image_context=image, **values)

    blocks["template"] = split_template(render, slots, prefix="instr:template", plain=plain, locale=user_locale)

    order = (
        ["sender", "record", "governance", "approval_rule", "withheld", "template"]
        if ablated
        else ["governance", "record", "sender", "template"]
    )
    user_segments: List[PromptSegment] = []
    user_items: List[LayoutItem] = []
    for name in order:
        if name in blocks:
            segs, its = blocks[name]
            user_segments.extend(segs)
            user_items.extend(its)
    message("user", user_segments, user_items)

    thought_kind = ManifestThoughtKind.GUIDANCE if authorization is not None else (
        ManifestThoughtKind.FOLLOWUP if _is_follow_up(thought) else ManifestThoughtKind.SEED
    )
    messages, manifest = (assembler or PromptAssembler()).build(
        stage,
        segments,
        call=AssemblyCall(
            task_id=task_id,
            thought_id=thought_id,
            thought_kind=thought_kind,
            response_model=response_model,
            facts=facts,
            language=language,
        ),
        layout=layout,
    )
    user_prompt = messages[-1].content if messages and messages[-1].role == "user" else ""
    return ConsciencePrompt(
        messages=messages,
        manifest=manifest,
        user_prompt=user_prompt if isinstance(user_prompt, str) else "",
        sees_governance="governance" in blocks,
    )


def _is_follow_up(thought: Any) -> bool:
    depth = getattr(thought, "thought_depth", 0)
    return bool(getattr(thought, "parent_thought_id", None)) or (isinstance(depth, int) and depth > 0)


__all__ = ["ABLATED", "ConsciencePrompt", "assemble_conscience_prompt"]
