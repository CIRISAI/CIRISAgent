"""
Notion Adapter - Converted from Clawdbot skill: notion

Notion API for creating and managing pages, databases, and blocks.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/notion/SKILL.md
"""

from .adapter import NotionAdapter
from .service import NotionToolService

# Export as Adapter for load_adapter() compatibility
Adapter = NotionAdapter

__all__ = [
    "Adapter",
    "NotionAdapter",
    "NotionToolService",
]
