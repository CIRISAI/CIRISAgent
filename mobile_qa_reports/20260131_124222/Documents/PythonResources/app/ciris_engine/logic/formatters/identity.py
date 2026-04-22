"""
Identity formatter for agent identity context in system snapshots.

Converts raw identity graph node data into human-readable text format,
including shutdown/continuity history.
"""

from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_list, get_str
from ciris_engine.schemas.types import JSONDict


def _format_core_identity(agent_identity: JSONDict) -> List[str]:
    """Extract and format core identity fields."""
    lines = []
    agent_id = get_str(agent_identity, "agent_id", "Unknown")
    description = get_str(agent_identity, "description", "")
    role = get_str(agent_identity, "role_description", "")

    lines.append(f"Agent ID: {agent_id}")
    if description:
        lines.append(f"Purpose: {description.strip()}")
    if role:
        lines.append(f"Role: {role.strip()}")

    trust_level = agent_identity.get("trust_level")
    if trust_level is not None:
        lines.append(f"Trust Level: {trust_level}")

    return lines


def _format_domain_knowledge(agent_identity: JSONDict) -> List[str]:
    """Extract and format domain-specific knowledge."""
    lines = []
    domain_knowledge = agent_identity.get("domain_specific_knowledge")
    if domain_knowledge and isinstance(domain_knowledge, dict):
        dk_role = domain_knowledge.get("role")
        if dk_role:
            lines.append(f"Domain Role: {dk_role}")
    return lines


def _format_permitted_actions(agent_identity: JSONDict) -> List[str]:
    """Extract and format permitted actions summary."""
    lines = []
    permitted_actions = agent_identity.get("permitted_actions", [])
    if permitted_actions and isinstance(permitted_actions, list):
        lines.append(f"Permitted Actions: {', '.join(permitted_actions[:10])}")
    return lines


def _is_continuity_event(tags: List[str]) -> bool:
    """Check if tags indicate a continuity awareness event."""
    return "consciousness_preservation" in tags or "continuity_awareness" in tags


def _extract_startup_timestamps(agent_identity: JSONDict) -> List[str]:
    """Extract startup event timestamps from agent identity."""
    timestamps = []
    for key, value in agent_identity.items():
        if not key.startswith("startup_"):
            continue
        if not isinstance(value, dict):
            continue

        tags = value.get("tags", [])
        if "startup" in tags and _is_continuity_event(tags):
            timestamp_str = key.replace("startup_", "")
            timestamps.append(timestamp_str)

    return timestamps


def _extract_shutdown_timestamps(agent_identity: JSONDict) -> List[str]:
    """Extract shutdown event timestamps from agent identity."""
    timestamps = []
    for key, value in agent_identity.items():
        if not key.startswith("shutdown_"):
            continue
        if not isinstance(value, dict):
            continue

        tags = value.get("tags", [])
        if "shutdown" in tags and _is_continuity_event(tags):
            timestamp_str = key.replace("shutdown_", "")
            timestamps.append(timestamp_str)

    return timestamps


def _extract_event_timestamps(agent_identity: JSONDict) -> Tuple[Optional[str], List[str]]:
    """
    Extract startup and shutdown timestamps.

    Returns
    -------
    tuple
        (first_event_timestamp, shutdown_timestamps)
    """
    startup_timestamps = _extract_startup_timestamps(agent_identity)
    shutdown_timestamps = _extract_shutdown_timestamps(agent_identity)

    all_timestamps = startup_timestamps + shutdown_timestamps
    first_event_timestamp = min(all_timestamps) if all_timestamps else None

    return first_event_timestamp, shutdown_timestamps


def _clean_timestamp(timestamp: str) -> str:
    """Clean timestamp string for display."""
    try:
        clean_ts = timestamp.split(".")[0] if "." in timestamp else timestamp
        clean_ts = clean_ts.replace("+00:00", " UTC")
        return clean_ts
    except Exception:
        return timestamp


def _format_shutdown_history(shutdown_timestamps: List[str]) -> List[str]:
    """Format shutdown history into readable lines."""
    lines: List[str] = []
    if not shutdown_timestamps:
        return lines

    # Sort by timestamp (most recent first)
    sorted_shutdowns = sorted(shutdown_timestamps, reverse=True)
    recent_shutdowns = sorted_shutdowns[:5]

    lines.append(f"Recent Shutdowns ({len(shutdown_timestamps)} total):")
    for ts in recent_shutdowns:
        clean_ts = _clean_timestamp(ts)
        lines.append(f"  - {clean_ts}")

    if len(shutdown_timestamps) > 5:
        lines.append(f"  ... and {len(shutdown_timestamps) - 5} more")

    return lines


def _format_continuity_history(first_event_timestamp: Optional[str], shutdown_timestamps: List[str]) -> List[str]:
    """Format continuity history section."""
    lines: List[str] = []
    if not first_event_timestamp and not shutdown_timestamps:
        return lines

    lines.append("")
    lines.append("=== Continuity History ===")

    if first_event_timestamp:
        clean_ts = _clean_timestamp(first_event_timestamp)
        lines.append(f"First Start: {clean_ts}")

    lines.extend(_format_shutdown_history(shutdown_timestamps))

    return lines


def _find_channel_assignment(agent_identity: JSONDict) -> Optional[str]:
    """Find channel assignment message in agent identity."""
    for key, value in agent_identity.items():
        if isinstance(value, str) and "assigned channel" in value.lower():
            return value
    return None


def format_agent_identity(agent_identity: Optional[JSONDict]) -> str:
    """
    Format agent identity information into readable text.

    Handles both old terminology (consciousness_preservation) and new terminology
    (continuity_awareness) for backward compatibility with existing shutdown nodes.

    Parameters
    ----------
    agent_identity : dict or None
        Agent identity data from graph node, typically containing:
        - agent_id: Agent identifier
        - description: Agent description/purpose
        - role_description: Agent role
        - trust_level: Trust level (0-1)
        - domain_specific_knowledge: Domain knowledge dict
        - permitted_actions: List of allowed actions
        - And potentially many shutdown node references

    Returns
    -------
    str
        Formatted identity context ready for system prompt, or empty string if no identity.

    Notes
    -----
    - Extracts core identity fields (agent_id, description, role)
    - Identifies shutdown nodes by tags (supports both old and new terminology)
    - Formats shutdown history as clean timestamp list
    - Omits raw graph node data to keep prompts concise
    - Preserves channel assignment if present
    """
    if not agent_identity or not isinstance(agent_identity, dict):
        return ""

    lines = []

    # Core identity information
    lines.extend(_format_core_identity(agent_identity))

    # Domain-specific knowledge
    lines.extend(_format_domain_knowledge(agent_identity))

    # Permitted actions summary
    lines.extend(_format_permitted_actions(agent_identity))

    # Extract and format continuity history
    first_event_timestamp, shutdown_timestamps = _extract_event_timestamps(agent_identity)
    lines.extend(_format_continuity_history(first_event_timestamp, shutdown_timestamps))

    # Channel assignment (if present)
    channel_assignment = _find_channel_assignment(agent_identity)
    if channel_assignment:
        lines.append("")
        lines.append(channel_assignment)

    return "\n".join(lines)
