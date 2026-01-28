"""
NanoBananaPro Adapter - Converted from Clawdbot skill: nano-banana-pro

Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/nano-banana-pro/SKILL.md
"""

from .adapter import NanoBananaProAdapter
from .service import NanoBananaProToolService

# Export as Adapter for load_adapter() compatibility
Adapter = NanoBananaProAdapter

__all__ = [
    "Adapter",
    "NanoBananaProAdapter",
    "NanoBananaProToolService",
]
