"""
OpenaiImageGen Adapter - Converted from Clawdbot skill: openai-image-gen

Batch-generate images via OpenAI Images API. Random prompt sampler + `index.html` gallery.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/openai-image-gen/SKILL.md
"""

from .adapter import OpenaiImageGenAdapter
from .service import OpenaiImageGenToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OpenaiImageGenAdapter

__all__ = [
    "Adapter",
    "OpenaiImageGenAdapter",
    "OpenaiImageGenToolService",
]
