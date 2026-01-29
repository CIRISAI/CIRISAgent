"""
Bird Adapter - Converted from Clawdbot skill: bird

X/Twitter CLI for reading, searching, posting, and engagement via cookies.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/bird/SKILL.md
"""

from .adapter import BirdAdapter
from .service import BirdToolService

# Export as Adapter for load_adapter() compatibility
Adapter = BirdAdapter

__all__ = [
    "Adapter",
    "BirdAdapter",
    "BirdToolService",
]
