"""
Sonoscli Adapter - Converted from Clawdbot skill: sonoscli

Control Sonos speakers (discover/status/play/volume/group).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/sonoscli/SKILL.md
"""

from .adapter import SonoscliAdapter
from .service import SonoscliToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SonoscliAdapter

__all__ = [
    "Adapter",
    "SonoscliAdapter",
    "SonoscliToolService",
]
