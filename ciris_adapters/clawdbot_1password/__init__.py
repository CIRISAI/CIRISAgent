"""
Onepassword Adapter - Converted from Clawdbot skill: 1password

Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/1password/SKILL.md
"""

from .adapter import OnepasswordAdapter
from .service import OnepasswordToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OnepasswordAdapter

__all__ = [
    "Adapter",
    "OnepasswordAdapter",
    "OnepasswordToolService",
]
