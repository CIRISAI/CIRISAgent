"""
Songsee Adapter - Converted from CIRIS adapter: songsee

Generate spectrograms and feature-panel visualizations from audio with the songsee CLI.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/songsee/SKILL.md
"""

from .adapter import SongseeAdapter
from .service import SongseeToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SongseeAdapter

__all__ = [
    "Adapter",
    "SongseeAdapter",
    "SongseeToolService",
]
