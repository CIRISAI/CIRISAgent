"""
Identity formatter for agent identity context in system snapshots.

Converts raw identity graph node data into human-readable text format,
including shutdown/continuity history.
"""

from typing import Any, Dict, Optional


def format_agent_identity(agent_identity: Optional[Dict[str, Any]]) -> str:
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
    agent_id = agent_identity.get("agent_id", "Unknown")
    description = agent_identity.get("description", "")
    role = agent_identity.get("role_description", "")

    lines.append(f"Agent ID: {agent_id}")

    if description:
        lines.append(f"Purpose: {description.strip()}")

    if role:
        lines.append(f"Role: {role.strip()}")

    # Trust level
    trust_level = agent_identity.get("trust_level")
    if trust_level is not None:
        lines.append(f"Trust Level: {trust_level}")

    # Domain-specific knowledge (if present and concise)
    domain_knowledge = agent_identity.get("domain_specific_knowledge")
    if domain_knowledge and isinstance(domain_knowledge, dict):
        dk_role = domain_knowledge.get("role")
        if dk_role:
            lines.append(f"Domain Role: {dk_role}")

    # Permitted actions summary
    permitted_actions = agent_identity.get("permitted_actions", [])
    if permitted_actions and isinstance(permitted_actions, list):
        lines.append(f"Permitted Actions: {', '.join(permitted_actions[:10])}")  # Limit to 10

    # Extract startup and shutdown history
    # Support both old terminology (consciousness_preservation) and new (continuity_awareness)
    first_event_timestamp = None
    shutdown_timestamps = []
    all_timestamps = []

    for key, value in agent_identity.items():
        if key.startswith("startup_"):
            # Extract startup timestamp
            if isinstance(value, dict):
                tags = value.get("tags", [])
                if "startup" in tags and ("consciousness_preservation" in tags or "continuity_awareness" in tags):
                    timestamp_str = key.replace("startup_", "")
                    all_timestamps.append(timestamp_str)

        elif key.startswith("shutdown_"):
            # This is a shutdown node reference
            if isinstance(value, dict):
                # Check if tags indicate this is a shutdown node
                tags = value.get("tags", [])
                if "shutdown" in tags and ("consciousness_preservation" in tags or "continuity_awareness" in tags):
                    # Extract timestamp from key (format: shutdown_YYYY-MM-DDTHH:MM:SS.ffffff+00:00)
                    timestamp_str = key.replace("shutdown_", "")
                    shutdown_timestamps.append(timestamp_str)
                    all_timestamps.append(timestamp_str)

    # Use earliest event (startup or shutdown) as first start date
    if all_timestamps:
        first_event_timestamp = min(all_timestamps)

    # Format continuity history
    if first_event_timestamp or shutdown_timestamps:
        lines.append("")  # Blank line for separation
        lines.append("=== Continuity History ===")

        # First start (earliest startup or shutdown event)
        if first_event_timestamp:
            try:
                clean_ts = (
                    first_event_timestamp.split(".")[0] if "." in first_event_timestamp else first_event_timestamp
                )
                clean_ts = clean_ts.replace("+00:00", " UTC")
                lines.append(f"First Start: {clean_ts}")
            except Exception:
                lines.append(f"First Start: {first_event_timestamp}")

        # Shutdown history
        if shutdown_timestamps:
            # Sort by timestamp (most recent first)
            shutdown_timestamps.sort(reverse=True)

            # Show last 5 shutdowns for conciseness
            recent_shutdowns = shutdown_timestamps[:5]
            lines.append(f"Recent Shutdowns ({len(shutdown_timestamps)} total):")
            for ts in recent_shutdowns:
                # Format timestamp more readably (just date and time, no microseconds)
                try:
                    clean_ts = ts.split(".")[0] if "." in ts else ts
                    clean_ts = clean_ts.replace("+00:00", " UTC")
                    lines.append(f"  - {clean_ts}")
                except Exception:
                    lines.append(f"  - {ts}")

            if len(shutdown_timestamps) > 5:
                lines.append(f"  ... and {len(shutdown_timestamps) - 5} more")

    # Channel assignment (if present)
    # Look for patterns like "Our assigned channel is api_google:110265575142761676421"
    for key, value in agent_identity.items():
        if isinstance(value, str) and "assigned channel" in value.lower():
            lines.append("")
            lines.append(value)
            break

    return "\n".join(lines)
