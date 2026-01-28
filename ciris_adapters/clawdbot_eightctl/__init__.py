"""
Eightctl Adapter - Converted from Clawdbot skill: eightctl

Control Eight Sleep pods (status, temperature, alarms, schedules).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/eightctl/SKILL.md
"""

from .adapter import EightctlAdapter
from .service import EightctlToolService

# Export as Adapter for load_adapter() compatibility
Adapter = EightctlAdapter

__all__ = [
    "Adapter",
    "EightctlAdapter",
    "EightctlToolService",
]
