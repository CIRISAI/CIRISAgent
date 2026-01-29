"""
Blucli Adapter - Converted from Clawdbot skill: blucli

BluOS CLI (blu) for discovery, playback, grouping, and volume.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/blucli/SKILL.md
"""

from .adapter import BlucliAdapter
from .service import BlucliToolService

# Export as Adapter for load_adapter() compatibility
Adapter = BlucliAdapter

__all__ = [
    "Adapter",
    "BlucliAdapter",
    "BlucliToolService",
]
