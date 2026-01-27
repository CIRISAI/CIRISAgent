"""
OpenaiWhisper Adapter - Converted from Clawdbot skill: openai-whisper

Local speech-to-text with the Whisper CLI (no API key).

Original source: ../clawdbot/skills/openai-whisper/SKILL.md
"""

from .adapter import OpenaiWhisperAdapter
from .service import OpenaiWhisperToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OpenaiWhisperAdapter

__all__ = [
    "Adapter",
    "OpenaiWhisperAdapter",
    "OpenaiWhisperToolService",
]
