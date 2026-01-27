"""
NanoPdf Adapter - Converted from Clawdbot skill: nano-pdf

Edit PDFs with natural-language instructions using the nano-pdf CLI.

Original source: ../clawdbot/skills/nano-pdf/SKILL.md
"""

from .adapter import NanoPdfAdapter
from .service import NanoPdfToolService

# Export as Adapter for load_adapter() compatibility
Adapter = NanoPdfAdapter

__all__ = [
    "Adapter",
    "NanoPdfAdapter",
    "NanoPdfToolService",
]
