"""
Clawdhub Adapter - Converted from Clawdbot skill: clawdhub

Use the ClawdHub CLI to search, install, update, and publish agent skills from clawdhub.com. Use when you need to fetch new skills on the fly, sync installed skills to latest or a specific version, or publish new/updated skill folders with the npm-installed clawdhub CLI.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/clawdhub/SKILL.md
"""

from .adapter import ClawdhubAdapter
from .service import ClawdhubToolService

# Export as Adapter for load_adapter() compatibility
Adapter = ClawdhubAdapter

__all__ = [
    "Adapter",
    "ClawdhubAdapter",
    "ClawdhubToolService",
]
