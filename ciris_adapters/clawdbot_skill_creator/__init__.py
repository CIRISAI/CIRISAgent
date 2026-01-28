"""
SkillCreator Adapter - Converted from Clawdbot skill: skill-creator

Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/skill-creator/SKILL.md
"""

from .adapter import SkillCreatorAdapter
from .service import SkillCreatorToolService

# Export as Adapter for load_adapter() compatibility
Adapter = SkillCreatorAdapter

__all__ = [
    "Adapter",
    "SkillCreatorAdapter",
    "SkillCreatorToolService",
]
