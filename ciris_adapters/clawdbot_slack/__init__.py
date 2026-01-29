"""
Slack Adapter - Converted from Clawdbot skill: slack

Use when you need to control Slack from Moltbot via the slack tool, including reacting to messages or pinning/unpinning items in Slack channels or DMs.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/slack/SKILL.md
"""

from .adapter import SlackAdapter
from .service import SlackToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SlackAdapter

__all__ = [
    "Adapter",
    "SlackAdapter",
    "SlackToolService",
]
