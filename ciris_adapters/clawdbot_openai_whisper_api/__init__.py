"""
OpenaiWhisperApi Adapter - Converted from Clawdbot skill: openai-whisper-api

Transcribe audio via OpenAI Audio Transcriptions API (Whisper).

Original source: ../clawdbot/skills/openai-whisper-api/SKILL.md
"""

from .adapter import OpenaiWhisperApiAdapter
from .service import OpenaiWhisperApiToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OpenaiWhisperApiAdapter

__all__ = [
    "Adapter",
    "OpenaiWhisperApiAdapter",
    "OpenaiWhisperApiToolService",
]
