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
"""

import hashlib
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.prompt_assembly.manifest_scope import messages_sha256
from ciris_engine.logic.prompt_assembly.policy import (
    ALWAYS_REQUIRED_KINDS,
    REQUIRING_PREDICATES,
    STAGE_ROLES,
    declared_trust,
    load_context_policy,
    predicate_holds,
)
from ciris_engine.logic.utils.mock_llm_guard import TraceRunKind, trace_run_kind
from ciris_engine.schemas.context.prompt_provenance import (
    AssemblyMode,
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

ASSEMBLER_VERSION = "1"
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
            required = row.kind in ALWAYS_REQUIRED_KINDS or row.predicate in REQUIRING_PREDICATES
            if required and predicate_holds(row.predicate, call.facts, retry) and key not in present:
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

    def render(self, seg: PromptSegment) -> str:
        """The bytes a segment occupies in the prompt (FSD §6)."""
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

    # ------------------------------------------------------------------ build

    def build(
        self,
        stage: PromptStage,
        segments: Sequence[PromptSegment],
        mode: Optional[AssemblyMode] = None,
        *,
        call: AssemblyCall,
    ) -> Tuple[List[LLMMessage], PromptManifest]:
        """Guard, order and render ``segments`` for ``stage``; returns (messages, manifest).

        ``mode`` None resolves from the process's run kind (:func:`current_guard_mode`).
        Raises :class:`ContextPolicyViolation` in FAIL_CLOSED mode on any violation.
        """
        mode = mode if mode is not None else current_guard_mode()
        kept, violations, trust = self._guard(stage, segments, call, mode)
        if violations:
            if mode == AssemblyMode.FAIL_CLOSED:
                raise ContextPolicyViolation(stage, violations)
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

        order = {row.key: i for i, row in enumerate(self._rows(stage))}
        ordered = sorted(kept, key=lambda s: (order[s.policy_key], s.order_key, s.segment_id))

        groups: Dict[str, List[Tuple[PromptSegment, str]]] = defaultdict(list)
        for seg in ordered:
            role = "user" if trust[seg.segment_id] == TrustLevel.UNTRUSTED else "system"
            groups[role].append((seg, self.render(seg)))

        messages: List[LLMMessage] = []
        records: List[SegmentRecord] = []
        for role in ("system", "user"):
            if not groups.get(role):
                continue
            index = len(messages)
            parts: List[str] = []
            cursor = 0
            for seg, text in groups[role]:
                if parts:
                    cursor += len(SEGMENT_SEPARATOR)
                start = cursor
                cursor += len(text)
                parts.append(text)
                spec = self.policy.kinds[seg.kind]
                records.append(
                    SegmentRecord(
                        segment_id=seg.segment_id,
                        kind=seg.kind,
                        provenance=seg.provenance,
                        source=seg.source,
                        trust=trust[seg.segment_id],
                        lifecycle=spec.lifecycle,
                        authn=seg.authn,
                        authz=seg.authz,
                        acct=seg.acct,
                        message_index=index,
                        span_start=start,
                        span_end=cursor,
                        sha256=_sha256(text),
                        truncated=seg.truncated,
                        derived_from=list(seg.derived_from),
                    )
                )
            messages.append(LLMMessage(role="system" if role == "system" else "user", content=SEGMENT_SEPARATOR.join(parts)))

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


__all__ = [
    "ASSEMBLER_VERSION",
    "AssemblyCall",
    "ContextPolicyViolation",
    "PromptAssembler",
    "current_guard_mode",
    "guard_mode_for_run_kind",
]
