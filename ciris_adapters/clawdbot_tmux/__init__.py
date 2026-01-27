"""
Tmux Adapter - Converted from Clawdbot skill: tmux

Remote-control tmux sessions for interactive CLIs by sending keystrokes and scraping pane output.

Original source: ../clawdbot/skills/tmux/SKILL.md
"""

from .adapter import TmuxAdapter
from .service import TmuxToolService

# Export as Adapter for load_adapter() compatibility
Adapter = TmuxAdapter

__all__ = [
    "Adapter",
    "TmuxAdapter",
    "TmuxToolService",
]
