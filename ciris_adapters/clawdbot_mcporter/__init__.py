"""
Mcporter Adapter - Converted from Clawdbot skill: mcporter

Use the mcporter CLI to list, configure, auth, and call MCP servers/tools directly (HTTP or stdio), including ad-hoc servers, config edits, and CLI/type generation.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/mcporter/SKILL.md
"""

from .adapter import McporterAdapter
from .service import McporterToolService

# Export as Adapter for load_adapter() compatibility
Adapter = McporterAdapter

__all__ = [
    "Adapter",
    "McporterAdapter",
    "McporterToolService",
]
