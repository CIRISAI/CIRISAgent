"""
1password Adapter - Converted from Clawdbot skill: 1password

Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.

Original source: ../clawdbot/skills/1password/SKILL.md
"""

from .adapter import OnePasswordAdapter
from .service import OnePasswordToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OnePasswordAdapter

__all__ = [
    "Adapter",
    "OnePasswordAdapter",
    "OnePasswordToolService",
]
