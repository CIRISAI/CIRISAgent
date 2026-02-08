"""
Gifgrep Adapter - Converted from CIRIS adapter: gifgrep

Search GIF providers with CLI/TUI, download results, and extract stills/sheets.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/gifgrep/SKILL.md
"""

from .adapter import GifgrepAdapter
from .service import GifgrepToolService

# Export as Adapter for load_adapter() compatibility
Adapter = GifgrepAdapter

__all__ = [
    "Adapter",
    "GifgrepAdapter",
    "GifgrepToolService",
]
