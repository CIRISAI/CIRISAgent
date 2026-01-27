"""
Github Adapter - Converted from Clawdbot skill: github

Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries.

Original source: ../clawdbot/skills/github/SKILL.md
"""

from .adapter import GithubAdapter
from .service import GithubToolService

# Export as Adapter for load_adapter() compatibility
Adapter = GithubAdapter

__all__ = [
    "Adapter",
    "GithubAdapter",
    "GithubToolService",
]
