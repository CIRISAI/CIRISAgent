"""What a memory learned in one room may be shown to (CC 1.13.3.4, Eric 2026-11-20).

"What an agent derives from content may be shown only to those who may see every piece it was derived from. What
draws on two rooms may be shown only to those who are in both." A DM's audience is its two parties; a channel's is
its members.

2.23.2 stops the leak at the room boundary: a conversation memory carries the room it was learned in, and it is
recalled only in that room. The engine stamps it at MEMORIZE (``room:<channel id>`` in the node's tags) and strips
any such tag the model supplied, so a draft cannot claim another room. The agent's own identity and config nodes
are not stamped: they are not anyone's conversation.

Not yet covered, recorded as a divergence until Agent 3.0's audience model (an audience on each prompt segment,
intersected across ``derived_from`` like trust, checked before SPEAK, edge and trace egress): nodes written before
2.23.2 carry no room and still pass, and so does what the model writes in a reply from what it read.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from ciris_engine.schemas.services.graph_core import GraphNode

#: The tag naming the room a conversation memory was learned in.
ROOM_TAG_PREFIX = "room:"


def _tags_of(attributes: Any) -> List[str]:
    tags = attributes.get("tags") if isinstance(attributes, dict) else getattr(attributes, "tags", None)
    return [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []


def node_room(node: GraphNode) -> Optional[str]:
    """The room this node was learned in, or ``None`` when it names none (the agent's own, or written before 2.23.2)."""
    rooms = [t[len(ROOM_TAG_PREFIX) :] for t in _tags_of(node.attributes) if t.startswith(ROOM_TAG_PREFIX)]
    return rooms[0] if len(rooms) == 1 and rooms[0] else (None if not rooms else "")


def stamp_room(node: GraphNode, channel_id: Optional[str]) -> GraphNode:
    """The node to write: any model-supplied ``room:`` tag removed, then the room it was actually learned in.

    With no channel the node is still stripped (a draft never names a room itself) and left unstamped.
    """
    attributes = node.attributes
    tags = [t for t in _tags_of(attributes) if not t.startswith(ROOM_TAG_PREFIX)]
    if channel_id:
        tags.append(f"{ROOM_TAG_PREFIX}{channel_id}")
    if isinstance(attributes, dict):
        if not tags and "tags" not in attributes:
            return node
        return node.model_copy(update={"attributes": {**attributes, "tags": tags}})
    if hasattr(attributes, "tags"):
        return node.model_copy(update={"attributes": attributes.model_copy(update={"tags": tags})})
    return node


def visible_in(node: GraphNode, channel_id: Optional[str]) -> bool:
    """True when this node may be shown in ``channel_id``: it names no room, or this one.

    A node naming a room is never shown where the room is unknown, nor where two ``room:`` tags disagree.
    """
    room = node_room(node)
    if room is None:
        return True
    return bool(room) and bool(channel_id) and room == channel_id


def visible_nodes(nodes: Sequence[GraphNode], channel_id: Optional[str]) -> List[GraphNode]:
    """The nodes that may be shown in ``channel_id``, in order."""
    return [n for n in nodes if visible_in(n, channel_id)]


__all__ = ["ROOM_TAG_PREFIX", "node_room", "stamp_room", "visible_in", "visible_nodes"]
