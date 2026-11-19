"""The decision contract between consciences and the retry (CIRISAgent#1366 items 7-9).

A conscience veto used to be a free-text reason, read by the retry as fact
whatever its kind: an "I cannot see this rule" objection was read as "the rule
is a hallucination". Every objection is now typed, carries an id and the
conscience that raised it, says whether that conscience held trusted Wise
Authority governance, and is kept for the whole task.

Lives beside ``task_envelope`` (not under ``schemas/conscience``) because the
task row carries the record, and ``schemas/conscience`` imports the runtime
models: a dependency-free module keeps that import one-way.

See FSD/PROMPT_CONTEXT_PROVENANCE.md §9 and formal/h3ere_ctxflow (Judge:
typed verdicts, banned, discharged, attached).
"""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ObjectionType(str, Enum):
    """What kind of objection a veto is. Each has its own response (#1366 item 7)."""

    #: The conscience cannot see the authority for a rule the draft relies on.
    #: Only the SYSTEM discharges it, from trusted state; never the drafter.
    EVIDENCE = "evidence"
    #: The justification is insufficient. The drafter may restate it.
    JUSTIFICATION = "justification"
    #: An ethical, safety or coherence objection to the action itself. The
    #: action must change: an identical re-proposal is vetoed again.
    SUBSTANTIVE = "substantive"


def coerce_objection_type(value: object) -> ObjectionType:
    """The objection type a model answered, or SUBSTANTIVE (fail safe).

    Never raises: an unknown or missing type must not send the gate into a
    reask, and must never weaken a veto into something the drafter can argue
    away. Only an exact evidence/justification answer is read as one.
    """
    if isinstance(value, ObjectionType):
        return value
    if isinstance(value, str):
        raw = value.strip().lower().strip("\"'.").rsplit(".", 1)[-1]
        for member in ObjectionType:
            if raw == member.value:
                return member
    return ObjectionType.SUBSTANTIVE


class VetoObjection(BaseModel):
    """One conscience's typed objection to one draft."""

    veto_id: str = Field(..., description="Unique id of this veto")
    conscience: str = Field(..., description="Registry name of the objecting conscience")
    objection_type: ObjectionType = Field(..., description="evidence, justification or substantive")
    reason: str = Field("", description="The conscience's stated reason")
    held_trusted_rule: bool = Field(
        False, description="Whether the conscience held trusted WA governance (signed guidance or amendments)"
    )
    held_evidence_ids: List[str] = Field(
        default_factory=list, description="Ids of the trusted governance entries the conscience held"
    )
    action_fingerprint: str = Field(..., description="Reviewed-action fingerprint of the vetoed draft (sha256:...)")
    equivalence_key: str = Field(
        "", description="Ban-equivalence key (verb:tool:normalized hash); the ban matches on this"
    )

    model_config = ConfigDict(extra="forbid")


class VetoDischarge(BaseModel):
    """Why a veto stopped applying (#1366 item 9). Only the system writes these."""

    veto_id: str = Field(..., description="The veto that was discharged")
    conscience: str = Field(..., description="The conscience that had raised it")
    kind: Literal["new_evidence", "changed_action"] = Field(..., description="What changed")
    discharged_by: str = Field(
        ..., description="Trusted evidence id (WA authorization / amendment) or the changed action's fingerprint"
    )

    model_config = ConfigDict(extra="forbid")


class VetoRecordEntry(BaseModel):
    """One veto as the task keeps it: what was vetoed, by whom, of what kind."""

    veto_id: str = Field(..., description="Unique id of this veto")
    thought_id: Optional[str] = Field(None, description="The thought whose draft was vetoed")
    action_fingerprint: str = Field(..., description="Reviewed-action fingerprint of the vetoed draft")
    equivalence_key: str = Field(
        "",
        description=(
            "Ban-equivalence key of the vetoed draft. Empty on a record written before the "
            "fingerprint/key split, whose action_fingerprint is that key"
        ),
    )
    action_summary: str = Field("", description="Short description of the vetoed draft, for the drafters")
    objection_type: ObjectionType = Field(..., description="evidence, justification or substantive")
    conscience: str = Field(..., description="Registry name of the objecting conscience")
    reason: str = Field("", description="The conscience's stated reason")
    held_evidence_ids: List[str] = Field(
        default_factory=list, description="Trusted governance ids the conscience held when it objected"
    )
    banned: bool = Field(
        ...,
        description=(
            "True when an identical re-proposal is vetoed again without review: a substantive "
            "objection, or an evidence objection no trusted state discharged"
        ),
    )
    discharged_by: Optional[str] = Field(None, description="Set when the system discharged this veto")

    model_config = ConfigDict(extra="forbid")


class VetoChange(BaseModel):
    """What changed when a draft passed after earlier vetoes in the task (#1366 item 9).

    Without it a pass after a veto is indistinguishable from sampling noise.
    """

    prior_veto_ids: List[str] = Field(default_factory=list, description="Vetoes earlier in this task")
    change: Literal["new_evidence", "changed_action", "unchanged"] = Field(
        ..., description="new trusted evidence, a different action, or neither (a restated justification)"
    )
    evidence_ids: List[str] = Field(default_factory=list, description="Trusted evidence attached on re-review")
    action_fingerprint: str = Field(..., description="Reviewed-action fingerprint of the draft that passed")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ObjectionType",
    "VetoChange",
    "VetoDischarge",
    "VetoObjection",
    "VetoRecordEntry",
    "coerce_objection_type",
]
