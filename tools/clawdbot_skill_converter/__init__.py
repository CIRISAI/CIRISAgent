"""
Clawdbot Skill Converter - Convert Clawdbot SKILL.md files to CIRIS adapters.

Usage:
    python -m tools.clawdbot_skill_converter /path/to/skills /path/to/output
"""

from .converter import SkillConverter, convert_skill, convert_skills_batch
from .parser import ParsedSkill, SkillParser, SkillRequirements

__all__ = [
    "SkillConverter",
    "SkillParser",
    "ParsedSkill",
    "SkillRequirements",
    "convert_skill",
    "convert_skills_batch",
]
