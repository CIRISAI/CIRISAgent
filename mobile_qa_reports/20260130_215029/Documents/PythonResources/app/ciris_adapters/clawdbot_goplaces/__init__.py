"""
Goplaces Adapter - Converted from Clawdbot skill: goplaces

Query Google Places API (New) via the goplaces CLI for text search, place details, resolve, and reviews. Use for human-friendly place lookup or JSON output for scripts.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/goplaces/SKILL.md
"""

from .adapter import GoplacesAdapter
from .service import GoplacesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = GoplacesAdapter

__all__ = [
    "Adapter",
    "GoplacesAdapter",
    "GoplacesToolService",
]
