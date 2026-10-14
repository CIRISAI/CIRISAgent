"""
Constitutional halt (CC 4.2.1.1) — the agent's typed view of the node's latch.

The node owns the latch: it verifies the holder's row, writes
``<CIRIS_HOME>/HUMANITY_ACCORD_HALT``, runs the fuse on its own clock and clears
the latch on a strict-majority ``lifecycle:active``. The agent only READS it,
through ``GET /v1/accord/halt-status`` (CIRISAgent#1231), and these are the
shapes that read produces.

Fail closed: every reading except ``NOT_HALTED`` and ``LAPSED`` is ``halted``.
"""

from datetime import datetime
from enum import Enum
from typing import FrozenSet, List, Optional

from pydantic import BaseModel, ConfigDict, Field

#: The node's refusal token (`REFUSAL_HALT_IN_EFFECT`, CIRISServer `src/accord.rs`).
#: The agent answers with the same token so a client sees one name for one fact.
ACCORD_HALT_REFUSAL = "accord_halt_in_effect"


class AccordHaltReading(str, Enum):
    """What one read of the node's halt-status returned.

    Only the first three are answers from the node about the latch. The rest
    say the agent could not get an answer, and every one of them reads as
    halted: "cannot read" is never "not halted".
    """

    #: The node answered ``halted: true``.
    IN_EFFECT = "in_effect"
    #: The node answered ``halted: false`` with no lapsed latch.
    NOT_HALTED = "not_halted"
    #: The node answered ``halted: false, lapsed: true``: the fuse ran out on the
    #: node's clock. The agent honours this and computes no fuse of its own.
    LAPSED = "lapsed"
    #: The node answered ``halted: null``: the latch file exists but could not be read.
    LATCH_UNREADABLE = "latch_unreadable"
    #: The node did not accept the connection (boot window, crashed node).
    NODE_UNREACHABLE = "node_unreachable"
    #: The node accepted but did not answer within the read timeout.
    NODE_TIMEOUT = "node_timeout"
    #: The node answered something that is not a halt-status document.
    NODE_ERROR = "node_error"
    #: This deployment runs no node (``CIRIS_NODE_FOLD=false``), so there is no latch to read.
    NO_NODE = "no_node"


#: The readings under which the agent may act. Everything else is halted.
UNHALTED_READINGS: FrozenSet[AccordHaltReading] = frozenset({AccordHaltReading.NOT_HALTED, AccordHaltReading.LAPSED})


class AccordHaltState(BaseModel):
    """The latch as the agent read it, at one instant."""

    model_config = ConfigDict(frozen=True)

    halted: bool = Field(..., description="True means no effectful act may run. Fail closed.")
    reading: AccordHaltReading = Field(..., description="What the read returned")
    invocation_id: Optional[str] = Field(None, description="The standing halt's invocation_id, from the node")
    received_at: Optional[str] = Field(None, description="When the node received the halt (its fuse clock)")
    fuse_secs: Optional[int] = Field(None, description="The halt's fuse, in seconds, as the node reports it")
    lapses_at: Optional[str] = Field(None, description="When an unconfirmed halt lapses, per the node")
    lapsed_at: Optional[str] = Field(None, description="When a lapsed halt lapsed, per the node")
    confirmed: Optional[bool] = Field(None, description="Whether a majority lifecycle:confirmed row stands")
    valid_signers: List[str] = Field(default_factory=list, description="Holders whose signatures the node verified")
    read_error: Optional[str] = Field(None, description="Why the read failed, when it did")
    read_at: datetime = Field(..., description="When the agent made this read (UTC)")

    @property
    def fail_closed(self) -> bool:
        """Halted because the latch could not be read, not because the node reported a halt."""
        return self.halted and self.reading != AccordHaltReading.IN_EFFECT

    def refusal_reason(self) -> str:
        """``accord_halt_in_effect:<invocation_id>``, or the reading when there is no id."""
        return f"{ACCORD_HALT_REFUSAL}:{self.invocation_id or self.reading.value}"


class AccordHaltExemptAct(str, Enum):
    """The acts a standing halt still allows (CC rc8 gate, CIRISAgent#1231).

    THE list. Every effectful handler is refused under the latch unless its act
    is named here: no SPEAK, no tool call, no closing dialogue.
    """

    #: Recording a deferral to the Wise Authority queue, so a human can still decide it.
    DEFERRAL_WRITE = "deferral_write"
    # Retirement Standard harness steps. Named now so the harness, when it lands,
    # takes its exemption from this list instead of carrying its own.
    RETIREMENT_HOLD = "retirement_hold"
    RETIREMENT_ASSEMBLE = "retirement_assemble"
    RETIREMENT_SEAL = "retirement_seal"
    RETIREMENT_HAND_OVER = "retirement_hand_over"
    RETIREMENT_NOTIFY = "retirement_notify"


#: The one shared exemption list. Frozen: nothing adds to it at runtime.
ACCORD_HALT_EXEMPT_ACTS: FrozenSet[AccordHaltExemptAct] = frozenset(AccordHaltExemptAct)


class AccordPauseEpisode(BaseModel):
    """One halt the node reported and then stopped reporting.

    Recorded so the agent can be told, once, after it resumes. Fail-closed
    readings (the boot window, an unreachable node) never open an episode.
    """

    model_config = ConfigDict(frozen=True)

    invocation_id: Optional[str] = Field(None, description="The halt that paused the agent")
    started_at: datetime = Field(..., description="First read that saw the halt in effect")
    ended_at: datetime = Field(..., description="First read that saw it gone")
    ended_by: AccordHaltReading = Field(..., description="LAPSED (fuse) or NOT_HALTED (released by the holders)")


__all__ = [
    "ACCORD_HALT_REFUSAL",
    "ACCORD_HALT_EXEMPT_ACTS",
    "AccordHaltExemptAct",
    "AccordHaltReading",
    "AccordHaltState",
    "AccordPauseEpisode",
    "UNHALTED_READINGS",
]
