"""Node ownership as the agent reads it: every node is claimed by a named human.

An agent cannot run without a named human for its node. The node holds the
answer (its owner-binding); `ciris_engine.logic.utils.node_ownership` reads it
and the processor start, intake, the act gate and setup completion all gate on
that one reading.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.authority_core import WARole

#: The error token for every refusal on an unowned node (intake 423, setup 409, act refusal).
NODE_UNCLAIMED_ERROR = "node_unclaimed"

#: The file the node writes its one-time claim PIN to while it is unowned,
#: relative to CIRIS_HOME. The location is said out loud; the PIN never is.
CLAIM_PIN_FILE_NAME = "claim_pin"

#: A FRESH node: the route that claims it with that PIN (what the wizard and CIRISManager post).
CLAIM_ROUTE = "POST /v1/setup/claim-remote"

#: An UPGRADED node that already has a ROOT: setup/root is closed and the node
#: mints no PIN, so the existing owner, signed in, mints a federation ID and
#: re-roots the node on a fed-ID owner-binding, in this order.
UPGRADE_CLAIM_ROUTES = ("POST /v1/self/identity", "POST /v1/self/upgrade-owner")


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
    claim_route: str = Field(CLAIM_ROUTE, description="The route that claims a fresh node with the PIN")
    upgrade_claim_routes: List[str] = Field(
        default_factory=lambda: list(UPGRADE_CLAIM_ROUTES),
        description="The routes, in order, by which an upgraded node's existing ROOT owner claims it",
    )

    @property
    def unclaimed(self) -> bool:
        """True when the agent must hold: every reading except OWNED."""
        return self.reading != NodeOwnershipReading.OWNED

    def unclaimed_message(self) -> str:
        """What is missing and how to supply it. Names the PIN file, never its contents."""
        why = f" ({self.reading.value}{f': {self.read_error}' if self.read_error else ''})"
        return (
            f"This node has no owner{why}. An agent does not run on an unowned node. To claim it: on a fresh "
            f"node, the deployer uses the one-time PIN the node wrote to {self.claim_pin_file}, via "
            f"{self.claim_route}; on an upgraded node that already has a ROOT (no PIN is minted), the existing "
            f"owner signs in and calls {' then '.join(self.upgrade_claim_routes)}."
        )


class NodeOwnerRecord(BaseModel):
    """The node-claimed owner, as `ciris_server.owner_record()` reports it (CIRISServer 0.5.234).

    Every value comes from the node's founding ROOT WaCert; the substrate invents
    none of them, and neither does the agent. The brain's user table holds no row
    for this identity (the node owns identity), so this is the only source.
    """

    wa_id: str = Field(..., description="The founding ROOT WaCert's wa_id (a substrate session's user_id)")
    name: str = Field(..., description="The WaCert's name")
    role: WARole = Field(..., description="The WaCert's role (persist WaRole, lowercase on the wire)")
    created_at: datetime = Field(..., description="When the WaCert was created")
    owner_key_id: Optional[str] = Field(None, description="owner_of(node): the bound fedID; null for a legacy ROOT")
    oauth_provider: Optional[str] = Field(None, description="The WaCert's OAuth provider, when it has one")


__all__ = [
    "CLAIM_PIN_FILE_NAME",
    "CLAIM_ROUTE",
    "NODE_UNCLAIMED_ERROR",
    "UPGRADE_CLAIM_ROUTES",
    "NodeOwnerRecord",
    "NodeOwnership",
    "NodeOwnershipReading",
]
