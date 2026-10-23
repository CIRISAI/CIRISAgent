"""Wise Authority-approved identity amendments: the one loader every identity view reads.

A WA-approved IDENTITY-scope MEMORIZE is stored as an ``IDENTITY_AMENDMENT``
node carrying its approval's provenance (``MemorizeHandler`` via
``as_identity_amendment``). ``agent/identity`` stays the template-derived core;
these load beside it, so the CORE IDENTITY block the DMAs see includes every
approved change while each one stays individually auditable and revocable.

Before this, approved identity changes were stored and authorized but never
read: every identity view took ``agent/identity`` alone, and
``export_identity_context`` took whichever IDENTITY node was newest (usually a
telemetry snapshot) and presented it as the identity.
"""

import logging
from typing import Any, List

from pydantic import ValidationError

from ciris_engine.logic.infrastructure.handlers.shared_helpers import amendment_text
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

logger = logging.getLogger(__name__)


def _optional_text(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def amendment_from_node(node: Any) -> IdentityAmendment | None:
    """The amendment a node records, or None when it is not a complete one.

    A node without the approval's provenance or without text is skipped:
    an amendment is only as good as the record of who approved it.
    """
    if getattr(node, "type", None) != NodeType.IDENTITY_AMENDMENT:
        return None
    attributes = node.attributes
    if hasattr(attributes, "model_dump"):
        attributes = attributes.model_dump()
    if not isinstance(attributes, dict):
        return None
    provenance = attributes.get("wa_amendment")
    content = amendment_text(attributes)
    if not isinstance(provenance, dict) or not content:
        logger.warning("identity amendment %s has no provenance or no content; not loaded", node.id)
        return None
    try:
        return IdentityAmendment(
            node_id=str(node.id),
            content=str(content),
            wa_id=str(provenance.get("wa_id", "")),
            deferral_id=str(provenance.get("deferral_id", "")),
            granted_at=str(provenance.get("granted_at", "")),
            response_attestation_id=_optional_text(provenance.get("response_attestation_id")),
            amendment_attestation_id=_optional_text(provenance.get("amendment_attestation_id")),
        )
    except ValidationError:
        logger.warning("identity amendment %s is malformed; not loaded", node.id)
        return None


async def load_identity_amendments(memory_service: Any) -> List[IdentityAmendment]:
    """Every approved identity amendment, oldest approval first."""
    if memory_service is None:
        return []
    query = MemoryQuery(
        node_id="*", scope=GraphScope.IDENTITY, type=NodeType.IDENTITY_AMENDMENT, include_edges=False, depth=1
    )
    try:
        nodes = await memory_service.recall(query)
    except Exception as e:  # noqa: BLE001 - a failed read must not take the identity down with it
        logger.warning(f"Failed to load identity amendments: {e}")
        return []
    amendments = [a for a in (amendment_from_node(n) for n in nodes or []) if a is not None]
    amendments.sort(key=lambda a: (a.granted_at, a.node_id))
    return amendments
