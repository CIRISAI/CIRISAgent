"""Code admission for units loaded beyond the attested build (rc21 CC 2.7.11, `admission:unit`).

A unit inside the attested build (the agent wheel's own adapters and tools,
checked by CIRISVerify file integrity) runs under the build's attestation and is
not admitted here. Everything that loads BEYOND it (imported skills, adapters
discovered outside the installed package, tools those units register) runs only
under a live `admission:unit` row naming the exact digest that is loaded.

The rows themselves are read through ONE adapter function
(`unit_admission.read_admission_rows`); these are the shapes it returns and the
answer the host gives.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field

#: CC 2.7.11 constant: a lease never runs longer than this, from `asserted_at`
#: and from the instant the host first held the row.
UNIT_LEASE_MAX_SECS = 86400

#: `sub` of an admission row, and how a unit digest is written on the wire.
UNIT_DIGEST_TAG_PREFIX = "canonical:sha256:"


class UnitCapability(str, Enum):
    """The closed capability set of `admission:unit` (wire `capabilities`)."""

    COMPUTE = "compute"
    READ = "read"
    NET_SEND = "net_send"
    SUBMIT = "submit"
    SIGN = "sign"
    STORE_WRITE = "store_write"
    ACTUATE = "actuate"


#: The effect capabilities. `compute` and `read` are not effects.
EFFECT_CAPABILITIES: FrozenSet[UnitCapability] = frozenset(
    {
        UnitCapability.NET_SEND,
        UnitCapability.SUBMIT,
        UnitCapability.SIGN,
        UnitCapability.STORE_WRITE,
        UnitCapability.ACTUATE,
    }
)

#: A key record whose identity_type contains one of these is a person's key.
PERSON_IDENTITY_TYPES: FrozenSet[str] = frozenset({"user", "accord_holder"})


class UnitAdmissionToken(str, Enum):
    """The host's answer (CC 2.7.11 host tokens), plus the verifier token a host may meet."""

    ADMITTED = "admitted"
    ISSUER_NOT_REACHED = "admission_issuer_not_reached"
    COUNT_UNMET = "admission_count_unmet"
    NONE = "admission_none"
    CAPABILITY_NOT_ADMITTED = "admission_capability_not_admitted"
    CAPABILITY_NOT_HELD = "admission_capability_not_held"
    HALTED = "admission_halted"
    #: Verifier token: a signer's key is not a person's (here: the row admits nothing).
    ISSUER_NOT_PERSON = "admission_issuer_not_person"


class UnitAdmissionNoneDetail(str, Enum):
    """Detail of `admission_none`."""

    LEASE_ENDED = "lease_ended"
    WITHDRAWN = "withdrawn"
    NO_ROW = "no_row"


class AdmissionSigner(BaseModel):
    """One signer of a row (the author, or one voice of a counted row), as the key directory reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key_id: str = Field(..., description="The signer's `iss` key id")
    identity_type: str = Field(..., description="The key record's identity_type (e.g. 'user', 'node,agent')")


class UnitAdmissionRow(BaseModel):
    """One `admission:unit` row for a digest, as the server adapter returns it.

    The row's own signatures are verified by the substrate; the standing walk
    (owner's key, or the owner's `trust:accepts` edges with `admission` on every
    hop) is the server's answer in `standing`. Everything else is evaluated here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_id: str = Field(..., description="The row's id")
    sub: str = Field(..., description="canonical:sha256:{hex}, the unit digest")
    author: Optional[AdmissionSigner] = Field(None, description="Present exactly when the row is authored")
    refs_head: Optional[str] = Field(None, description="Counted rows only: the roster head the count is over")
    voices: List[AdmissionSigner] = Field(default_factory=list, description="Counted rows: each voice that signed")
    count_met: Optional[bool] = Field(
        None, description="Counted rows: the group's declared protocol is met at refs_head (None: head not held)"
    )
    capabilities: List[str] = Field(default_factory=list, description="Wire capabilities (validated here)")
    asserted_at_ms: int = Field(..., description="Lease opens (ms since epoch)")
    valid_until_ms: int = Field(..., description="Lease closes (ms since epoch), exclusive")
    standing: bool = Field(..., description="The author or the group stands at this host (server's walk)")
    withdrawn: bool = Field(False, description="A withdraws row for this admission is held")


class AdmissionRead(BaseModel):
    """What the one adapter function answered for one digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supported: bool = Field(..., description="False: the substrate has no admission read; nothing beyond the build loads")
    rows: List[UnitAdmissionRow] = Field(default_factory=list)
    read_error: Optional[str] = Field(None, description="Why the read failed, when it did (fail closed)")


class UnitAdmissionDecision(BaseModel):
    """The host's answer for a load or for one effect."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: UnitAdmissionToken
    detail: Optional[str] = Field(None, description="Detail (e.g. the admission_none detail, or the capability)")
    unit_digest: str = Field(..., description="canonical:sha256:{hex}")
    admitted_capabilities: List[UnitCapability] = Field(
        default_factory=list, description="Union over the live admitting rows"
    )
    admitting_rows: List[str] = Field(default_factory=list, description="Row ids that admit now")
    operator_notice: Optional[str] = Field(None, description="What an operator must do, when refused")

    @property
    def admitted(self) -> bool:
        return self.token == UnitAdmissionToken.ADMITTED

    def message(self) -> str:
        """`token[:detail]`, the refusal reason a caller surfaces."""
        return f"{self.token.value}:{self.detail}" if self.detail else self.token.value


__all__ = [
    "EFFECT_CAPABILITIES",
    "PERSON_IDENTITY_TYPES",
    "UNIT_DIGEST_TAG_PREFIX",
    "UNIT_LEASE_MAX_SECS",
    "AdmissionRead",
    "AdmissionSigner",
    "UnitAdmissionDecision",
    "UnitAdmissionNoneDetail",
    "UnitAdmissionRow",
    "UnitAdmissionToken",
    "UnitCapability",
]
