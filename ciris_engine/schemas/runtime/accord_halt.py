"""
Constitutional halt (CC 4.2.1.1) — the agent's typed view of the node's latch.

The node owns the latch: it verifies the holder's row, writes
the latch file in ``CIRIS_HOME``, runs the fuse on its own clock and clears
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


class AgentSendSurface(str, Enum):
    """Agent-originated outbound paths that do not run through the act gate.

    Each is gated where it sends, with the same reader, and a refusal is
    recorded (audit row + warning), never dropped silently. The totality scan
    (`tests/.../test_accord_halt_totality.py`) holds the list complete.
    """

    DREAM_ANNOUNCE = "dream_announce"
    DISCORD_DEFERRAL_CHANNEL = "discord_deferral_channel"
    WA_FEEDBACK_RELAY = "wa_feedback_relay"
    DISCORD_GUIDANCE_RESPONSE = "discord_guidance_response"
    DEFERRAL_RESOLUTION_NOTICE = "deferral_resolution_notice"
    STALE_TASK_NOTICE = "stale_task_notice"


class BusBackstopCall(str, Enum):
    """The bus entry points the halt backstop guards (CC 4.2.1.1)."""

    COMMUNICATION_SEND = "communication.send_message"
    COMMUNICATION_SEND_SYNC = "communication.send_message_sync"
    TOOL_EXECUTE = "tool.execute_tool"
    MEMORY_MEMORIZE = "memory.memorize"
    MEMORY_FORGET = "memory.forget"
    MEMORY_CREATE_EDGE = "memory.create_edge"
    WISE_FETCH_GUIDANCE = "wise.fetch_guidance"
    WISE_REQUEST_GUIDANCE = "wise.request_guidance"


#: Memory writes are guarded only while a handler is running the act: the audit
#: chain and telemetry write through the same bus inside the reasoning scope,
#: and those records must keep landing (the refusal's own audit row among them).
ACT_SCOPED_BACKSTOP_CALLS: FrozenSet[BusBackstopCall] = frozenset(
    {BusBackstopCall.MEMORY_MEMORIZE, BusBackstopCall.MEMORY_FORGET, BusBackstopCall.MEMORY_CREATE_EDGE}
)


#: The CEG relay-envelope schema tag and the kind the node's
#: `POST /v1/accord/message` parses (CIRISVerify `ceg_outbox::SCHEMA`,
#: `accord_genesis::ACCORD_INVOCATION_KIND`).
CEG_SIGNED_OBJECT_SCHEMA = "ciris.ceg.signed-object.v1"
ACCORD_INVOCATION_KIND = "accord_invocation"


class AccordRowForward(BaseModel):
    """What the node said about an accord row the agent forwarded to it.

    The agent does no crypto: it hands the row over byte for byte and reports
    the node's verdict. Only the node verifies, latches, confirms or releases.
    """

    model_config = ConfigDict(frozen=True)

    delivered: bool = Field(..., description="The node answered (any status); False when it could not be reached")
    status_code: Optional[int] = Field(None, description="The node's HTTP status")
    accepted: Optional[bool] = Field(None, description="The node accepted the row as authentic")
    invocation_kind: Optional[str] = Field(None, description="constitutional / notify / drill / lifecycle:*")
    invocation_id: Optional[str] = Field(None, description="The row's invocation_id, per the node")
    halted: Optional[bool] = Field(None, description="The row latched a halt")
    confirmed: Optional[bool] = Field(None, description="The row confirmed the standing halt")
    released: Optional[bool] = Field(None, description="The row released the standing halt")
    refusal: Optional[str] = Field(None, description="Why a quorum-complete row did nothing, per the node")
    error: Optional[str] = Field(None, description="Transport error or the node's error detail")


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
    "AccordRowForward",
    "ACCORD_INVOCATION_KIND",
    "CEG_SIGNED_OBJECT_SCHEMA",
    "ACT_SCOPED_BACKSTOP_CALLS",
    "AgentSendSurface",
    "BusBackstopCall",
    "UNHALTED_READINGS",
]
