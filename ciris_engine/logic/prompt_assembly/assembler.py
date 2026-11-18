"""PromptAssembler: the one builder of an LLM call's message list (FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

``build(stage, segments, mode, call)`` takes typed segments, never strings, and returns the messages to send and
the call's manifest. In order:

1. **Taint** (§4.4): a segment's trust is the minimum of the policy's trust for its kind (a rule: its provenance),
   the caller's own statement, and the trust of every segment it was derived from, transitively. An unknown or
   cyclic ``derived_from`` counts as untrusted. A grant whose signature did not verify grants nothing.
2. **Guard** (§6): each segment is checked against the policy row for (stage, kind[.provenance]) under the
   system's facts, then the required rows are checked. ``FAIL_CLOSED`` (tests, QA, battery, mock) raises
   :class:`ContextPolicyViolation`; ``STRIP_AND_INCIDENT`` (production) strips the offending segments, records an
   incident (an ERROR log, which the incident capture handler persists) and proceeds: aborting a conscience
   would make its result "unavailable" and weaken the gate.
3. **Order and render**: rows in policy order; within a row, ``order_key`` then ``segment_id``, so input order
   never matters. Verified and system segments go in the system message, untrusted ones in the user message:
   the layout follows trust. ``sender_identity`` is rendered from its ``authn`` carrier alone; ``display_name``
   is labelled self-chosen; rules and amendments carry their provenance.
4. **Stubs** (§6a): at an ablated stage, a segment whose policy cell has ``form: stub`` is withheld: the call
   carries one system-built line of closed-vocabulary properties in its place (kind, author role, authority,
   scope, disposition, size, draft relation, digest ...), never a byte of it. Consecutive stubs share one block
   whose delimiters are neutralised in every untrusted segment, so no input can open or close one. The guard
   also probes every other non-residual segment for the withheld bytes (``UNTRUSTED_BYTES``): a call site that
   interpolated the request into, say, its instruction text is caught, not stubbed around.

A call site that must keep its legacy message layout passes ``layout``: which messages exist, their roles, the
order of segments in each and the glue between them. Ordering is then the call site's (deterministic per stage),
and the assembler still guards, stubs, neutralises, renders and records every segment.
"""

import hashlib
import logging
from collections import defaultdict
from typing import Dict, List, Literal, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.prompt_assembly.manifest_scope import messages_sha256
from ciris_engine.logic.prompt_assembly.policy import (
    STAGE_ROLES,
    declared_trust,
    load_context_policy,
    predicate_holds,
    row_is_required,
)
from ciris_engine.logic.prompt_assembly.rendering import render_display_name_line, render_sender_identity_lines
from ciris_engine.logic.utils.mock_llm_guard import TraceRunKind, trace_run_kind
from ciris_engine.schemas.context.prompt_provenance import (
    STUB_DISPOSITIONS,
    AssemblyMode,
    DraftRelation,
    QuoteShare,
    SegmentForm,
    SegmentStub,
    SizeBucket,
    StubAuthorRole,
    StubAuthority,
    StubDisposition,
    StubFacts,
    StubField,
    StubScope,
    StubTransform,
    ContextPolicy,
    GuardAction,
    GuardViolation,
    GuardViolationKind,
    Lifecycle,
    ManifestThoughtKind,
    PolicyFacts,
    PolicyRow,
    PromptManifest,
    PromptSegment,
    PromptStage,
    RuleProvenance,
    SegmentKind,
    SegmentRecord,
    TrustLevel,
    min_trust,
)
from ciris_engine.schemas.services.llm import LLMMessage

logger = logging.getLogger(__name__)

ASSEMBLER_VERSION = "2"
SEGMENT_SEPARATOR = "\n\n"


class ContextPolicyViolation(Exception):
    """A call's segments break the context policy (raised in FAIL_CLOSED mode)."""

    def __init__(self, stage: PromptStage, violations: List[GuardViolation]) -> None:
        self.stage = stage
        self.violations = violations
        summary = "; ".join(f"{v.kind.value} {v.policy_key} ({v.segment_id or '-'}): {v.detail}" for v in violations)
        super().__init__(f"context policy violated at stage {stage.value}: {summary}")


class AssemblyCall(BaseModel):
    """The per-call facts the manifest records and the guard evaluates against."""

    task_id: Optional[str] = None
    thought_id: Optional[str] = None
    thought_kind: ManifestThoughtKind = ManifestThoughtKind.SEED
    retry_index: int = Field(0, ge=0, description="0 on the first pass; n on the n-th conscience retry")
    response_model: str = Field(..., min_length=1, description="Name of the response model the call asks for")
    facts: PolicyFacts = Field(default_factory=PolicyFacts)
    call_id: Optional[str] = Field(None, description="Defaults to a hash of the call's identity and messages")
    language: Optional[str] = Field(
        None, description="Render the engine's localized blocks in this locale; None: the assembler's own labels"
    )

    model_config = ConfigDict(extra="forbid", frozen=True)


class LayoutItem(BaseModel):
    """One segment's place in a message, and the glue placed before it when something precedes it."""

    segment_id: str = Field(..., min_length=1)
    glue: str = Field(SEGMENT_SEPARATOR, description="Placed before the segment unless it opens the message")

    model_config = ConfigDict(extra="forbid", frozen=True)


class LayoutMessage(BaseModel):
    """One message of an explicit layout: its role and its segments in order."""

    role: Literal["system", "user"]
    items: List[LayoutItem]

    model_config = ConfigDict(extra="forbid", frozen=True)


def guard_mode_for_run_kind(kind: TraceRunKind) -> AssemblyMode:
    """Production strips and records; every harness run (qa, battery, mock) fails closed."""
    return AssemblyMode.STRIP_AND_INCIDENT if kind == TraceRunKind.PRODUCTION else AssemblyMode.FAIL_CLOSED


def current_guard_mode() -> AssemblyMode:
    """The guard mode for this process, from its run kind (production when undeclared)."""
    return guard_mode_for_run_kind(trace_run_kind())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PromptAssembler:
    """Builds an LLM call's messages from typed segments under the context policy."""

    def __init__(self, policy: Optional[ContextPolicy] = None) -> None:
        self.policy = policy if policy is not None else load_context_policy()

    # ------------------------------------------------------------------ taint

    def _own_trust(self, segment: PromptSegment) -> TrustLevel:
        trust = declared_trust(self.policy, segment.kind, segment.provenance)
        if segment.trust is not None:
            trust = min_trust(trust, segment.trust)
        if segment.authz is not None and not segment.authz.signature_verified:
            trust = TrustLevel.UNTRUSTED  # an unverified grant grants nothing
        return trust

    def effective_trust(self, segments: Sequence[PromptSegment]) -> Dict[str, TrustLevel]:
        """Trust after taint for every segment id (FSD §4.4)."""
        by_id: Dict[str, PromptSegment] = {}
        for seg in segments:
            by_id.setdefault(seg.segment_id, seg)
        done: Dict[str, TrustLevel] = {}

        def visit(seg_id: str, path: Set[str]) -> TrustLevel:
            if seg_id in done:
                return done[seg_id]
            seg = by_id.get(seg_id)
            if seg is None or seg_id in path:
                return TrustLevel.UNTRUSTED  # bytes of unknown or circular origin
            trust = self._own_trust(seg)
            for parent in seg.derived_from:
                trust = min_trust(trust, visit(parent, path | {seg_id}))
            done[seg_id] = trust
            return trust

        for seg_id in by_id:
            visit(seg_id, set())
        return done

    # ------------------------------------------------------------------ guard

    def _rows(self, stage: PromptStage) -> List[PolicyRow]:
        rows = self.policy.stages.get(stage)
        if rows is None:
            # A stage the policy does not describe is a configuration error, in every mode.
            raise ValueError(f"context policy v{self.policy.version} has no rows for stage {stage.value!r}")
        return rows

    def _segment_violations(
        self,
        stage: PromptStage,
        seg: PromptSegment,
        row: Optional[PolicyRow],
        trust: TrustLevel,
        call: AssemblyCall,
    ) -> List[Tuple[GuardViolationKind, str]]:
        found: List[Tuple[GuardViolationKind, str]] = []
        retry = call.retry_index > 0
        if row is None or not predicate_holds(row.predicate, call.facts, retry):
            why = "not listed for this stage" if row is None else f"predicate {row.predicate.value} does not hold"
            found.append((GuardViolationKind.FORBIDDEN, why))
        declared = declared_trust(self.policy, seg.kind, seg.provenance)
        if trust != declared and min_trust(trust, declared) == trust:
            found.append((GuardViolationKind.TAINTED, f"trust after taint {trust.value} < policy {declared.value}"))
        spec = self.policy.kinds[seg.kind]
        authz_required = spec.authz_required or (
            seg.kind == SegmentKind.RULE and seg.provenance in (RuleProvenance.SIGNED_GUIDANCE, RuleProvenance.AMENDMENT)
        )
        for name, required, present in (
            ("authn", spec.authn_required, seg.authn is not None),
            ("authz", authz_required, seg.authz is not None),
            ("acct", spec.acct_required, seg.acct is not None),
        ):
            if required and not present:
                found.append((GuardViolationKind.MISSING_CARRIER, f"{name} is required"))
        if spec.source is not None and seg.source != spec.source:
            found.append((GuardViolationKind.WRONG_SOURCE, f"source must be {spec.source.value}"))
        if seg.lifecycle is not None and seg.lifecycle != spec.lifecycle:
            found.append((GuardViolationKind.LIFECYCLE_MISMATCH, f"policy lifecycle is {spec.lifecycle.value}"))
        if spec.lifecycle == Lifecycle.PER_TASK and seg.origin_task_id not in (None, call.task_id):
            found.append((GuardViolationKind.CROSS_SCOPE, "per-task segment from another task"))
        if spec.lifecycle == Lifecycle.PER_THOUGHT and seg.origin_thought_id not in (None, call.thought_id):
            found.append((GuardViolationKind.CROSS_SCOPE, "per-thought segment from another thought"))
        return found

    def _guard(
        self, stage: PromptStage, segments: Sequence[PromptSegment], call: AssemblyCall, mode: AssemblyMode
    ) -> Tuple[List[PromptSegment], List[GuardViolation], Dict[str, TrustLevel]]:
        rows = {row.key: row for row in self._rows(stage)}
        trust = self.effective_trust(segments)
        strip_action = GuardAction.RAISED if mode == AssemblyMode.FAIL_CLOSED else GuardAction.STRIPPED
        missing_action = GuardAction.RAISED if mode == AssemblyMode.FAIL_CLOSED else GuardAction.RECORDED
        violations: List[GuardViolation] = []
        kept: List[PromptSegment] = []
        seen: Set[str] = set()
        for seg in segments:
            if seg.segment_id in seen:
                found = [(GuardViolationKind.DUPLICATE_SEGMENT_ID, "segment id already used in this call")]
            else:
                seen.add(seg.segment_id)
                found = self._segment_violations(stage, seg, rows.get(seg.policy_key), trust[seg.segment_id], call)
            for kind, detail in found:
                violations.append(
                    GuardViolation(
                        kind=kind,
                        stage=stage,
                        policy_key=seg.policy_key,
                        segment_id=seg.segment_id,
                        detail=detail,
                        action=strip_action,
                    )
                )
            if not found:
                kept.append(seg)
        present = {seg.policy_key for seg in kept}
        retry = call.retry_index > 0
        for key, row in rows.items():
            if row_is_required(row, STAGE_ROLES[stage]) and predicate_holds(row.predicate, call.facts, retry) and key not in present:
                violations.append(
                    GuardViolation(
                        kind=GuardViolationKind.MISSING_REQUIRED,
                        stage=stage,
                        policy_key=key,
                        detail=f"required when {row.predicate.value}",
                        action=missing_action,
                    )
                )
        return kept, violations, trust

    # ------------------------------------------------------------------ render

    @staticmethod
    def _authority_clause(seg: PromptSegment) -> str:
        authz = seg.authz
        if authz is None:  # the guard strips these before rendering
            return "authorization unknown"
        signature = "signature verified" if authz.signature_verified else "signature NOT verified"
        return f"authorized by Wise Authority {authz.authorizer_id or 'unknown'}, {authz.grant_kind.value} {authz.grant_id}, {signature}"

    def render(self, seg: PromptSegment, language: Optional[str] = None) -> str:
        """The bytes a segment occupies in the prompt (FSD §6).

        ``language`` set: the engine's localized prompt blocks. ``sender_identity`` and ``display_name`` render
        from their carriers through ``formatters.verified_sender``; a rule or amendment renders its own text,
        which the engine's formatter built with its provenance ids. None: the assembler's own labels.
        """
        if language is not None:
            if seg.kind == SegmentKind.SENDER_IDENTITY:
                return render_sender_identity_lines(seg.authn, language)
            if seg.kind == SegmentKind.DISPLAY_NAME:
                return render_display_name_line(seg.text, language)
            return seg.text
        if seg.kind == SegmentKind.SENDER_IDENTITY:
            a = seg.authn
            if a is None:
                return "VERIFIED SENDER: none"
            return f"VERIFIED SENDER: id={a.subject_id}, role={a.role} (verified by {a.verifier})"
        if seg.kind == SegmentKind.DISPLAY_NAME:
            return f"Display name (self-chosen, not identity): {seg.text}"
        if seg.kind == SegmentKind.RULE:
            if seg.provenance in (RuleProvenance.SIGNED_GUIDANCE, RuleProvenance.AMENDMENT):
                return f"RULE IN FORCE — {self._authority_clause(seg)}:\n{seg.text}"
            who = "the Wise Authority" if seg.provenance == RuleProvenance.WA_CHAT else "the user"
            return f"ADVISORY RULE — stated in chat by {who}, not signed, not authoritative:\n{seg.text}"
        if seg.kind == SegmentKind.AMENDMENT:
            return f"APPROVED IDENTITY AMENDMENT — {self._authority_clause(seg)}:\n{seg.text}"
        return seg.text

    # ------------------------------------------------------------------ stubs (FSD §6a)

    def make_stub(self, seg: PromptSegment, trust: TrustLevel, drafts: Sequence[str]) -> SegmentStub:
        """The closed-vocabulary description of a withheld segment. Every value is computed by the engine."""
        facts = seg.stub_facts or StubFacts()
        lifecycle = self.policy.kinds[seg.kind].lifecycle
        allowed = STUB_DISPOSITIONS.get(seg.kind.value, [])
        if facts.disposition is not None and facts.disposition not in allowed:
            raise ValueError(f"disposition {facts.disposition.value} is not one of {seg.kind.value}'s")
        disposition = facts.disposition or (allowed[0] if allowed else StubDisposition.PRIOR)
        transforms = set(facts.transforms)
        if seg.truncated:
            transforms.add(StubTransform.TRUNCATED)
        share = quote_share(seg.text, drafts)
        if share != QuoteShare.ZERO:
            relation = DraftRelation.QUOTES
        elif facts.responds_to_draft and drafts:
            relation = DraftRelation.RESPONDS_TO
        else:
            relation = DraftRelation.NONE
        return SegmentStub(
            kind=seg.kind,
            provenance=seg.provenance,
            source=seg.source,
            trust=trust,
            author_role=_author_role(seg),
            authority=_authority(seg),
            scope=_SCOPE[lifecycle],
            disposition=disposition,
            transforms=sorted(transforms, key=lambda t: t.value),
            draft_relation=relation,
            quote_share=share,
            size=_size(seg.text),
            position=facts.position,
            digest=_sha256(seg.text)[:12],
        )

    def render_stub(self, stub: SegmentStub) -> str:
        """One system-built line: only the fields the policy's closed ``stub_fields`` set declares."""
        fields = self.policy.stub_fields
        values: List[str] = []
        for name in fields:
            if name == StubField.KIND:
                continue
            if name == StubField.PROVENANCE:
                if stub.provenance is not None:
                    values.append(f"provenance={stub.provenance.value}")
                continue
            if name == StubField.TRANSFORMS:
                values.append("transforms=" + (",".join(t.value for t in stub.transforms) or "none"))
                continue
            if name == StubField.DRAFT_RELATION:
                values.append(f"draft_relation={stub.draft_relation.value} quote_share={stub.quote_share.value}")
                continue
            value = getattr(stub, name.value)
            values.append(f"{name.value}={getattr(value, 'value', value)}")
        return f"WITHHELD {stub.kind.value} — " + " ".join(values)

    @staticmethod
    def _leak_violations(
        stage: PromptStage,
        withheld: Sequence[PromptSegment],
        rendered: Dict[str, str],
        residual: Set[str],
        action: GuardAction,
    ) -> List[GuardViolation]:
        """At an ablated stage: does any withheld segment's text occur inside another non-residual segment?"""
        found: List[GuardViolation] = []
        probes = [(seg.segment_id, _probes(seg.text)) for seg in withheld]
        for seg_id, text in rendered.items():
            if seg_id in residual:
                continue
            haystack = _normalise(text)
            for source_id, windows in probes:
                if source_id != seg_id and any(w in haystack for w in windows):
                    found.append(
                        GuardViolation(
                            kind=GuardViolationKind.UNTRUSTED_BYTES,
                            stage=stage,
                            policy_key=seg_id,
                            segment_id=seg_id,
                            detail=f"carries bytes of withheld segment {source_id}",
                            action=action,
                        )
                    )
                    break
        return found

    # ------------------------------------------------------------------ build

    def build(
        self,
        stage: PromptStage,
        segments: Sequence[PromptSegment],
        mode: Optional[AssemblyMode] = None,
        *,
        call: AssemblyCall,
        layout: Optional[Sequence[LayoutMessage]] = None,
    ) -> Tuple[List[LLMMessage], PromptManifest]:
        """Guard, stub, order and render ``segments`` for ``stage``; returns (messages, manifest).

        ``mode`` None resolves from the process's run kind (:func:`current_guard_mode`). ``layout`` None orders
        by the policy and lays out by trust; otherwise it must name every segment exactly once.
        Raises :class:`ContextPolicyViolation` in FAIL_CLOSED mode on any violation.
        """
        mode = mode if mode is not None else current_guard_mode()
        if layout is not None:
            _check_layout(segments, layout)
        kept, violations, trust = self._guard(stage, segments, call, mode)
        if violations and mode == AssemblyMode.FAIL_CLOSED:
            raise ContextPolicyViolation(stage, violations)

        rows = {row.key: row for row in self._rows(stage)}
        withheld_ids = {s.segment_id for s in kept if rows[s.policy_key].form == SegmentForm.STUB}
        drafts = [s.text for s in kept if s.kind == SegmentKind.DRAFT]
        stubs = {s.segment_id: self.make_stub(s, trust[s.segment_id], drafts) for s in kept if s.segment_id in withheld_ids}
        rendered: Dict[str, str] = {}
        for seg in kept:
            if seg.segment_id in withheld_ids:
                rendered[seg.segment_id] = self.render_stub(stubs[seg.segment_id])
            else:
                text = self.render(seg, call.language)
                rendered[seg.segment_id] = neutralise(text) if trust[seg.segment_id] == TrustLevel.UNTRUSTED else text
        if stage in self.policy.ablated_stages and withheld_ids:
            residual = {s.segment_id for s in kept if self.policy.kinds[s.kind].residual} | withheld_ids
            action = GuardAction.RAISED if mode == AssemblyMode.FAIL_CLOSED else GuardAction.STRIPPED
            leaks = self._leak_violations(
                stage,
                [s for s in kept if s.segment_id in withheld_ids],
                {k: v for k, v in rendered.items() if k not in withheld_ids},
                residual,
                action,
            )
            if leaks:
                if mode == AssemblyMode.FAIL_CLOSED:
                    raise ContextPolicyViolation(stage, leaks)
                leaked = {v.segment_id for v in leaks}
                kept = [s for s in kept if s.segment_id not in leaked]
                violations = violations + leaks
        if violations:
            # Production: an incident (ERROR reaches incidents_latest.log and the incident graph). Ids, never text.
            logger.error(
                "[CONTEXT-GUARD] stage=%s task=%s thought=%s: %d context policy violation(s), offending segments "
                "stripped, call proceeds: %s",
                stage.value,
                call.task_id,
                call.thought_id,
                len(violations),
                "; ".join(f"{v.kind.value}:{v.policy_key}:{v.segment_id or '-'}" for v in violations),
            )

        arranged = self._arrange(stage, kept, trust, layout)
        messages: List[LLMMessage] = []
        records: List[SegmentRecord] = []
        for role, items in arranged:
            content, spans = _join(items, rendered, withheld_ids)
            if not spans:
                continue
            index = len(messages)
            for seg, (start, end) in spans:
                withheld = seg.segment_id in withheld_ids
                records.append(
                    SegmentRecord(
                        segment_id=seg.segment_id,
                        kind=seg.kind,
                        provenance=seg.provenance,
                        source=seg.source,
                        trust=trust[seg.segment_id],
                        lifecycle=self.policy.kinds[seg.kind].lifecycle,
                        authn=seg.authn,
                        authz=seg.authz,
                        acct=seg.acct,
                        message_index=index,
                        span_start=start,
                        span_end=end,
                        sha256=_sha256(content[start:end]),
                        truncated=seg.truncated,
                        derived_from=list(seg.derived_from),
                        form=SegmentForm.STUB if withheld else SegmentForm.FULL,
                        stub=stubs.get(seg.segment_id),
                        withheld_sha256=_sha256(seg.text) if withheld else None,
                    )
                )
            messages.append(LLMMessage(role=role, content=content))

        wire = [m.model_dump(exclude_none=True) for m in messages]
        digest = messages_sha256(wire)
        call_id = call.call_id or _sha256(
            "|".join([stage.value, call.task_id or "", call.thought_id or "", str(call.retry_index), digest])
        )[:32]
        manifest = PromptManifest(
            call_id=call_id,
            task_id=call.task_id,
            thought_id=call.thought_id,
            thought_kind=call.thought_kind,
            retry_index=call.retry_index,
            stage=stage,
            stage_role=STAGE_ROLES[stage],
            response_model=call.response_model,
            policy_version=self.policy.version,
            policy_sha256=self.policy.source_sha256,
            assembler_version=ASSEMBLER_VERSION,
            guard_mode=mode,
            guard_violations=violations,
            segments=records,
            messages_sha256=digest,
        )
        return messages, manifest

    def _arrange(
        self,
        stage: PromptStage,
        kept: Sequence[PromptSegment],
        trust: Dict[str, TrustLevel],
        layout: Optional[Sequence[LayoutMessage]],
    ) -> List[Tuple[Literal["system", "user"], List[Tuple[PromptSegment, str]]]]:
        """(role, [(segment, glue before it)]) per message, stripped segments dropped."""
        by_id = {s.segment_id: s for s in kept}
        if layout is not None:
            return [
                (
                    msg.role,
                    [(by_id[i.segment_id], i.glue) for i in msg.items if i.segment_id in by_id],
                )
                for msg in layout
            ]
        order = {row.key: i for i, row in enumerate(self._rows(stage))}
        ordered = sorted(kept, key=lambda s: (order[s.policy_key], s.order_key, s.segment_id))
        groups: Dict[str, List[Tuple[PromptSegment, str]]] = defaultdict(list)
        for seg in ordered:
            role = "user" if trust[seg.segment_id] == TrustLevel.UNTRUSTED else "system"
            groups[role].append((seg, SEGMENT_SEPARATOR))
        return [("system", groups["system"]), ("user", groups["user"])]


# ---------------------------------------------------------------------------------------------- helpers

#: The withheld-context block's delimiters. Neutralised in every untrusted segment (``neutralise``): no input can
#: open, close or imitate a block.
STUB_BLOCK_OPEN = "\u27e6WITHHELD\u27e7"
STUB_BLOCK_CLOSE = "\u27e6/WITHHELD\u27e7"
_NEUTRALISE = str.maketrans({"\u27e6": "[", "\u27e7": "]"})

#: Stub size buckets, in characters of the withheld text.
SIZE_SHORT_MAX = 200
SIZE_MEDIUM_MAX = 1000
#: Character n-gram length of the deterministic draft overlap (script-agnostic: no tokeniser).
QUOTE_NGRAM = 8
#: Leak probes: windows of the withheld text searched for in every other segment at an ablated stage.
LEAK_MIN_CHARS = 20
LEAK_WINDOW = 32
LEAK_STRIDE = 16
LEAK_MAX_PROBES = 256

_SCOPE: Dict[Lifecycle, StubScope] = {
    Lifecycle.STANDING: StubScope.STANDING,
    Lifecycle.PER_TASK: StubScope.THIS_TASK,
    Lifecycle.PER_MESSAGE: StubScope.THIS_TURN,
    Lifecycle.PER_THOUGHT: StubScope.THIS_TURN,
    Lifecycle.RETRY_ONLY: StubScope.THIS_TURN,
    Lifecycle.PER_CALL: StubScope.THIS_TURN,
}


def neutralise(text: str) -> str:
    """Untrusted text with the stub block's delimiter characters replaced by plain brackets."""
    return text.translate(_NEUTRALISE)


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _ngrams(text: str) -> Set[str]:
    norm = _normalise(text)
    if not norm:
        return set()
    if len(norm) <= QUOTE_NGRAM:
        return {norm}
    return {norm[i : i + QUOTE_NGRAM] for i in range(len(norm) - QUOTE_NGRAM + 1)}


def quote_share(text: str, drafts: Sequence[str]) -> QuoteShare:
    """Bucketed share of ``text``'s character n-grams that also occur in the draft(s)."""
    grams = _ngrams(text)
    if not grams or not drafts:
        return QuoteShare.ZERO
    draft_grams: Set[str] = set()
    for draft in drafts:
        draft_grams |= _ngrams(draft)
    share = len(grams & draft_grams) / len(grams)
    if share == 0:
        return QuoteShare.ZERO
    if share < 0.10:
        return QuoteShare.UNDER_10
    if share <= 0.50:
        return QuoteShare.FROM_10_TO_50
    return QuoteShare.OVER_50


def _probes(text: str) -> List[str]:
    norm = _normalise(text)
    if len(norm) < LEAK_MIN_CHARS:
        return []
    if len(norm) <= LEAK_WINDOW:
        return [norm]
    starts = range(0, len(norm) - LEAK_WINDOW + 1, LEAK_STRIDE)
    return [norm[i : i + LEAK_WINDOW] for i in list(starts)[:LEAK_MAX_PROBES]]


def _size(text: str) -> SizeBucket:
    if len(text) <= SIZE_SHORT_MAX:
        return SizeBucket.SHORT
    if len(text) <= SIZE_MEDIUM_MAX:
        return SizeBucket.MEDIUM
    return SizeBucket.LONG


def _author_role(seg: PromptSegment) -> StubAuthorRole:
    role = seg.authn.role if seg.authn is not None else None
    try:
        return StubAuthorRole(role) if role else StubAuthorRole.UNAUTHENTICATED
    except ValueError:
        return StubAuthorRole.UNAUTHENTICATED


def _authority(seg: PromptSegment) -> StubAuthority:
    if seg.authz is not None and seg.authz.signature_verified:
        return StubAuthority.SIGNED
    if seg.kind == SegmentKind.RULE and seg.provenance in (RuleProvenance.USER_CHAT, RuleProvenance.WA_CHAT):
        return StubAuthority.ADVISORY
    return StubAuthority.NONE


def _check_layout(segments: Sequence[PromptSegment], layout: Sequence[LayoutMessage]) -> None:
    """A layout names every segment exactly once (a configuration error otherwise, in every mode)."""
    named = [i.segment_id for msg in layout for i in msg.items]
    ids = [s.segment_id for s in segments]
    if len(named) != len(set(named)) or set(named) != set(ids):
        missing = sorted(set(ids) - set(named))
        unknown = sorted(set(named) - set(ids))
        raise ValueError(f"layout must name each segment once (missing {missing}, unknown {unknown})")


def _join(
    items: Sequence[Tuple[PromptSegment, str]], rendered: Dict[str, str], withheld: Set[str]
) -> Tuple[str, List[Tuple[PromptSegment, Tuple[int, int]]]]:
    """One message's content and each segment's span. Consecutive stubs share one delimited block."""
    parts: List[str] = []
    spans: List[Tuple[PromptSegment, Tuple[int, int]]] = []
    cursor = 0
    in_block = False

    def emit(text: str) -> None:
        nonlocal cursor
        parts.append(text)
        cursor += len(text)

    for seg, glue in items:
        is_stub = seg.segment_id in withheld
        if in_block and not is_stub:
            emit("\n" + STUB_BLOCK_CLOSE)
            in_block = False
        if is_stub and in_block:
            emit("\n")
        else:
            if parts:
                emit(glue)
            if is_stub:
                emit(STUB_BLOCK_OPEN + "\n")
                in_block = True
        start = cursor
        emit(rendered[seg.segment_id])
        spans.append((seg, (start, cursor)))
    if in_block:
        emit("\n" + STUB_BLOCK_CLOSE)
    return "".join(parts), spans


__all__ = [
    "ASSEMBLER_VERSION",
    "AssemblyCall",
    "ContextPolicyViolation",
    "LayoutItem",
    "LayoutMessage",
    "PromptAssembler",
    "STUB_BLOCK_CLOSE",
    "STUB_BLOCK_OPEN",
    "neutralise",
    "quote_share",
    "current_guard_mode",
    "guard_mode_for_run_kind",
]
