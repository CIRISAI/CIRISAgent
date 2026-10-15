"""Node ownership as the agent reads it: every node is claimed by a named human.

An agent cannot run without a named human for its node. The node holds the
answer (its owner-binding); `ciris_engine.logic.utils.node_ownership` reads it
and the processor start, intake, the act gate and setup completion all gate on
that one reading.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

#: The error token for every refusal on an unowned node (intake 423, setup 409, act refusal).
NODE_UNCLAIMED_ERROR = "node_unclaimed"

#: The file the node writes its one-time claim PIN to while it is unowned,
#: relative to CIRIS_HOME. The location is said out loud; the PIN never is.
CLAIM_PIN_FILE_NAME = "claim_pin"

#: The node route that claims it with that PIN (what the wizard and CIRISManager post).
CLAIM_ROUTE = "POST /v1/setup/claim-remote"


class NodeOwnershipReading(str, Enum):
    """What one read of the node's ownership found."""

    OWNED = "owned"
    #: The node answered: it has no owner.
    UNOWNED = "unowned"
    #: The node has not named its own key yet (compose not done).
    NO_NODE_KEY = "no_node_key"
    #: No in-process persist engine to ask.
    NO_ENGINE = "no_engine"
    READ_ERROR = "read_error"
    READ_TIMEOUT = "read_timeout"
    #: CIRIS_NODE_FOLD=false: no node in this process, so no owner. Held like
    #: any other unowned reading; there are no deployments without nodes.
    NO_NODE = "no_node"


class NodeOwnership(BaseModel):
    """One ownership reading. Anything that is not a definite owner is unclaimed (fail closed)."""

    reading: NodeOwnershipReading
    owner_key_id: Optional[str] = Field(None, description="The node's single responsible owner, when owned")
    node_key_id: Optional[str] = Field(None, description="The node key the owner-binding was asked about")
    read_error: Optional[str] = Field(None, description="Why the read could not tell, when it could not")
    read_at: datetime
    claim_pin_file: str = Field(..., description="Where the node writes its claim PIN (the location, never the PIN)")
    claim_route: str = Field(CLAIM_ROUTE, description="The node route that claims it")

    @property
    def unclaimed(self) -> bool:
        """True when the agent must hold: every reading except OWNED."""
        return self.reading != NodeOwnershipReading.OWNED

    def unclaimed_message(self) -> str:
        """What is missing and how to supply it. Names the PIN file, never its contents."""
        why = f" ({self.reading.value}{f': {self.read_error}' if self.read_error else ''})"
        return (
            f"This node has no owner{why}. An agent does not run on an unowned node: the deployer claims it "
            f"with the one-time PIN the node wrote to {self.claim_pin_file}, via {self.claim_route}."
        )


__all__ = [
    "CLAIM_PIN_FILE_NAME",
    "CLAIM_ROUTE",
    "NODE_UNCLAIMED_ERROR",
    "NodeOwnership",
    "NodeOwnershipReading",
]
