"""
SessionLogs Adapter - Converted from Clawdbot skill: session-logs

Search and analyze your own session logs (older/parent conversations) using jq.

Original source: ../clawdbot/skills/session-logs/SKILL.md
"""

from .adapter import SessionLogsAdapter
from .service import SessionLogsToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SessionLogsAdapter

__all__ = [
    "Adapter",
    "SessionLogsAdapter",
    "SessionLogsToolService",
]
