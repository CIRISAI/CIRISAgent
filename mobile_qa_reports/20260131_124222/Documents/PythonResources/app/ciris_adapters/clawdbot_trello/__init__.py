"""
Trello Adapter - Converted from Clawdbot skill: trello

Manage Trello boards, lists, and cards via the Trello REST API.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/trello/SKILL.md
"""

from .adapter import TrelloAdapter
from .service import TrelloToolService

# Export as Adapter for load_adapter() compatibility
Adapter = TrelloAdapter

__all__ = [
    "Adapter",
    "TrelloAdapter",
    "TrelloToolService",
]
