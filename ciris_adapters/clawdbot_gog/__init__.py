"""
Gog Adapter - Converted from Clawdbot skill: gog

Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/gog/SKILL.md
"""

from .adapter import GogAdapter
from .service import GogToolService

# Export as Adapter for load_adapter() compatibility
Adapter = GogAdapter

__all__ = [
    "Adapter",
    "GogAdapter",
    "GogToolService",
]
