"""Typed records for the signed CEG rows a Wise Authority deferral leaves (CIRISAgent#1316).

The node (ciris_server >= 0.5.234) builds and signs three rows; the agent only
calls it at the right moments and keeps the returned ids:

- ``deferral:request:v1`` when the agent defers (occurrence key, about the agent);
- ``deferral:response:{approved|rejected}:v1`` when a Wise Authority answers
  (the resolver's OWN key; ``references_attestation_id`` -> the request);
- ``identity_amendment:v1`` when the approved identity change is applied
  (occurrence key; ``authorized_by`` / ``evidence_refs`` -> the response).

The seam that calls the node is
``ciris_engine/logic/services/governance/wise_authority/deferral_rows.py``.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

#: The row dimensions, as the Constitution (rc10) names them.
DEFERRAL_REQUEST_DIMENSION = "deferral:request:v1"
DEFERRAL_APPROVED_DIMENSION = "deferral:response:approved:v1"
DEFERRAL_REJECTED_DIMENSION = "deferral:response:rejected:v1"
IDENTITY_AMENDMENT_DIMENSION = "identity_amendment:v1"
DEFERRAL_ROW_DIMENSIONS = (
    DEFERRAL_REQUEST_DIMENSION,
    DEFERRAL_APPROVED_DIMENSION,
    DEFERRAL_REJECTED_DIMENSION,
    IDENTITY_AMENDMENT_DIMENSION,
)

#: The node's reason ids the agent branches on.
REASON_UNKNOWN_REQUEST = "deferral.unknown_request"
REASON_AMENDMENT_UNAUTHORIZED = "identity_amendment_unauthorized"
#: Set by the agent, never by the node: the approval carries no response row.
REASON_NO_RESPONSE_ROW = "deferral.no_response_row"
#: Set by the agent: the node answered with a message that is not "<reason_id>: <text>".
REASON_UNPARSED = "unparsed"
#: Set by the agent: the node did not answer within the call's timeout (an outage).
REASON_TIMEOUT = "deferral.timeout"


class DeferralRowRefusalKind(str, Enum):
    """How the node refused, from the exception class it raised."""

    INVALID = "invalid"  # ValueError: bad input, or an unknown request
    REFUSED = "refused"  # PermissionError: an authority refusal
    OUTAGE = "outage"  # RuntimeError (or a timeout): the store did not answer; not a verdict


class DeferralRowRefusal(BaseModel):
    """The node's ``"<reason_id>: <text>"`` refusal, parsed."""

    reason_id: str = Field(..., description="The node's stable reason id, e.g. deferral.store")
    text: str = Field("", description="The node's explanation")
    kind: DeferralRowRefusalKind = Field(..., description="invalid / refused / outage")

    model_config = ConfigDict(extra="forbid", frozen=True)


class DeferralRowStatus(str, Enum):
    """Whether a deferral got its signed request row."""

    EMITTED = "emitted"  # the node signed and stored it; attestation_id is set
    UNAVAILABLE = "unavailable"  # this node has no deferral rows (server < 0.5.234, or no node)
    FAILED = "failed"  # the node refused or did not answer; the deferral stands without a row


class DeferralRequestRow(BaseModel):
    """The request row's outcome, stored with the deferral at ``context["deferral"]["request_row"]``."""

    status: DeferralRowStatus = Field(..., description="emitted / unavailable / failed")
    attestation_id: Optional[str] = Field(None, description="The deferral:request:v1 row, when emitted")
    reason_id: Optional[str] = Field(None, description="Why there is no row, when it failed")
    room_id: Optional[str] = Field(None, description="The room the row was placed in; None until #1300")

    model_config = ConfigDict(extra="forbid")


class DeferralRowView(BaseModel):
    """One of the three rows, read back from the node's store (GET /v1/wa/rows/{id})."""

    attestation_id: str
    attestation_type: str = Field(..., description="The row's dimension, e.g. deferral:request:v1")
    attesting_key_id: str = Field(..., description="Who signed it")
    attested_key_id: str = Field(..., description="Whom it is about (the agent's identity)")
    asserted_at: str
    deferral_id: Optional[str] = None
    reason_digest: Optional[str] = None
    references_attestation_id: Optional[str] = Field(None, description="On a response: the request it answers")
    amendment_digest: Optional[str] = None
    authorized_by: Optional[str] = Field(None, description="On an amendment: the approved response")
    evidence_refs: List[str] = Field(default_factory=list)
    room_id: Optional[str] = Field(None, description="The envelope's community_key_id, when the row has a room")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "DEFERRAL_APPROVED_DIMENSION",
    "DEFERRAL_REJECTED_DIMENSION",
    "DEFERRAL_REQUEST_DIMENSION",
    "DEFERRAL_ROW_DIMENSIONS",
    "IDENTITY_AMENDMENT_DIMENSION",
    "REASON_AMENDMENT_UNAUTHORIZED",
    "REASON_NO_RESPONSE_ROW",
    "REASON_TIMEOUT",
    "REASON_UNKNOWN_REQUEST",
    "REASON_UNPARSED",
    "DeferralRequestRow",
    "DeferralRowRefusal",
    "DeferralRowRefusalKind",
    "DeferralRowStatus",
    "DeferralRowView",
]
