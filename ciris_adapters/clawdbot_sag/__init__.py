"""
Sag Adapter - Converted from Clawdbot skill: sag

ElevenLabs text-to-speech with mac-style say UX.

Original source: ../clawdbot/skills/sag/SKILL.md
"""

from .adapter import SagAdapter
from .service import SagToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SagAdapter

__all__ = [
    "Adapter",
    "SagAdapter",
    "SagToolService",
]
