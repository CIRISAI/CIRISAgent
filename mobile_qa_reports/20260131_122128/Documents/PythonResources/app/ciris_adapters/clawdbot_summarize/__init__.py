"""
Summarize Adapter - Converted from Clawdbot skill: summarize

Summarize or extract text/transcripts from URLs, podcasts, and local files (great fallback for “transcribe this YouTube/video”).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/summarize/SKILL.md
"""

from .adapter import SummarizeAdapter
from .service import SummarizeToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SummarizeAdapter

__all__ = [
    "Adapter",
    "SummarizeAdapter",
    "SummarizeToolService",
]
