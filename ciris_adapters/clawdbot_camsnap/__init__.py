"""
Camsnap Adapter - Converted from Clawdbot skill: camsnap

Capture frames or clips from RTSP/ONVIF cameras.

Original source: ../clawdbot/skills/camsnap/SKILL.md
"""

from .adapter import CamsnapAdapter
from .service import CamsnapToolService

# Export as Adapter for load_adapter() compatibility
Adapter = CamsnapAdapter

__all__ = [
    "Adapter",
    "CamsnapAdapter",
    "CamsnapToolService",
]
