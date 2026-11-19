"""Typed segments from the blocks the engine already renders (FSD/PROMPT_CONTEXT_PROVENANCE.md §4, §6; #1366 Phase 3).

A call site moving onto PromptAssembler must send the same bytes it sent before, except where the policy requires a
change. These helpers take the engine's existing formatters apart along the boundaries the taxonomy cares about,
without rewording anything:

- :func:`split_template` renders a prompt template twice, once with its real slot values and once with
  sentinels, and cuts the sentinel render into instruction pieces and slot segments. The pieces are checked to
  rejoin to the real render byte for byte.
- :func:`identity_segments` renders the CORE IDENTITY block the same way, so each approved amendment is its own
  ``amendment`` segment with its own grant (FSD §6) inside the identity's bytes.
- :func:`sender_block_segments` and :func:`governance_segments` give the VERIFIED SENDER and the verified Wise
  Authority governance blocks as their parts: the sender's identity rendered from its authn carrier, the display
  name labelled, each signed entry a ``rule`` segment carrying its grant.
- :func:`policy_facts` establishes the predicates' facts from trusted state only (signed rows, auth context).
"""

import logging
import re
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ciris_engine.logic.prompt_assembly.assembler import LayoutItem
from ciris_engine.logic.prompt_assembly.carriers import authz_from_wa_authorization
from ciris_engine.logic.prompt_assembly.rendering import ROLE_NOT_VERIFIED
from ciris_engine.schemas.context.prompt_provenance import (
    AuthnCarrier,
    AuthzCarrier,
    GrantKind,
    PolicyFacts,
    PromptSegment,
    RuleProvenance,
    SegmentKind,
    SegmentSource,
)
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.runtime.models import VerifiedSender, WAAuthorization

logger = logging.getLogger(__name__)

Segments = Tuple[List[PromptSegment], List[LayoutItem]]

_SENTINEL = "\x00§{}§\x00"
_SENTINEL_RE = re.compile("\x00§([^§\x00]+)§\x00")

#: Set while :func:`split_template` renders its sentinel probe. That render only locates the slots; its bytes never
#: reach a message, so an observer of the render seams (the #973 compose dump) must not count it as composed text.
_PROBE_RENDER: ContextVar[bool] = ContextVar("prompt_assembly_probe_render", default=False)


def in_probe_render() -> bool:
    """True while a template is being rendered with slot sentinels rather than its real values."""
    return _PROBE_RENDER.get()


class SegmentationError(ValueError):
    """A block's parts did not rejoin to its legacy bytes."""


def _instruction(
    segment_id: str, text: str, source: SegmentSource = SegmentSource.ENGINE, locale: Optional[str] = None
) -> PromptSegment:
    return PromptSegment(
        segment_id=segment_id, kind=SegmentKind.STAGE_INSTRUCTION, source=source, text=text, locale=locale
    )


def items(segments: Sequence[PromptSegment], glue: str, first_glue: str = "\n\n") -> List[LayoutItem]:
    """Layout items for one block: ``first_glue`` before the block, ``glue`` between its segments."""
    return [LayoutItem(segment_id=s.segment_id, glue=first_glue if i == 0 else glue) for i, s in enumerate(segments)]


def split_template(
    render: Callable[..., str],
    slots: Mapping[str, PromptSegment],
    *,
    prefix: str,
    plain: Optional[Mapping[str, str]] = None,
    first_glue: str = "\n\n",
    instruction_source: SegmentSource = SegmentSource.ENGINE,
    locale: Optional[str] = None,
) -> Segments:
    """Cut a template's render into instruction pieces and the given slot segments, in template order.

    ``instruction_source`` is the source of the instruction pieces: the engine's, or ``agent_profile`` for text
    an agent template authored (FSD §4.3).

    ``render(**values)`` must render the template; ``slots`` maps a slot name to the segment its value is.
    ``plain`` slot values stay inside the instruction text (engine-built values such as a locale code).
    A slot used twice yields its segment twice, the second as ``<id>#2``. Raises SegmentationError when the cut
    does not rejoin to the real render (a template that transforms its values).

    ``locale`` is the locale of the template file actually served (``PromptCollection.served_language``, after any
    fallback): the instruction pieces record it. None when unknown (an agent template's own text).
    """
    plain = dict(plain or {})
    real = render(**plain, **{name: seg.text for name, seg in slots.items()})
    token = _PROBE_RENDER.set(True)
    try:
        marked = render(**plain, **{name: _SENTINEL.format(name) for name in slots})
    finally:
        _PROBE_RENDER.reset(token)
    segments: List[PromptSegment] = []
    seen: Dict[str, int] = {}
    cursor = 0
    n = 0
    for match in _SENTINEL_RE.finditer(marked):
        if match.start() > cursor:
            segments.append(_instruction(f"{prefix}:{n}", marked[cursor : match.start()], instruction_source, locale))
            n += 1
        name = match.group(1)
        if name not in slots:
            raise SegmentationError(f"{prefix}: the template rewrote a slot marker ({name!r})")
        seen[name] = seen.get(name, 0) + 1
        seg = slots[name]
        if seen[name] > 1:
            seg = seg.model_copy(update={"segment_id": f"{seg.segment_id}#{seen[name]}"})
        segments.append(seg)
        cursor = match.end()
    if cursor < len(marked):
        segments.append(_instruction(f"{prefix}:{n}", marked[cursor:], instruction_source, locale))
    if "".join(s.text for s in segments) != real:
        raise SegmentationError(f"{prefix}: template pieces do not rejoin to the rendered template")
    return segments, items(segments, "", first_glue)


# ------------------------------------------------------------------------------------------------ identity


def _field(identity: Any, name: str) -> Any:
    return identity.get(name) if isinstance(identity, dict) else getattr(identity, name, None)


def _amendment_authz(raw: Any, index: int) -> AuthzCarrier:
    def get(name: str) -> Any:
        return _field(raw, name)

    return AuthzCarrier(
        grant_kind=GrantKind.AMENDMENT,
        grant_id=str(get("node_id") or f"amendment-{index}"),
        authorizer_id=get("wa_id") or None,
        signature_verified=get("verified") is True,
        attestation_ids=[str(a) for a in (get("response_attestation_id"), get("amendment_attestation_id")) if a],
        granted_at=get("granted_at") or None,
    )


def identity_segments(
    agent_identity: Any, language: Optional[str], *, verified_only: bool = False, prefix: str = "identity"
) -> Segments:
    """The CORE IDENTITY block as ``identity_base`` pieces with one ``amendment`` segment per approved amendment.

    Same bytes as ``formatters.identity.identity_block_of``; ([], []) when that renders nothing.
    """
    from ciris_engine.logic.formatters.identity import amendment_texts, format_core_identity_block, identity_block_of

    real = identity_block_of(agent_identity, language=language, verified_only=verified_only)
    if not real:
        return [], []

    def text_field(name: str) -> str:
        value = _field(agent_identity, name)
        return str(value) if value else ""

    amendments: List[PromptSegment] = []
    for index, raw in enumerate(_field(agent_identity, "approved_amendments") or []):
        texts = amendment_texts({"approved_amendments": [raw]}, verified_only=verified_only, language=language)
        if not texts:
            continue
        amendments.append(
            PromptSegment(
                segment_id=f"{prefix}:amendment:{index}",
                kind=SegmentKind.AMENDMENT,
                source=SegmentSource.SIGNED_ROW,
                text=texts[0],
                authz=_amendment_authz(raw, index),
                order_key=str(_field(raw, "granted_at") or ""),
            )
        )
    marked = format_core_identity_block(
        text_field("agent_id"),
        text_field("description"),
        text_field("role"),
        language=language,
        amendments=[_SENTINEL.format(seg.segment_id) for seg in amendments],
    )
    by_id = {seg.segment_id: seg for seg in amendments}
    segments: List[PromptSegment] = []
    cursor = 0
    n = 0
    for match in _SENTINEL_RE.finditer(marked):
        if match.start() > cursor:
            segments.append(
                _base(f"{prefix}:base:{n}", marked[cursor : match.start()])
            )
            n += 1
        segments.append(by_id[match.group(1)])
        cursor = match.end()
    if cursor < len(marked):
        segments.append(_base(f"{prefix}:base:{n}", marked[cursor:]))
    if "".join(s.text for s in segments) != real:
        raise SegmentationError(f"{prefix}: identity pieces do not rejoin to the identity block")
    return segments, items(segments, "", "")


def _base(segment_id: str, text: str) -> PromptSegment:
    return PromptSegment(
        segment_id=segment_id, kind=SegmentKind.IDENTITY_BASE, source=SegmentSource.AGENT_PROFILE, text=text
    )


# ------------------------------------------------------------------------------------------------ sender


def sender_authn(sender: VerifiedSender) -> AuthnCarrier:
    """The authn carrier of a sender, exactly as the VERIFIED SENDER block states it (``rendering`` inverts it)."""
    return AuthnCarrier(
        subject_id=sender.user_id or "unknown",
        role=sender.role.value if sender.role is not None else ROLE_NOT_VERIFIED,
        verifier=sender.source or "unverified",
    )


def sender_block_segments(
    sender: VerifiedSender, *, include_display_name: bool, prefix: str = "sender", language: Optional[str] = None
) -> Segments:
    """The VERIFIED SENDER block as ``sender_identity`` (from authn), ``display_name`` and its closing lines.

    The assembler renders the first two from their carriers (AssemblyCall.language must be set); the bytes are
    ``formatters.verified_sender.format_verified_sender_block``'s.
    """
    from ciris_engine.logic.formatters.verified_sender import verified_sender_trailer_lines

    segments = [
        PromptSegment(
            segment_id=f"{prefix}:identity",
            kind=SegmentKind.SENDER_IDENTITY,
            source=SegmentSource.AUTH_CONTEXT if sender.role is not None else SegmentSource.ADAPTER_METADATA,
            authn=sender_authn(sender),
        )
    ]
    if include_display_name and sender.self_chosen_display_name:
        segments.append(
            PromptSegment(
                segment_id=f"{prefix}:display_name",
                kind=SegmentKind.DISPLAY_NAME,
                source=SegmentSource.ADAPTER_METADATA,
                text=sender.self_chosen_display_name,
            )
        )
    segments.append(_instruction(f"{prefix}:trailer", "\n".join(verified_sender_trailer_lines(language))))
    return segments, items(segments, "\n")


def authn_sender_block_segments(
    authn: AuthnCarrier, source: SegmentSource, *, prefix: str = "sender", language: Optional[str] = None
) -> Segments:
    """The VERIFIED SENDER block of an engine-built sender (``formatters.verified_sender.engine_sender_authn``): a
    ``sender_identity`` carrying ``authn`` and the block's closing lines. No display name."""
    from ciris_engine.logic.formatters.verified_sender import verified_sender_trailer_lines

    segments = [PromptSegment(segment_id=f"{prefix}:identity", kind=SegmentKind.SENDER_IDENTITY, source=source, authn=authn)]
    segments.append(_instruction(f"{prefix}:trailer", "\n".join(verified_sender_trailer_lines(language))))
    return segments, items(segments, "\n")


# ------------------------------------------------------------------------------------------------ governance


def signed_guidance_segment(segment_id: str, text: str, authorization: WAAuthorization) -> PromptSegment:
    """The Wise Authority's grant as a ``rule.signed_guidance`` segment with its authz (the one WA guidance kind,
    decision 2026-11-18: the former ``wa_guidance`` kind is merged into it)."""
    return PromptSegment(
        segment_id=segment_id,
        kind=SegmentKind.RULE,
        provenance=RuleProvenance.SIGNED_GUIDANCE,
        source=SegmentSource.SIGNED_ROW,
        text=text,
        authz=authz_from_wa_authorization(authorization),
    )


def governance_segments(
    authorization: Optional[WAAuthorization],
    amendments: Sequence[IdentityAmendment],
    language: Optional[str],
    prefix: str = "governance",
) -> Segments:
    """The verified WA governance block: header, one signed ``rule`` per entry (with its grant), footer."""
    from ciris_engine.logic.formatters.wa_approval import wa_governance_parts

    parts = wa_governance_parts(authorization, amendments, language)
    if parts is None:
        return [], []
    header, entries, footer = parts
    segments = [_instruction(f"{prefix}:header", header)]
    for index, (text, record) in enumerate(entries):
        if isinstance(record, WAAuthorization):
            segments.append(signed_guidance_segment(f"{prefix}:entry:{index}", text, record))
            continue
        segments.append(
            PromptSegment(
                segment_id=f"{prefix}:entry:{index}",
                kind=SegmentKind.RULE,
                provenance=RuleProvenance.AMENDMENT,
                source=SegmentSource.SIGNED_ROW,
                text=text,
                authz=_amendment_authz(record, index),
            )
        )
    segments.append(_instruction(f"{prefix}:footer", footer))
    return segments, items(segments, "\n")


# ------------------------------------------------------------------------------------------------ facts


def governed_amendments(agent_identity: Any) -> List[IdentityAmendment]:
    """The amendments that are rules in force: verified as the WA-approved bytes, not the profile's base link."""
    from ciris_engine.logic.formatters.wa_approval import approved_amendments_of

    return [a for a in approved_amendments_of(agent_identity) if a.verified and a.approved_sha256 and not a.base]


def amendment_in_force(agent_identity: Any) -> bool:
    """A landed amendment the loader VERIFIED as the WA-approved bytes (the identity block's own test), not the base link."""
    for raw in _field(agent_identity, "approved_amendments") or [] if agent_identity else []:
        content = _field(raw, "content")
        if _field(raw, "verified") is True and not _field(raw, "base") and content and str(content).strip():
            return True
    return False


def policy_facts(authorization: Optional[WAAuthorization], agent_identity: Any, id_scoped: bool = False) -> PolicyFacts:
    """The predicates' facts, from trusted state only: a verified grant, verified amendments.

    Only signed rules count (decision 2026-11-18): ``advisory_rule`` is never established (a rule stated in chat
    has no segment; nothing structural marks chat text as a rule), and ``id_scoped`` is no longer read by any
    policy row (the ablated consciences get the verified sender whenever a trusted rule is in force). Both stay
    in the closed vocabulary; ``id_scoped`` is accepted for call sites that still pass it.
    """
    return PolicyFacts(
        signed_guidance_in_force=authorization is not None,
        amendment_in_force=amendment_in_force(agent_identity),
        id_scoped=id_scoped,
    )




# ------------------------------------------------------------------------------------------------ blocks


def rendered_text(seg: PromptSegment, language: Optional[str]) -> str:
    """A segment's bytes as the assembler renders them in ``language`` (the sender's lines from their carriers)."""
    from ciris_engine.logic.prompt_assembly.rendering import render_display_name_line, render_sender_identity_lines
    from ciris_engine.logic.utils.localization import get_preferred_language

    if seg.kind == SegmentKind.SENDER_IDENTITY:
        return render_sender_identity_lines(seg.authn, language or get_preferred_language())
    if seg.kind == SegmentKind.DISPLAY_NAME:
        return render_display_name_line(seg.text, language or get_preferred_language())
    return seg.text


def joined(block: Segments, language: Optional[str] = None) -> str:
    """The text of a block laid out with its glue (what the assembler renders for it, untrusted text aside)."""
    segments, layout = block
    by_id = {seg.segment_id: seg for seg in segments}
    out: List[str] = []
    for item in layout:
        if out:
            out.append(item.glue)
        out.append(rendered_text(by_id[item.segment_id], language))
    return "".join(out)


def concat(head: Segments, tail: Segments, glue: str) -> Segments:
    """Two blocks as one, ``glue`` between them (none when either is empty)."""
    h_segments, h_layout = head
    t_segments, t_layout = tail
    if not t_segments:
        return h_segments, h_layout
    if not h_segments:
        return t_segments, [t_layout[0].model_copy(update={"glue": ""})] + t_layout[1:]
    return h_segments + t_segments, h_layout + [t_layout[0].model_copy(update={"glue": glue})] + t_layout[1:]


def block(*segments: Optional[PromptSegment]) -> Segments:
    """Segments laid end to end with no glue; None and empty-text segments are left out."""
    kept = [s for s in segments if s is not None and (s.text or s.kind == SegmentKind.SENDER_IDENTITY)]
    return kept, items(kept, "", "")


def expand(
    whole: Segments, segment_id: str, parts: Segments, language: Optional[str] = None, id_prefix: str = ""
) -> Segments:
    """``whole`` with segment ``segment_id`` (and its ``#n`` repeats from :func:`split_template`) replaced by ``parts``.

    ``parts`` must rejoin to the segment's text (SegmentationError otherwise); an empty slot is left as it is.
    ``id_prefix`` is put before each part's id (one block expanded into two messages keeps its ids distinct).
    """
    segments, layout = whole
    by_id = {seg.segment_id: seg for seg in segments}
    out_segments: List[PromptSegment] = []
    out_layout: List[LayoutItem] = []
    for item in layout:
        seg = by_id[item.segment_id]
        suffix = item.segment_id[len(segment_id) :]
        if not item.segment_id.startswith(segment_id) or (suffix and not suffix.startswith("#")) or not parts[0]:
            out_segments.append(seg)
            out_layout.append(item)
            continue
        if joined(parts, language) != seg.text:
            raise SegmentationError(f"{segment_id}: parts do not rejoin to the slot's text")
        renamed = [p.model_copy(update={"segment_id": id_prefix + p.segment_id + suffix}) for p in parts[0]]
        out_segments.extend(renamed)
        for i, (part_item, part) in enumerate(zip(parts[1], renamed)):
            out_layout.append(LayoutItem(segment_id=part.segment_id, glue=item.glue if i == 0 else part_item.glue))
    return out_segments, out_layout


def task_context_segments(task_context: str, sender: Optional[VerifiedSender], language: Optional[str]) -> Segments:
    """``BaseDMA.format_task_context``'s text as the task (``request``), its VERIFIED SENDER block and the rest.

    The block is cut out where ``format_verified_sender_block`` rendered it; the follow-through guidance after it is
    the engine's instruction. Without a sender block the follow-through is still cut off the task's text.
    """
    from ciris_engine.logic.formatters.verified_sender import format_verified_sender_block

    follow = "\n\n\u26a0\ufe0f FOLLOW-THROUGH REQUIRED:"
    sender_text = format_verified_sender_block(sender, language) if sender is not None else ""
    at = task_context.find(sender_text) if sender_text else -1
    if sender is not None and at >= 0:
        head, tail = task_context[:at], task_context[at + len(sender_text) :]
        result = concat(
            block(_request("task", head)), sender_block_segments(sender, include_display_name=True, language=language), ""
        )
        return concat(result, block(_instruction("task:guidance", tail)), "")
    cut = task_context.find(follow)
    head, tail = (task_context, "") if cut < 0 else (task_context[:cut], task_context[cut:])
    return block(_request("task", head), _instruction("task:guidance", tail))


def _request(segment_id: str, text: str) -> PromptSegment:
    return PromptSegment(segment_id=segment_id, kind=SegmentKind.REQUEST, source=SegmentSource.USER_INPUT, text=text)


def history(segment_id: str, text: str) -> PromptSegment:
    """Engine-gathered conversation state (snapshot, user profiles): ``history``."""
    return PromptSegment(segment_id=segment_id, kind=SegmentKind.HISTORY, source=SegmentSource.ENGINE, text=text)


def original_task_segments(task: Segments, snapshot: str, profiles: str) -> Segments:
    """``=== ORIGINAL TASK ===\n{task}\n\n{snapshot}{profiles}``, the evaluators' context block."""
    head = block(_instruction("ctx:task_header", "=== ORIGINAL TASK ===\n"))
    whole = concat(concat(head, task, ""), block(_instruction("ctx:task_footer", "\n\n")), "")
    return concat(whole, block(history("system_snapshot", snapshot), history("user_profiles", profiles)), "")


def round1_preamble(builder: "PromptBuilder", language: str, accord_mode: str) -> None:
    """``append_round1_accord_blocks``: accord, language guidance, crisis resources, prohibition context."""
    from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
    from ciris_engine.logic.utils.constants import get_accord_text
    from ciris_engine.logic.utils.localization import get_language_guidance, get_prohibition_guidance

    builder.single("system", segment("accord", SegmentKind.ACCORD, get_accord_text(accord_mode) or ""))
    builder.single("system", _instruction("instr:language", get_language_guidance(language) or ""))
    builder.single("system", _instruction("instr:crisis", get_crisis_resources_system_block(language) or ""))
    builder.single("system", _instruction("instr:prohibition", get_prohibition_guidance(language) or ""))


def evaluator_call(response_model: str, thought: Any, language: str, authorization: Optional[WAAuthorization], agent_identity: Any) -> Any:
    """An evaluator's AssemblyCall: the thought's ids and kind, and the facts from trusted state only."""
    from ciris_engine.logic.prompt_assembly.assembler import AssemblyCall
    from ciris_engine.schemas.context.prompt_provenance import ManifestThoughtKind

    depth = getattr(thought, "thought_depth", 0)
    kind = (
        ManifestThoughtKind.GUIDANCE
        if authorization is not None
        else ManifestThoughtKind.FOLLOWUP if isinstance(depth, int) and depth > 0 else ManifestThoughtKind.SEED
    )
    task_id = getattr(thought, "source_task_id", None)
    thought_id = getattr(thought, "thought_id", None)
    return AssemblyCall(
        task_id=task_id if isinstance(task_id, str) else None,
        thought_id=thought_id if isinstance(thought_id, str) else None,
        thought_kind=kind,
        response_model=response_model,
        facts=policy_facts(authorization, agent_identity),
        language=language,
    )


def thought_request(segment_id: str, text: str, thought: Any) -> PromptSegment:
    """The thought under evaluation: the user's message on a seed thought, model text on a follow-up."""
    depth = getattr(thought, "thought_depth", 0)
    source = SegmentSource.LLM_OUTPUT if isinstance(depth, int) and depth > 0 else SegmentSource.USER_INPUT
    return PromptSegment(segment_id=segment_id, kind=SegmentKind.REQUEST, source=source, text=text)


# ------------------------------------------------------------------------------------------------ builder


class PromptBuilder:
    """Collects segments message by message, then assembles them in that layout."""

    def __init__(self) -> None:
        self.segments: List[PromptSegment] = []
        self.layout: List[Any] = []

    def message(
        self,
        role: str,
        segments: Sequence[PromptSegment],
        layout_items: Sequence[LayoutItem],
        images: Optional[Sequence[Any]] = None,
    ) -> None:
        """Append one message (skipped when it has no segments). ``images`` ride after its text (multimodal)."""
        from ciris_engine.logic.prompt_assembly.assembler import LayoutMessage

        if not segments:
            return
        self.segments.extend(segments)
        self.layout.append(
            LayoutMessage(role="system" if role == "system" else "user", items=list(layout_items), images=list(images or []))
        )

    def single(self, role: str, segment: Optional[PromptSegment]) -> None:
        """A message holding one segment (skipped for None or empty text)."""
        if segment is not None and (segment.text or segment.kind == SegmentKind.SENDER_IDENTITY):
            self.message(role, [segment], items([segment], ""))

    def assemble(self, stage: Any, call: Any, assembler: Any = None) -> Tuple[List[Dict[str, Any]], Any]:
        """(messages as the dicts DMAs send, manifest)."""
        from ciris_engine.logic.prompt_assembly.assembler import PromptAssembler

        from ciris_engine.logic.prompt_assembly.assembler import wire_message

        messages, manifest = (assembler or PromptAssembler()).build(stage, self.segments, call=call, layout=self.layout)
        return [wire_message(m) for m in messages], manifest


def segment(segment_id: str, kind: SegmentKind, text: str, source: SegmentSource = SegmentSource.ENGINE, **kw: Any) -> PromptSegment:
    """A segment (shorthand for call sites)."""
    return PromptSegment(segment_id=segment_id, kind=kind, source=source, text=text, **kw)


#: The id every stage gives its pipeline-position segment (#1366 item 12).
PIPELINE_POSITION_ID = "instr:system:pipeline_position"


def pipeline_position_segment(
    text: str, segment_id: str = PIPELINE_POSITION_ID, locale: Optional[str] = None
) -> PromptSegment:
    """The stage's ``pipeline_position`` field as its own segment (system trust, standing, engine source).

    Built from the template FIELD the caller read from the engine template, never found in rendered text: the
    paragraph's heading is translatable, so segmentation cannot depend on its wording.
    """
    return PromptSegment(
        segment_id=segment_id, kind=SegmentKind.PIPELINE_POSITION, source=SegmentSource.ENGINE, text=text, locale=locale
    )


def pipeline_position_slot(text: Any, locale: Optional[str] = None) -> Dict[str, PromptSegment]:
    """``{"pipeline_position": segment}`` for :func:`split_template`, or ``{}`` when the paragraph is empty.

    Empty only when a research manifest replaced the field it was split out of (the render then omits it, so a
    sentinel for it would mark bytes the real render does not have).
    """
    # isinstance, not truthiness: tests substitute a Mock for the prompt loader.
    # isinstance for the locale too: a Mock loader's locale is not a string.
    locale = locale if isinstance(locale, str) else None
    return {"pipeline_position": pipeline_position_segment(text, locale=locale)} if isinstance(text, str) and text else {}


def stripped_ends(segments: List[PromptSegment]) -> List[PromptSegment]:
    """``segments`` as ``str.strip()`` of their concatenation leaves them (``format_system_prompt_blocks`` strips)."""
    out = list(segments)
    while out and not out[0].text.strip() and out[0].kind != SegmentKind.SENDER_IDENTITY:
        out.pop(0)
    while out and not out[-1].text.strip() and out[-1].kind != SegmentKind.SENDER_IDENTITY:
        out.pop()
    if out and out[0].kind != SegmentKind.SENDER_IDENTITY:
        out[0] = out[0].model_copy(update={"text": out[0].text.lstrip()})
    if out and out[-1].kind != SegmentKind.SENDER_IDENTITY:
        out[-1] = out[-1].model_copy(update={"text": out[-1].text.rstrip()})
    return out


__all__ = [
    "PIPELINE_POSITION_ID",
    "PromptBuilder",
    "pipeline_position_segment",
    "pipeline_position_slot",
    "block",
    "evaluator_call",
    "thought_request",
    "concat",
    "expand",
    "history",
    "joined",
    "original_task_segments",
    "round1_preamble",
    "task_context_segments",
    "SegmentationError",
    "Segments",
    "governance_segments",
    "amendment_in_force",
    "governed_amendments",
    "identity_segments",
    "items",
    "policy_facts",
    "sender_authn",
    "authn_sender_block_segments",
    "sender_block_segments",
    "segment",
    "split_template",
    "stripped_ends",
]
