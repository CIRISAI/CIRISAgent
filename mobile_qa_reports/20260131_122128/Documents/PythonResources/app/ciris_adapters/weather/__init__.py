"""
Weather tool service for atmospheric conditions and forecasts.

This module provides weather tools using NOAA and OpenWeatherMap APIs:
- Current weather conditions
- Weather forecast
- Weather alerts

SAFE DOMAIN - No medical/health capabilities.
"""

from .adapter import Adapter, WeatherAdapter
from .configurable import WeatherConfigurableAdapter
from .service import WeatherToolService

__all__ = ["WeatherToolService", "WeatherAdapter", "Adapter", "WeatherConfigurableAdapter"]
