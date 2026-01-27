"""
Himalaya Adapter - Converted from Clawdbot skill: himalaya

CLI to manage emails via IMAP/SMTP. Use `himalaya` to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).

Original source: ../clawdbot/skills/himalaya/SKILL.md
"""

from .adapter import HimalayaAdapter
from .service import HimalayaToolService

# Export as Adapter for load_adapter() compatibility
Adapter = HimalayaAdapter

__all__ = [
    "Adapter",
    "HimalayaAdapter",
    "HimalayaToolService",
]
