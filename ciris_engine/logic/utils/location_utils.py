"""Location utilities for CIRIS Engine.

Provides functions for tools and adapters to access user location data
stored during setup. Location data is available via environment variables
and graph memory.

Format follows ISO 6709 for coordinates (decimal degrees).
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class UserLocation:
    """User location data in ISO 6709 format.

    Attributes:
        location_string: Human-readable location (e.g., "San Francisco, CA, US")
        latitude: Latitude in decimal degrees (-90 to 90)
        longitude: Longitude in decimal degrees (-180 to 180)
        timezone: IANA timezone (e.g., "America/Los_Angeles")
        country: Country name
        region: Region/state/province name
        city: City name
        share_in_traces: Whether user consented to include location in traces
    """

    location_string: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    share_in_traces: bool = False

    def has_coordinates(self) -> bool:
        """Check if coordinates are available."""
        return self.latitude is not None and self.longitude is not None

    def to_iso6709_string(self) -> Optional[str]:
        """Format coordinates as ISO 6709 string (e.g., +37.7749-122.4194/).

        Returns None if coordinates are not available.
        """
        if self.latitude is None or self.longitude is None:
            return None
        lat_sign = "+" if self.latitude >= 0 else ""
        lon_sign = "+" if self.longitude >= 0 else ""
        return f"{lat_sign}{self.latitude:.6f}{lon_sign}{self.longitude:.6f}/"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {}
        if self.location_string:
            result["location"] = self.location_string
        if self.latitude is not None:
            result["latitude"] = self.latitude
        if self.longitude is not None:
            result["longitude"] = self.longitude
        if self.timezone:
            result["timezone"] = self.timezone
        if self.country:
            result["country"] = self.country
        if self.region:
            result["region"] = self.region
        if self.city:
            result["city"] = self.city
        if self.has_coordinates():
            result["iso6709"] = self.to_iso6709_string()
        return result


def get_user_location() -> UserLocation:
    """Get user location from environment variables.

    This function reads location data set during setup from environment
    variables. Tools can call this to get location context for weather,
    navigation, or other location-aware features.

    Returns:
        UserLocation object with available location data.
    """
    share_in_traces = os.environ.get("CIRIS_SHARE_LOCATION_IN_TRACES", "").lower() == "true"

    # Parse location string into components
    location_string = os.environ.get("CIRIS_USER_LOCATION", "")
    parts = [p.strip() for p in location_string.split(",")] if location_string else []

    # Location string format is written by setup as: Country, Region, City
    # (from most general to most specific)
    # Country only: "United States"
    # Region: "United States, California"
    # City: "United States, California, San Francisco"
    country = parts[0] if parts else None
    region = parts[1] if len(parts) >= 2 else None
    city = parts[2] if len(parts) >= 3 else None

    # Parse coordinates with error handling for malformed values
    lat_str = os.environ.get("CIRIS_USER_LATITUDE", "")
    lon_str = os.environ.get("CIRIS_USER_LONGITUDE", "")
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    if lat_str:
        try:
            latitude = float(lat_str)
        except ValueError:
            logger.warning("Invalid CIRIS_USER_LATITUDE value: %s", lat_str)

    if lon_str:
        try:
            longitude = float(lon_str)
        except ValueError:
            logger.warning("Invalid CIRIS_USER_LONGITUDE value: %s", lon_str)

    return UserLocation(
        location_string=location_string or None,
        latitude=latitude,
        longitude=longitude,
        timezone=os.environ.get("CIRIS_USER_TIMEZONE") or None,
        country=country,
        region=region,
        city=city,
        share_in_traces=share_in_traces,
    )


def get_location_for_context_enrichment() -> Optional[Dict[str, Any]]:
    """Get location data formatted for context enrichment tools.

    Returns a dictionary suitable for including in tool context, or None
    if no location data is available.

    Example return value:
    {
        "location": "San Francisco, California, United States",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "timezone": "America/Los_Angeles",
        "iso6709": "+37.774900-122.419400/"
    }
    """
    location = get_user_location()
    if not location.location_string and not location.has_coordinates():
        return None
    return location.to_dict()


def format_coordinates_for_trace(location: UserLocation) -> Optional[Dict[str, Any]]:
    """Format location for inclusion in telemetry traces.

    Only returns data if user has consented to share location in traces.

    Returns:
        Dictionary with location data for traces, or None if not consented
        or no data available.
    """
    if not location.share_in_traces:
        return None

    result: Dict[str, Any] = {}
    if location.location_string:
        result["user_location"] = location.location_string
    if location.timezone:
        result["user_timezone"] = location.timezone
    if location.has_coordinates():
        result["user_latitude"] = location.latitude
        result["user_longitude"] = location.longitude
        result["user_coordinates_iso6709"] = location.to_iso6709_string()

    return result if result else None
