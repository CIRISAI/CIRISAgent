"""
BearNotes Adapter - Converted from Clawdbot skill: bear-notes

Create, search, and manage Bear notes via grizzly CLI.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/bear-notes/SKILL.md
"""

from .adapter import BearNotesAdapter
from .service import BearNotesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = BearNotesAdapter

__all__ = [
    "Adapter",
    "BearNotesAdapter",
    "BearNotesToolService",
]
