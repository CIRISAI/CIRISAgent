"""
AppleReminders Adapter - Converted from Clawdbot skill: apple-reminders

Manage Apple Reminders via the `remindctl` CLI on macOS (list, add, edit, complete, delete). Supports lists, date filters, and JSON/plain output.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/apple-reminders/SKILL.md
"""

from .adapter import AppleRemindersAdapter
from .service import AppleRemindersToolService

# Export as Adapter for load_adapter() compatibility
Adapter = AppleRemindersAdapter

__all__ = [
    "Adapter",
    "AppleRemindersAdapter",
    "AppleRemindersToolService",
]
