"""
Navigation tool service for geocoding and routing.

This module provides navigation tools using OpenStreetMap:
- Geocoding (address to coordinates)
- Reverse geocoding (coordinates to address)
- Route calculation (distance and duration)

SAFE DOMAIN - No medical/health capabilities.
"""

from .adapter import Adapter, NavigationAdapter
from .configurable import NavigationConfigurableAdapter
from .service import NavigationToolService

__all__ = [
    "NavigationToolService",
    "NavigationAdapter",
    "Adapter",
    "NavigationConfigurableAdapter",
]
