"""
Wacli Adapter - Converted from Clawdbot skill: wacli

Send WhatsApp messages to other people or search/sync WhatsApp history via the wacli CLI (not for normal user chats).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/wacli/SKILL.md
"""

from .adapter import WacliAdapter
from .service import WacliToolService

# Export as Adapter for load_adapter() compatibility
Adapter = WacliAdapter

__all__ = [
    "Adapter",
    "WacliAdapter",
    "WacliToolService",
]
