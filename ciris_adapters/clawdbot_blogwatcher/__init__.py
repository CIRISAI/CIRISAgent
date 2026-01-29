"""
Blogwatcher Adapter - Converted from Clawdbot skill: blogwatcher

Monitor blogs and RSS/Atom feeds for updates using the blogwatcher CLI.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/blogwatcher/SKILL.md
"""

from .adapter import BlogwatcherAdapter
from .service import BlogwatcherToolService

# Export as Adapter for load_adapter() compatibility
Adapter = BlogwatcherAdapter

__all__ = [
    "Adapter",
    "BlogwatcherAdapter",
    "BlogwatcherToolService",
]
