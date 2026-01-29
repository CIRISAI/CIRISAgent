"""
VoiceCall Adapter - Converted from Clawdbot skill: voice-call

Start voice calls via the Moltbot voice-call plugin.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/voice-call/SKILL.md
"""

from .adapter import VoiceCallAdapter
from .service import VoiceCallToolService

# Export as Adapter for load_adapter() compatibility
Adapter = VoiceCallAdapter

__all__ = [
    "Adapter",
    "VoiceCallAdapter",
    "VoiceCallToolService",
]
