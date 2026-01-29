"""
AppleNotes Adapter - Converted from Clawdbot skill: apple-notes

Manage Apple Notes via the `memo` CLI on macOS (create, view, edit, delete, search, move, and export notes). Use when a user asks Moltbot to add a note, list notes, search notes, or manage note folders.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/apple-notes/SKILL.md
"""

from .adapter import AppleNotesAdapter
from .service import AppleNotesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = AppleNotesAdapter

__all__ = [
    "Adapter",
    "AppleNotesAdapter",
    "AppleNotesToolService",
]
