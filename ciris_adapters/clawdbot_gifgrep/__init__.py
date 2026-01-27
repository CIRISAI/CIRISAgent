"""
Gifgrep Adapter - Converted from Clawdbot skill: gifgrep

Search GIF providers with CLI/TUI, download results, and extract stills/sheets.

Original source: ../clawdbot/skills/gifgrep/SKILL.md
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
