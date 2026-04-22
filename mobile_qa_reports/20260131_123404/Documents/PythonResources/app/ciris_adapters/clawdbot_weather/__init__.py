"""
Weather Adapter - Converted from Clawdbot skill: weather

Get current weather and forecasts (no API key required).

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/weather/SKILL.md
"""

from .adapter import WeatherAdapter
from .service import WeatherToolService

# Export as Adapter for load_adapter() compatibility
Adapter = WeatherAdapter

__all__ = [
    "Adapter",
    "WeatherAdapter",
    "WeatherToolService",
]
