"""
Ordercli Adapter - Converted from Clawdbot skill: ordercli

Foodora-only CLI for checking past orders and active order status (Deliveroo WIP).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/ordercli/SKILL.md
"""

from .adapter import OrdercliAdapter
from .service import OrdercliToolService

# Export as Adapter for load_adapter() compatibility
Adapter = OrdercliAdapter

__all__ = [
    "Adapter",
    "OrdercliAdapter",
    "OrdercliToolService",
]
