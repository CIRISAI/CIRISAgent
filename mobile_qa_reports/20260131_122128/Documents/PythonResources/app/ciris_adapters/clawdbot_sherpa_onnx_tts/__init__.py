"""
SherpaOnnxTts Adapter - Converted from Clawdbot skill: sherpa-onnx-tts

Local text-to-speech via sherpa-onnx (offline, no cloud)

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/sherpa-onnx-tts/SKILL.md
"""

from .adapter import SherpaOnnxTtsAdapter
from .service import SherpaOnnxTtsToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SherpaOnnxTtsAdapter

__all__ = [
    "Adapter",
    "SherpaOnnxTtsAdapter",
    "SherpaOnnxTtsToolService",
]
