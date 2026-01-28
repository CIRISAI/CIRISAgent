"""
Obsidian Adapter - Converted from Clawdbot skill: obsidian

Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/obsidian/SKILL.md
"""

from .adapter import ObsidianAdapter
from .service import ObsidianToolService

# Export as Adapter for load_adapter() compatibility
Adapter = ObsidianAdapter

__all__ = [
    "Adapter",
    "ObsidianAdapter",
    "ObsidianToolService",
]
