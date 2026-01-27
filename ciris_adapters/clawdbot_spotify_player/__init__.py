"""
SpotifyPlayer Adapter - Converted from Clawdbot skill: spotify-player

Terminal Spotify playback/search via spogo (preferred) or spotify_player.

Original source: ../clawdbot/skills/spotify-player/SKILL.md
"""

from .adapter import SpotifyPlayerAdapter
from .service import SpotifyPlayerToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SpotifyPlayerAdapter

__all__ = [
    "Adapter",
    "SpotifyPlayerAdapter",
    "SpotifyPlayerToolService",
]
