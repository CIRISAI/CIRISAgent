"""
Openhue Adapter - Converted from CIRIS adapter: openhue

Control Philips Hue lights/scenes via the OpenHue CLI.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/openhue/SKILL.md
"""

from .adapter import OpenhueAdapter
from .service import OpenhueToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OpenhueAdapter

__all__ = [
    "Adapter",
    "OpenhueAdapter",
    "OpenhueToolService",
]
