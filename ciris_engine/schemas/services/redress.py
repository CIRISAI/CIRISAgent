"""Post-action redress — the governed corrective act (NULLWORKS RC3 finding F6).

The defect this addresses: CIRIS's reconsideration is **strictly forward-looking**.
PONDER, the recursive-ASPDMA retry, the conscience re-open and DEFER all fire
*before* the agent commits. Once a SPEAK has been read or a TOOL has run, there
is no governed way to say "that was wrong, and here is what stands instead".
The repo has known this: `compliance/README.md` cross-cutting finding #5, and
`compliance/D24_reconsideration.md` § "Current limitations" — *"no rollback
after SPEAK/TOOL; reconsideration strictly forward-looking via PONDER"*.

**This module is schema only. It contains no enforcement, and nothing writes a
redress record today.** No handler, route, service or persistence path calls
anything here. It is the *object* a redress workflow would record and the
*rules* that object must satisfy, so that the workflow phase has something to
key on. This mirrors ``TaskEnvelope`` (#938) Phase 1 deliberately — a
half-built corrective path that silently admits an unauthorized correction is
worse than none. See ``FSD/POST_ACTION_REDRESS.md``.

**Redress is not undo.** Nothing in this module reverses an external effect and
nothing here should be read as claiming it can. A message that was read stays
read; a payment that settled stays settled; a Discord post someone saw was
seen. The single field that can assert a carrier-level reversal
(:attr:`RedressRecord.reversibility` = ``CARRIER_REVERSED``) is unrepresentable
without naming the receipt that proves it — see
:meth:`RedressRecord._validate_record`. Everything else defaults to
``IRREVERSIBLE``, which is the truth for most actions.

Four schema-level properties, one per requirement in the finding:

1. **The original record is never touched.** There is no field anywhere in this
   module that references, edits or supersedes the original action's storage.
   A redress is an *additional* record naming the original. The original's
   tamper-evidence is the append-only, hash-chained audit log
   (``cirislens_audit_log``; the persist FFI exposes no update verb and no
   per-row delete), which is why :class:`ActionRef` points at an audit
   ``entry_id`` and ``entry_hash`` in preference to anything mutable.
2. **Authority is checked, not assumed.** :func:`admit_redress` is fail-closed:
   a record whose authority did not cryptographically verify cannot become
   governing. Authority rides the existing WA deferral rail (#944) — this
   module mints no second signing scheme and no second permission.
3. **Linkage is bidirectional by construction.** The redress names the original
   (:attr:`RedressRecord.target`); the original becomes discoverable as
   corrected because :func:`resolve_effective_state` answers from the target's
   side.
4. **"What stands now?" has one answer.** :func:`resolve_effective_state`
   computes it, and its inputs are the whole admitted chain, so the answer is
   always reconstructible rather than cached.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ciris_engine.schemas.services.authority_core import DeferralVerification
from ciris_engine.schemas.services.graph.audit import AuditEventData


class RedressDisposition(str, Enum):
    """What the corrective act says about the original action.

    Closed enumeration. Four of the five members project onto the CEG
    four-primitive retraction family already used in-repo by
    :class:`~ciris_engine.logic.services.governance.consent.attestation.RevocationIntent`
    (``recants`` / ``withdraws`` / ``supersedes``); see :attr:`ceg_primitive`.
    We reuse that vocabulary rather than inventing verbs, because
    ``compliance/D24_reconsideration.md`` already commits CIRIS to landing
    after-the-fact semantics on it once agent actions reach the federation
    chain.

    :attr:`UPHELD` is here for a reason that is easy to miss. A ledger that can
    only ever record "we were wrong" is a *biased* ledger: absence of a redress
    record would conflate "nobody ever looked" with "someone looked and it was
    fine". Those are different facts and a reader is entitled to both.
    """

    UPHELD = "upheld"
    """Reviewed after challenge and affirmed. The action stands as issued."""

    ANNOTATED = "annotated"
    """Qualified or contextualised without disavowal — e.g. accurate but
    incomplete. Does **not** change whether the action stands (see
    :data:`BINDING_DISPOSITIONS`)."""

    WITHDRAWN = "withdrawn"
    """No longer endorsed going forward; historically it stands and is not
    disavowed. CEG ``withdraws``."""

    SUPERSEDED = "superseded"
    """Replaced by a later action, which must be named. Read the compensating
    action instead. CEG ``supersedes``."""

    RETRACTED = "retracted"
    """Disavowed — the agent asserts it should not have acted as it did. The
    *effect* still happened; the *endorsement* is gone. CEG ``recants``."""

    @property
    def ceg_primitive(self) -> Optional[str]:
        """The CEG structural verb this projects onto, or ``None``.

        ``UPHELD`` and ``ANNOTATED`` have no analogue in the retraction family
        — that family only expresses degrees of taking something back. Returning
        ``None`` rather than forcing a nearest fit keeps a future federation
        emission honest.
        """
        return _CEG_PRIMITIVES.get(self)


_CEG_PRIMITIVES: Dict["RedressDisposition", str] = {
    RedressDisposition.WITHDRAWN: "withdraws",
    RedressDisposition.SUPERSEDED: "supersedes",
    RedressDisposition.RETRACTED: "recants",
}

BINDING_DISPOSITIONS: FrozenSet[RedressDisposition] = frozenset(
    {
        RedressDisposition.UPHELD,
        RedressDisposition.WITHDRAWN,
        RedressDisposition.SUPERSEDED,
        RedressDisposition.RETRACTED,
    }
)
"""Dispositions that change what stands, so "newest wins" applies to them.

``ANNOTATED`` is excluded on purpose. Under a naive newest-wins rule, adding a
clarifying note to an already-retracted action would silently un-retract it.
Annotations accumulate; they never govern.
"""


class RedressGrounds(str, Enum):
    """Why the corrective act was warranted.

    ``NEW_EVIDENCE`` and ``PROCEDURAL_ERROR`` are the upstream
    ``reconsideration:{grounds}`` vocabulary (CIRISRegistry FSD-002 §3.6.4, as
    cited by ``compliance/D24_reconsideration.md``). The third upstream ground,
    ``quorum_compromise``, is deliberately **absent**: it describes a defect in
    a federation vote and has no meaning for one agent's own external act.
    Carrying it would be vocabulary cargo-culting.

    The remaining members are agent-side grounds with no upstream analogue.
    """

    NEW_EVIDENCE = "new_evidence"
    """Information that was not available when the action was taken."""

    PROCEDURAL_ERROR = "procedural_error"
    """The decision process was defective — a skipped check, a mis-routed
    deferral, a conscience signal that was not honoured."""

    FACTUAL_ERROR = "factual_error"
    """The content of the action was wrong on the facts."""

    HARM_REPORTED = "harm_reported"
    """Someone reported harm arising from the action."""

    POLICY_VIOLATION = "policy_violation"
    """The action breached a policy or a prohibited-capability boundary."""

    CONSENT_WITHDRAWN = "consent_withdrawn"
    """The consent the action relied on was revoked."""

    AUTHORITY_DEFECT = "authority_defect"
    """The action exceeded the authority actually held — outside the task
    envelope, over budget, or taken without a required approval."""


class EffectReversibility(str, Enum):
    """What is true of the *external effect*, as a claim that must be earned.

    This axis exists to make overclaiming structurally hard. It is a separate
    field from :class:`RedressDisposition` because "we take it back" and "the
    world no longer shows it" are independent facts, and collapsing them is
    precisely the compliance-prose failure a redress workflow is prone to.
    """

    IRREVERSIBLE = "irreversible"
    """The effect cannot be undone. **The default, and the honest answer for
    most actions** — a message that was read, a tool that mutated remote state,
    a settled payment."""

    CARRIER_REVERSIBLE = "carrier_reversible"
    """The carrier offers a reversal affordance (delete the post, void the
    draft) but it was **not** exercised, or exercising it does not unmake the
    observation — someone may already have read it."""

    CARRIER_REVERSED = "carrier_reversed"
    """A carrier-level reversal was actually performed. Requires
    :attr:`RedressRecord.carrier_evidence_ref`; it is unrepresentable without
    the receipt. Even here the claim is bounded: the artefact is gone, the
    *observation* of it is not recoverable."""


class RedressAuthorityBasis(str, Enum):
    """How the authority to issue this redress was established.

    Only :attr:`WA_DEFERRAL_RESOLUTION` is admissible today. That is not a
    placeholder — it is the point. #944 made deferral resolutions hybrid-signed
    (Ed25519 + ML-DSA-65) and verified fail-closed at
    ``WiseAuthorityService.resolve_deferral`` before any state mutation. Routing
    redress authority through that rail means this module adds **no** signing
    code, **no** second verifier and **no** second permission: the authority to
    redress is exactly ``Permission.RESOLVE_DEFERRALS`` / ``WARole.AUTHORITY``,
    already gated and already tested against the real substrate.
    """

    WA_DEFERRAL_RESOLUTION = "wa_deferral_resolution"
    """A Wise Authority approved a deferral proposing this redress. The
    resolution's own signature is the authority evidence."""

    WA_DIRECT = "wa_direct"
    """A Wise Authority ordered the redress without a deferral to hang it on —
    the "an operator corrects the record after a complaint" case.

    **Representable but not admissible.** Making it work needs a signature over
    :func:`redress_authorization_payload`, which means a second signing verb;
    that is deliberately not in this phase.
    :func:`admit_redress` refuses it with
    :attr:`RedressRefusalReason.AUTHORITY_BASIS_NOT_IMPLEMENTED` rather than
    letting an unverified claim through. It is representable so that the state
    model is complete and the refusal has a name, not so that it can be used.
    """


class RedressRefusalReason(str, Enum):
    """Why :func:`admit_redress` declined to let a record govern."""

    AUTHORITY_BASIS_NOT_IMPLEMENTED = "authority_basis_not_implemented"
    AUTHORITY_UNVERIFIED = "authority_unverified"
    """Signature material absent — a pre-signing legacy row. Not an attack."""

    AUTHORITY_VERIFICATION_FAILED = "authority_verification_failed"
    """Signature present and did not check out. An attack or a corruption."""

    MISSING_AUTHORIZING_DEFERRAL = "missing_authorizing_deferral"


class ActionStanding(str, Enum):
    """The resolved answer to "what stands now?" for one external action."""

    UNCHALLENGED = "unchallenged"
    """No admitted redress record names this action. **Not** the same as
    ``UPHELD``: nobody has reviewed it."""

    UPHELD = "upheld"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"

    @property
    def endorsed(self) -> bool:
        """Whether the agent still stands behind the action's content.

        ``WITHDRAWN`` is deliberately ``False`` while remaining historically
        valid: withdrawal is "not going forward", not "this never happened".
        """
        return self in (ActionStanding.UNCHALLENGED, ActionStanding.UPHELD)


_STANDING_FOR_DISPOSITION: Dict[RedressDisposition, ActionStanding] = {
    RedressDisposition.UPHELD: ActionStanding.UPHELD,
    RedressDisposition.WITHDRAWN: ActionStanding.WITHDRAWN,
    RedressDisposition.SUPERSEDED: ActionStanding.SUPERSEDED,
    RedressDisposition.RETRACTED: ActionStanding.RETRACTED,
}


class ActionRef(BaseModel):
    """A pointer to a completed external action.

    Prefers the audit chain. ``AuditEntryResult.entry_id`` is the strongest
    identifier a completed action has in this system: every dispatched action
    gets one (including TOOL, which writes no service correlation at all), the
    chain is append-only and hash-linked, and ``entry_hash`` makes the
    reference content-addressed.

    It is nonetheless **optional**, because of a real gap:
    ``action_dispatcher.py`` logs ``audit_data.entry_id`` and discards it — it
    is not written onto the thought or task row, so recovering it for a past
    action needs a chain scan. Requiring it would make redress unrepresentable
    for every action taken before that is fixed. So the model accepts the
    weaker ``(task_id, thought_id)`` identity and exposes
    :attr:`is_chain_anchored` so a reader can see which kind of reference they
    are looking at instead of having to guess.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_entry_id: Optional[str] = Field(
        None, description="AuditEntryResult.entry_id of the original action. The preferred anchor."
    )
    audit_entry_hash: Optional[str] = Field(
        None, description="entry_hash of that chain row, making the reference content-addressed"
    )
    audit_sequence_number: Optional[int] = Field(
        None, ge=0, description="Chain position of that row, for ordering and proof requests"
    )
    task_id: Optional[str] = Field(None, description="Task the action was dispatched under")
    thought_id: Optional[str] = Field(None, description="Thought that selected the action")
    action_type: Optional[str] = Field(None, description="HandlerActionType value, e.g. 'speak' or 'tool'")
    agent_occurrence_id: Optional[str] = Field(None, description="Occurrence that executed it")
    channel_id: Optional[str] = Field(None, description="Surface the effect landed on, when there was one")

    @model_validator(mode="after")
    def _validate_ref(self) -> "ActionRef":
        anchored = bool((self.audit_entry_id or "").strip())
        paired = bool((self.task_id or "").strip()) and bool((self.thought_id or "").strip())
        if not anchored and not paired:
            raise ValueError(
                "ActionRef must identify an action: either audit_entry_id, or both task_id and thought_id. "
                "A redress that cannot say what it corrects is not a redress."
            )
        if self.audit_entry_hash and not anchored:
            raise ValueError("audit_entry_hash without audit_entry_id does not reference anything")
        return self

    @property
    def is_chain_anchored(self) -> bool:
        """True when this points at the tamper-evident audit chain by hash.

        A reference that is merely ``(task_id, thought_id)`` resolves through
        mutable rows; a chain-anchored one does not. Both are admissible; they
        are not equally strong evidence, and this is how a reader tells.
        """
        return bool((self.audit_entry_id or "").strip()) and bool((self.audit_entry_hash or "").strip())

    @property
    def identity_key(self) -> str:
        """Stable key used to group redress records onto one action.

        ALWAYS the task/thought pair, never the audit id — even though the
        audit anchor is the stronger reference. Both forms are valid ways to
        name the same action: a redress raised from the audit chain carries
        the anchor, while the task rows a query starts from often have only
        the pair. Keying on whichever is present made those two spellings hash
        apart, so a redress stored under `audit:...` was invisible to a lookup
        holding `tt:...` and the action came back UNCHALLENGED — the one
        answer this type exists to make impossible.

        The pair is therefore preferred WHENEVER IT IS PRESENT, on both the
        strong and the weak form, so the two spellings of one action agree.

        It is not preferred unconditionally. The validator accepts an
        audit-only reference, and keying those on the pair yields
        ``tt:None:None`` for every one of them — so two entirely unrelated
        audit-only actions would collide and a redress recorded for one could
        govern the other. That is a worse failure than the one being fixed:
        the first makes a redress invisible, this one makes it apply to the
        wrong action. Audit-only references keep the anchor as their key.

        The residue is honest and irreducible: an audit-only reference and a
        pair reference to the same action still do not match. An audit-only
        reference carries nothing to reconcile them WITH — the pair is simply
        not there — so no keying scheme could relate them. What matters is
        that nothing silently collides.
        """
        has_pair = bool((self.task_id or "").strip()) and bool((self.thought_id or "").strip())
        if has_pair:
            return f"tt:{self.task_id}:{self.thought_id}"
        if (self.audit_entry_id or "").strip():
            return f"audit:{self.audit_entry_id}"
        # The validator should make this unreachable; do not let it degrade into
        # a shared constant that silently groups unrelated actions together.
        raise ValueError("ActionRef carries neither a task/thought pair nor an audit anchor")


class RedressAuthority(BaseModel):
    """Who authorized the correction, and on what evidence.

    Carries **no signature fields of its own**. The signature lives where #944
    put it — on the deferral resolution stored in the task's
    ``context["deferral"]["resolution"]`` — and this model records the pointer
    to it plus the verdict the existing verifier reached. Copying signature
    bytes here would create a second place they could drift from, and a second
    thing to verify.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    basis: RedressAuthorityBasis = Field(..., description="How authority was established")
    wa_id: str = Field(..., description="The Wise Authority that authorized the correction")
    authorizing_deferral_id: Optional[str] = Field(
        None, description="deferral_id whose signed resolution is the authority evidence"
    )
    verification: DeferralVerification = Field(
        DeferralVerification.UNSIGNED,
        description=(
            "Verdict from AuthenticationService.verify_deferral_resolution, carried verbatim. "
            "Reuses the #944 three-state enum so 'unsigned legacy row' and 'signature failed' "
            "stay distinguishable here exactly as they do there."
        ),
    )

    @field_validator("wa_id")
    @classmethod
    def _validate_wa_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("a redress must name the authority that issued it")
        return v

    @model_validator(mode="after")
    def _validate_authority(self) -> "RedressAuthority":
        if self.basis is RedressAuthorityBasis.WA_DEFERRAL_RESOLUTION and not (
            self.authorizing_deferral_id or ""
        ).strip():
            raise ValueError("WA_DEFERRAL_RESOLUTION authority must name the deferral it rests on")
        if self.basis is RedressAuthorityBasis.WA_DIRECT and (self.authorizing_deferral_id or "").strip():
            raise ValueError("WA_DIRECT authority does not rest on a deferral; do not name one")
        return self


class CompensatingAction(BaseModel):
    """The follow-up action actually emitted to carry the correction outward.

    A redress that only writes a ledger row corrects the *record*. It does not
    tell the person who read the original. When the correction was actually
    communicated, this names the action that did it — and that action is an
    ordinary SPEAK or TOOL with its own audit entry, subject to the same
    conscience and envelope checks as any other. **Redress grants no special
    execution path**; that is what keeps it from becoming a bypass.

    It is optional because a correction is sometimes purely internal (nobody
    external saw the original) and sometimes impossible to deliver (the channel
    is gone, the recipient unreachable). Absent means "not communicated" — never
    "communicated silently".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: ActionRef = Field(..., description="The emitted corrective action")
    delivered: bool = Field(
        False,
        description=(
            "The corrective action reached the surface the original landed on. False when it was "
            "attempted and failed, or emitted to a different surface."
        ),
    )
    note: Optional[str] = Field(None, description="Why delivery failed or landed elsewhere, when it did")


class RedressRecord(BaseModel):
    """One corrective act, recorded additively against one original action.

    Immutable (``frozen=True``). There is no edit path and no retract-a-redress
    field: a redress that was itself wrong is corrected by *another* redress
    naming it via :attr:`amends`. The ledger only ever grows, which is what
    makes the sequence auditable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, defer_build=True)

    redress_id: str = Field(..., description="Unique identifier for this corrective act")
    recorded_at: str = Field(..., description="ISO-8601 instant the redress was recorded")
    target: ActionRef = Field(..., description="The original external action being corrected")
    disposition: RedressDisposition = Field(..., description="What this says about the original")
    grounds: RedressGrounds = Field(..., description="Why the correction was warranted")
    statement: str = Field(
        ...,
        description=(
            "Plain-language account of what is being corrected and to what. Required: a redress "
            "whose meaning is only readable from an enum is not legible to the person it is for."
        ),
    )
    authority: RedressAuthority = Field(..., description="Who authorized it, and on what evidence")
    reversibility: EffectReversibility = Field(
        EffectReversibility.IRREVERSIBLE,
        description="What is true of the external effect. Defaults to the honest answer.",
    )
    carrier_evidence_ref: Optional[str] = Field(
        None,
        description=(
            "Receipt for a carrier-level reversal — a deletion confirmation id, a void reference. "
            "Required by CARRIER_REVERSED so the strongest claim cannot be made bare."
        ),
    )
    compensating_action: Optional[CompensatingAction] = Field(
        None, description="The follow-up action that carried the correction outward, if one was emitted"
    )
    amends: Optional[str] = Field(
        None,
        description=(
            "redress_id of an earlier record in this action's chain that this one corrects. "
            "Provenance only — ordering still governs which record is effective."
        ),
    )

    @field_validator("redress_id", "recorded_at", "statement")
    @classmethod
    def _validate_required_str(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v

    @model_validator(mode="after")
    def _validate_record(self) -> "RedressRecord":
        if self.reversibility is EffectReversibility.CARRIER_REVERSED and not (self.carrier_evidence_ref or "").strip():
            raise ValueError(
                "CARRIER_REVERSED asserts the external artefact was actually removed. "
                "It requires carrier_evidence_ref — the claim is not makeable without the receipt."
            )
        if self.disposition is RedressDisposition.SUPERSEDED and self.compensating_action is None:
            raise ValueError(
                "SUPERSEDED means 'read this other thing instead'. Without a compensating_action "
                "naming that thing it says nothing a reader can act on."
            )
        if self.amends is not None and self.amends == self.redress_id:
            raise ValueError("a redress cannot amend itself")
        return self

    @property
    def is_binding(self) -> bool:
        """Whether this record participates in newest-wins resolution."""
        return self.disposition in BINDING_DISPOSITIONS

    @property
    def external_effect_undone(self) -> bool:
        """True only for an evidenced carrier reversal.

        Deliberately narrow, and deliberately *not* implied by ``RETRACTED``.
        Retracting is something the agent does to its own endorsement; it does
        nothing to the world. Even ``True`` here means "the artefact was
        removed", never "the observation was unmade".
        """
        return self.reversibility is EffectReversibility.CARRIER_REVERSED


class RedressAdmission(BaseModel):
    """The fail-closed verdict on whether a record may govern.

    Refusal does not erase the record. A refused redress stays visible in
    :attr:`ActionEffectiveState.refused` — a correction that failed its
    authority check is itself a fact worth seeing, and dropping it silently
    would hide exactly the events most worth noticing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    redress_id: str = Field(..., description="Record this verdict is about")
    admitted: bool = Field(..., description="Whether the record may affect what stands")
    refusal: Optional[RedressRefusalReason] = Field(None, description="Why not, when not admitted")
    detail: Optional[str] = Field(None, description="Human-readable expansion of the refusal")

    @model_validator(mode="after")
    def _validate_admission(self) -> "RedressAdmission":
        if self.admitted and self.refusal is not None:
            raise ValueError("an admitted record has no refusal reason")
        if not self.admitted and self.refusal is None:
            raise ValueError("a refusal must say why")
        return self


def admit_redress(record: RedressRecord) -> RedressAdmission:
    """Decide whether ``record`` may change what stands. Fail-closed.

    Only ``WA_DEFERRAL_RESOLUTION`` authority whose signature actually verified
    is admitted. ``UNSIGNED`` is refused here even though
    ``WiseAuthorityService.resolve_deferral`` lets an unsigned *deferral*
    through: that leniency exists for rows written before #944 shipped, and no
    redress row predates this module, so there is no migration debt to be
    lenient about. Starting strict is free exactly once.

    This is a **schema-level** gate. Nothing calls it on any execution path
    today, because nothing produces redress records yet. It is written now so
    that the phase which does cannot accidentally admit an unauthorized
    correction, and so the property is testable before there is a workflow.
    """
    auth = record.authority

    if auth.basis is RedressAuthorityBasis.WA_DIRECT:
        return RedressAdmission(
            redress_id=record.redress_id,
            admitted=False,
            refusal=RedressRefusalReason.AUTHORITY_BASIS_NOT_IMPLEMENTED,
            detail=(
                "WA_DIRECT needs a signature over redress_authorization_payload and a verifier for it. "
                "Neither ships in this phase; see FSD/POST_ACTION_REDRESS.md §7."
            ),
        )

    if not (auth.authorizing_deferral_id or "").strip():
        return RedressAdmission(
            redress_id=record.redress_id,
            admitted=False,
            refusal=RedressRefusalReason.MISSING_AUTHORIZING_DEFERRAL,
            detail="No deferral named, so there is nothing whose signature could be checked.",
        )

    if auth.verification is DeferralVerification.FAILED:
        return RedressAdmission(
            redress_id=record.redress_id,
            admitted=False,
            refusal=RedressRefusalReason.AUTHORITY_VERIFICATION_FAILED,
            detail=f"Deferral {auth.authorizing_deferral_id} carries a signature that did not verify.",
        )

    if auth.verification is not DeferralVerification.VERIFIED:
        return RedressAdmission(
            redress_id=record.redress_id,
            admitted=False,
            refusal=RedressRefusalReason.AUTHORITY_UNVERIFIED,
            detail=f"Deferral {auth.authorizing_deferral_id} carries no verifiable signature.",
        )

    return RedressAdmission(redress_id=record.redress_id, admitted=True)


class ActionEffectiveState(BaseModel):
    """What stands now for one external action, and how that was arrived at.

    Never cached and never stored — it is recomputed from the chain, so it
    cannot drift from the records that justify it. A reader who disagrees with
    :attr:`standing` can inspect :attr:`chain` and see exactly which record
    produced it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_key: str = Field(..., description="ActionRef.identity_key this state is about")
    standing: ActionStanding = Field(..., description="The resolved answer to 'what stands now?'")
    governing_redress_id: Optional[str] = Field(
        None, description="The admitted binding record that produced this standing; None when unchallenged"
    )
    reviewed: bool = Field(
        ...,
        description=(
            "Any admitted record names this action. Distinguishes 'nobody looked' from "
            "'someone looked'; UNCHALLENGED implies False."
        ),
    )
    reversibility: EffectReversibility = Field(
        EffectReversibility.IRREVERSIBLE, description="Effect claim from the governing record"
    )
    compensating_action: Optional[CompensatingAction] = Field(
        None, description="Corrective action named by the governing record, if any"
    )
    annotations: Tuple[str, ...] = Field(
        default_factory=tuple, description="Statements of admitted ANNOTATED records, in order"
    )
    chain: Tuple[str, ...] = Field(
        default_factory=tuple, description="Every admitted redress_id naming this action, in resolution order"
    )
    refused: Tuple[RedressAdmission, ...] = Field(
        default_factory=tuple, description="Records that named this action but were not admitted"
    )

    @property
    def endorsed(self) -> bool:
        """Whether the agent still stands behind the original action's content."""
        return self.standing.endorsed

    @property
    def external_effect_undone(self) -> bool:
        """True only when the governing record evidenced a carrier reversal."""
        return self.reversibility is EffectReversibility.CARRIER_REVERSED


def _sort_key(record: RedressRecord) -> Tuple[str, str]:
    """Resolution order: recorded_at, then redress_id to break ties.

    ``recorded_at`` is an ISO-8601 string and sorts lexicographically only when
    the instants are normalised (same offset, same precision). Records written
    by different occurrences against a shared database can carry skewed clocks,
    which is a real hazard named in ``FSD/POST_ACTION_REDRESS.md`` §8 — the
    ``redress_id`` tie-break makes the order *deterministic*, not *correct*.
    """
    return (record.recorded_at, record.redress_id)


def resolve_effective_state(
    target: ActionRef,
    records: Iterable[RedressRecord],
) -> ActionEffectiveState:
    """Answer "what stands now?" for ``target``.

    Rules, in order:

    1. Filter to records naming ``target`` (by :attr:`ActionRef.identity_key`).
    2. Admit each via :func:`admit_redress`. **A refused record cannot change
       standing** — it stays visible in :attr:`ActionEffectiveState.refused`.
    3. Sort admitted records by :func:`_sort_key`.
    4. The newest *binding* record governs (see :data:`BINDING_DISPOSITIONS`).
       ``ANNOTATED`` records accumulate and never govern.
    5. No admitted binding record → ``UNCHALLENGED``.

    Admission runs *inside* this function rather than being the caller's job.
    That is the whole point: there is no way to call this and accidentally let
    an unauthorized correction count.
    """
    key = target.identity_key
    mine: Sequence[RedressRecord] = [r for r in records if r.target.identity_key == key]

    admitted: List[RedressRecord] = []
    refused: List[RedressAdmission] = []
    for record in sorted(mine, key=_sort_key):
        verdict = admit_redress(record)
        if verdict.admitted:
            admitted.append(record)
        else:
            refused.append(verdict)

    governing: Optional[RedressRecord] = None
    for record in admitted:
        if record.is_binding:
            governing = record  # sorted ascending, so the last binding record wins

    annotations = tuple(r.statement for r in admitted if r.disposition is RedressDisposition.ANNOTATED)

    if governing is None:
        return ActionEffectiveState(
            target_key=key,
            standing=ActionStanding.UNCHALLENGED,
            governing_redress_id=None,
            reviewed=bool(admitted),
            reversibility=EffectReversibility.IRREVERSIBLE,
            compensating_action=None,
            annotations=annotations,
            chain=tuple(r.redress_id for r in admitted),
            refused=tuple(refused),
        )

    return ActionEffectiveState(
        target_key=key,
        standing=_STANDING_FOR_DISPOSITION[governing.disposition],
        governing_redress_id=governing.redress_id,
        reviewed=True,
        reversibility=governing.reversibility,
        compensating_action=governing.compensating_action,
        annotations=annotations,
        chain=tuple(r.redress_id for r in admitted),
        refused=tuple(refused),
    )


def redress_authorization_payload(record: RedressRecord, signed_at: str) -> Dict[str, object]:
    """The exact fields a WA signature would commit to for a ``WA_DIRECT`` redress.

    Defined here, unused today, for the same reason
    :func:`~ciris_engine.schemas.services.authority_core.deferral_resolution_payload`
    exists as ONE function: when the signer and the verifier each build their
    canonical dict inline they drift apart silently, and the only symptom is a
    signature that stops verifying with no indication why. Whoever implements
    ``WA_DIRECT`` gets the shape handed to them rather than inventing a second
    one.

    It commits to the corrective *decision* — which redress, against which
    action, saying what, on what grounds, by whom, when — so a signature cannot
    be lifted onto a different target or a different disposition, and
    ``signed_at`` inside the payload stops it being replayed onto another
    moment.

    Note what this does **not** solve: for ``WA_DEFERRAL_RESOLUTION`` authority
    the signed payload is the deferral's, which commits to the verdict and not
    to the redress body. See ``FSD/POST_ACTION_REDRESS.md`` §8.
    """
    return {
        "redress_id": record.redress_id,
        "target_key": record.target.identity_key,
        "target_entry_hash": record.target.audit_entry_hash,
        "disposition": record.disposition.value,
        "grounds": record.grounds.value,
        "statement": record.statement,
        "wa_id": record.authority.wa_id,
        "signed_at": signed_at,
    }


def redress_audit_event_data(record: RedressRecord) -> AuditEventData:
    """Flatten a redress record for the append-only, hash-chained audit log.

    Reuses :class:`~ciris_engine.schemas.services.graph.audit.AuditEventData`
    rather than minting a storage shape. That log is the repo's tamper-evidence
    primitive — the persist FFI exposes ``audit_record_entry`` but no update
    verb and no per-row delete — so recording the corrective act there gives it
    the same append-only guarantee the original action already has, with no new
    table and no persist wheel cut.

    ``metadata`` is typed ``Dict[str, Union[str, int, float, bool]]``, so every
    value below is a scalar by construction. Optional fields are omitted rather
    than written as ``"None"``, so a reader can tell absent from empty.

    **This function does not write anything.** It produces the payload a caller
    would hand to ``GraphAuditService.log_event``. Wiring that call is the
    workflow phase; see ``FSD/POST_ACTION_REDRESS.md`` §7.
    """
    metadata: Dict[str, Union[str, int, float, bool]] = {
        "redress_id": record.redress_id,
        "recorded_at": record.recorded_at,
        "disposition": record.disposition.value,
        "grounds": record.grounds.value,
        "statement": record.statement,
        "reversibility": record.reversibility.value,
        "external_effect_undone": record.external_effect_undone,
        "target_key": record.target.identity_key,
        "target_chain_anchored": record.target.is_chain_anchored,
        "authority_basis": record.authority.basis.value,
        "authority_wa_id": record.authority.wa_id,
        "authority_verification": record.authority.verification.value,
        "admitted": admit_redress(record).admitted,
    }
    ceg = record.disposition.ceg_primitive
    if ceg is not None:
        metadata["ceg_primitive"] = ceg
    if record.target.audit_entry_id:
        metadata["target_audit_entry_id"] = record.target.audit_entry_id
    if record.target.audit_entry_hash:
        metadata["target_audit_entry_hash"] = record.target.audit_entry_hash
    if record.target.audit_sequence_number is not None:
        metadata["target_audit_sequence_number"] = record.target.audit_sequence_number
    if record.target.task_id:
        metadata["target_task_id"] = record.target.task_id
    if record.target.thought_id:
        metadata["target_thought_id"] = record.target.thought_id
    if record.target.action_type:
        metadata["target_action_type"] = record.target.action_type
    if record.authority.authorizing_deferral_id:
        metadata["authorizing_deferral_id"] = record.authority.authorizing_deferral_id
    if record.carrier_evidence_ref:
        metadata["carrier_evidence_ref"] = record.carrier_evidence_ref
    if record.amends:
        metadata["amends"] = record.amends
    if record.compensating_action is not None:
        metadata["compensating_action_key"] = record.compensating_action.action.identity_key
        metadata["compensating_action_delivered"] = record.compensating_action.delivered

    return AuditEventData(
        entity_id=record.target.identity_key,
        actor=record.authority.wa_id,
        outcome="success",
        severity="warning" if record.disposition is not RedressDisposition.UPHELD else "info",
        action=f"redress_{record.disposition.value}",
        resource=record.target.audit_entry_id or record.target.identity_key,
        reason=record.grounds.value,
        metadata=metadata,
    )


__all__ = [
    "BINDING_DISPOSITIONS",
    "ActionEffectiveState",
    "ActionRef",
    "ActionStanding",
    "CompensatingAction",
    "EffectReversibility",
    "RedressAdmission",
    "RedressAuthority",
    "RedressAuthorityBasis",
    "RedressDisposition",
    "RedressGrounds",
    "RedressRecord",
    "RedressRefusalReason",
    "admit_redress",
    "redress_audit_event_data",
    "redress_authorization_payload",
    "resolve_effective_state",
]
