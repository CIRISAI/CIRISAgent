"""
ModelUsage Adapter - Converted from Clawdbot skill: model-usage

Use CodexBar CLI local cost usage to summarize per-model usage for Codex or Claude, including the current (most recent) model or a full model breakdown. Trigger when asked for model-level usage/cost data from codexbar, or when you need a scriptable per-model summary from codexbar cost JSON.

Original source: ../clawdbot/skills/model-usage/SKILL.md
"""

from .adapter import ModelUsageAdapter
from .service import ModelUsageToolService

# Export as Adapter for load_adapter() compatibility
Adapter = ModelUsageAdapter

__all__ = [
    "Adapter",
    "ModelUsageAdapter",
    "ModelUsageToolService",
]
