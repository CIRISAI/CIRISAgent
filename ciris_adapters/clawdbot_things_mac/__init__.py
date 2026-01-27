"""
ThingsMac Adapter - Converted from Clawdbot skill: things-mac

Manage Things 3 via the `things` CLI on macOS (add/update projects+todos via URL scheme; read/search/list from the local Things database). Use when a user asks Moltbot to add a task to Things, list inbox/today/upcoming, search tasks, or inspect projects/areas/tags.

Original source: ../clawdbot/skills/things-mac/SKILL.md
"""

from .adapter import ThingsMacAdapter
from .service import ThingsMacToolService

# Export as Adapter for load_adapter() compatibility
Adapter = ThingsMacAdapter

__all__ = [
    "Adapter",
    "ThingsMacAdapter",
    "ThingsMacToolService",
]
