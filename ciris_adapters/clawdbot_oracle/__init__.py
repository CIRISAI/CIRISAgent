"""
Oracle Adapter - Converted from Clawdbot skill: oracle

Best practices for using the oracle CLI (prompt + file bundling, engines, sessions, and file attachment patterns).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/oracle/SKILL.md
"""

from .adapter import OracleAdapter
from .service import OracleToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OracleAdapter

__all__ = [
    "Adapter",
    "OracleAdapter",
    "OracleToolService",
]
