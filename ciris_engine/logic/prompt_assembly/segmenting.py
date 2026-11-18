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


class SegmentationError(ValueError):
    """A block's parts did not rejoin to its legacy bytes."""


def _instruction(segment_id: str, text: str, source: SegmentSource = SegmentSource.ENGINE) -> PromptSegment:
    return PromptSegment(segment_id=segment_id, kind=SegmentKind.STAGE_INSTRUCTION, source=source, text=text)


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
) -> Segments:
    """Cut a template's render into instruction pieces and the given slot segments, in template order.

    ``render(**values)`` must render the template; ``slots`` maps a slot name to the segment its value is.
    ``plain`` slot values stay inside the instruction text (engine-built values such as a locale code).
    A slot used twice yields its segment twice, the second as ``<id>#2``. Raises SegmentationError when the cut
    does not rejoin to the real render (a template that transforms its values).
    """
    plain = dict(plain or {})
    real = render(**plain, **{name: seg.text for name, seg in slots.items()})
    marked = render(**plain, **{name: _SENTINEL.format(name) for name in slots})
    segments: List[PromptSegment] = []
    seen: Dict[str, int] = {}
    cursor = 0
    n = 0
    for match in _SENTINEL_RE.finditer(marked):
        if match.start() > cursor:
            segments.append(_instruction(f"{prefix}:{n}", marked[cursor : match.start()]))
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
        segments.append(_instruction(f"{prefix}:{n}", marked[cursor:]))
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


# ------------------------------------------------------------------------------------------------ governance


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
            provenance, authz = RuleProvenance.SIGNED_GUIDANCE, authz_from_wa_authorization(record)
        else:
            provenance, authz = RuleProvenance.AMENDMENT, _amendment_authz(record, index)
        segments.append(
            PromptSegment(
                segment_id=f"{prefix}:entry:{index}",
                kind=SegmentKind.RULE,
                provenance=provenance,
                source=SegmentSource.SIGNED_ROW,
                text=text,
                authz=authz,
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


def policy_facts(
    authorization: Optional[WAAuthorization], agent_identity: Any, id_scoped: bool, advisory_rule: bool = False
) -> PolicyFacts:
    """The predicates' facts, from trusted state only: a verified grant, verified amendments, the auth context.

    ``advisory_rule`` stays False until the engine records a chat-stated rule structurally (never by reading text).
    """
    return PolicyFacts(
        signed_guidance_in_force=authorization is not None,
        amendment_in_force=amendment_in_force(agent_identity),
        id_scoped=id_scoped,
        advisory_rule=advisory_rule,
    )




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
    "PromptBuilder",
    "SegmentationError",
    "Segments",
    "governance_segments",
    "amendment_in_force",
    "governed_amendments",
    "identity_segments",
    "items",
    "policy_facts",
    "sender_authn",
    "sender_block_segments",
    "segment",
    "split_template",
    "stripped_ends",
]
