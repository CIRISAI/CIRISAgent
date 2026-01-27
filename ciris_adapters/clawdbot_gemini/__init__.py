"""
Gemini Adapter - Converted from Clawdbot skill: gemini

Gemini CLI for one-shot Q&A, summaries, and generation.

Original source: ../clawdbot/skills/gemini/SKILL.md
"""

from .adapter import GeminiAdapter
from .service import GeminiToolService

# Export as Adapter for load_adapter() compatibility
Adapter = GeminiAdapter

__all__ = [
    "Adapter",
    "GeminiAdapter",
    "GeminiToolService",
]
