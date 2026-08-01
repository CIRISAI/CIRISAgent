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
    if location.timezone:
        result["user_timezone"] = location.timezone

    # RAW COORDINATES ARE NOT EMITTED. See CIRISAgent#959.
    #
    # This used to ship user_latitude / user_longitude / an ISO-6709 string at
    # {:.6f} — roughly 11 cm — plus a location_string containing the city.
    #
    # CEG 0.8 §0.8 defines exactly one location representation: a signed
    # LocationProof carrying an H3 cell_id at resolution <= 7, which persist
    # enforces at admission via validate_location_cell. Raw lat/lon in a trace
    # payload is not a LocationProof, so that check never runs on it — this was
    # a PARALLEL CHANNEL around the rough-only bound, and persist's own comment
    # calls the substrate "the second line of defense after client UI gating".
    # A second line of defense is not much use if there is a path that misses it.
    #
    # And it bought nothing. Regional membership comes from matching an H3 cell
    # against communities_containing; no cell means no match, so the precise
    # fields enabled no feature while carrying the whole privacy cost.
    #
    # The proof itself is not minted here: this repo has no H3 encoder, and
    # persist already implements the representation. Emitting our own would be
    # authoring a trust primitive at the agent tier — the thing that keeps
    # forking when it is restated rather than read. Tracked in #959; when an
    # encoder is exposed, a `location_proof` goes here and its resolution is
    # READ from consent_disclosure()["location"]["max_resolution"], never
    # restated as a literal 7.
    if location.has_coordinates():
        proof = _mint_location_proof(location)
        if proof is not None:
            result["location_proof"] = proof

    return result if result else None


def _mint_location_proof(location: UserLocation) -> Optional[str]:
    """Ask the SUBSTRATE for a signed LocationProof. Never mint one here.

    The wheel owns this representation: persist implements H3 in
    ``src/federation/location.rs`` and enforces the CEG 0.8 §0.8.1 rough-only
    bound at admission via ``validate_location_cell``. ``Engine`` can already
    READ them (``list_signed_location_proofs_since``); minting is the missing
    half, tracked upstream at CIRISServer#341.

    Deliberately not implemented in Python. Doing so would mean:

    * restating a rule the substrate owns — the failure mode this project keeps
      hitting. A harness restated the consent prefixes and hid a dead trace
      plane for eight releases; a docstring restated the consent route and
      404'd the wizard two releases after the code was fixed; and
    * an unshippable dependency: ``h3`` publishes NO Android wheel and is a C
      extension, so Chaquopy cannot build it. ciris-server already ships
      android_24 wheels for all three ABIs.

    getattr-guarded so this activates by itself the moment the wheel exposes
    the entry point — no agent release required to turn it on. Resolution is
    READ from the disclosure, never restated as a literal 7.
    """
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        mint = getattr(ciris_server, "mint_location_proof", None)
        if mint is None:
            logger.debug(
                "location: coordinates present, no location_proof emitted — the substrate "
                "exposes no mint yet (CIRISServer#341). Rough-only holds; regional "
                "membership stays unavailable, which is the correct degradation."
            )
            return None

        # resolution=None => the build's own default, the same convention
        # author_federation_consent(peer, None, True) uses for prefixes.
        proof = mint(location.latitude, location.longitude, None)
        logger.info("location: signed location_proof minted by the substrate (rough-only, build default)")
        return str(proof)
    except Exception as exc:  # noqa: BLE001 — location must never break a trace
        logger.warning("location: proof mint failed (non-fatal): %s", exc)
        return None
