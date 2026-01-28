"""
Bluebubbles Adapter - Converted from Clawdbot skill: bluebubbles

Build or update the BlueBubbles external channel plugin for Moltbot (extension package, REST send/probe, webhook inbound).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/bluebubbles/SKILL.md
"""

from .adapter import BluebubblesAdapter
from .service import BluebubblesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = BluebubblesAdapter

__all__ = [
    "Adapter",
    "BluebubblesAdapter",
    "BluebubblesToolService",
]
