"""
Imsg Adapter - Converted from Clawdbot skill: imsg

iMessage/SMS CLI for listing chats, history, watch, and sending.

Original source: ../clawdbot/skills/imsg/SKILL.md
"""

from .adapter import ImsgAdapter
from .service import ImsgToolService

# Export as Adapter for load_adapter() compatibility
Adapter = ImsgAdapter

__all__ = [
    "Adapter",
    "ImsgAdapter",
    "ImsgToolService",
]
