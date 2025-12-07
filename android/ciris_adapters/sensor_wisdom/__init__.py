"""
Sensor wisdom module for IoT and home automation.

This module provides sensor data interpretation via Home Assistant.
SAFE DOMAIN - Actively filters out medical/health sensors.
"""

from .service import SensorWisdomAdapter

__all__ = ["SensorWisdomAdapter"]
