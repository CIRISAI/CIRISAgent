"""
LocalPlaces Adapter - Converted from Clawdbot skill: local-places

Search for places (restaurants, cafes, etc.) via Google Places API proxy on localhost.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/local-places/SKILL.md
"""

from .adapter import LocalPlacesAdapter
from .service import LocalPlacesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = LocalPlacesAdapter

__all__ = [
    "Adapter",
    "LocalPlacesAdapter",
    "LocalPlacesToolService",
]
