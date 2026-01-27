"""
CodingAgent Adapter - Converted from Clawdbot skill: coding-agent

Run Codex CLI, Claude Code, OpenCode, or Pi Coding Agent via background process for programmatic control.

Original source: ../clawdbot/skills/coding-agent/SKILL.md
"""

from .adapter import CodingAgentAdapter
from .service import CodingAgentToolService

# Export as Adapter for load_adapter() compatibility
Adapter = CodingAgentAdapter

__all__ = [
    "Adapter",
    "CodingAgentAdapter",
    "CodingAgentToolService",
]
