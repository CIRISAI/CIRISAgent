"""
Peekaboo Adapter - Converted from Clawdbot skill: peekaboo

Capture and automate macOS UI with the Peekaboo CLI.

Original source: ../clawdbot/skills/peekaboo/SKILL.md
"""

from .adapter import PeekabooAdapter
from .service import PeekabooToolService

# Export as Adapter for load_adapter() compatibility
Adapter = PeekabooAdapter

__all__ = [
    "Adapter",
    "PeekabooAdapter",
    "PeekabooToolService",
]
