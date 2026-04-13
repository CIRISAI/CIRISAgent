"""Location search and update endpoints for setup wizard.

Provides fast typeahead search for international cities using GeoNames data,
and endpoints to update user location preferences.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Query, Request

from pydantic import BaseModel, Field

from ciris_engine.logic.utils.path_resolution import get_env_file_path

logger = logging.getLogger(__name__)

router = APIRouter()

# Common field description constants
DESC_COUNTRY_NAME = "Country name"
DESC_COUNTRY_CODE = "ISO 3166-1 alpha-2 country code"

# Path to the cities database
# location.py is at ciris_engine/logic/adapters/api/routes/setup/location.py
# Database is at ciris_engine/data/geo/cities.db
# Need 6 parents to get to ciris_engine/
GEO_DB_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "data" / "geo" / "cities.db"


class LocationResult(BaseModel):
    """A single location search result."""

    city: str = Field(..., description="City name")
    region: Optional[str] = Field(None, description="State/province/region name")
    country: str = Field(..., description=DESC_COUNTRY_NAME)
    country_code: str = Field(..., description=DESC_COUNTRY_CODE)
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    population: int = Field(..., description="City population")
    timezone: Optional[str] = Field(None, description="IANA timezone")
    display_name: str = Field(..., description="Formatted display name")


class LocationSearchResponse(BaseModel):
    """Response from location search endpoint."""

    results: list[LocationResult] = Field(default_factory=list, description="Search results")
    query: str = Field(..., description="Original search query")
    count: int = Field(..., description="Number of results")


class CountryInfo(BaseModel):
    """Country information."""

    code: str = Field(..., description=DESC_COUNTRY_CODE)
    name: str = Field(..., description=DESC_COUNTRY_NAME)
    currency_code: Optional[str] = Field(None, description="Currency code (ISO 4217)")
    currency_name: Optional[str] = Field(None, description="Currency name")


class CountriesResponse(BaseModel):
    """Response from countries list endpoint."""

    countries: list[CountryInfo] = Field(default_factory=list, description="List of countries")
    count: int = Field(..., description="Number of countries")


def _get_db_connection() -> sqlite3.Connection:
    """Get a connection to the cities database."""
    conn = sqlite3.connect(str(GEO_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _search_locations_impl(
    q: str,
    country: Optional[str] = None,
    limit: int = 10,
) -> LocationSearchResponse:
    """Implementation of location search (can be called directly for testing).

    Args:
        q: Search query (city name or partial)
        country: Optional country code filter (ISO 3166-1 alpha-2)
        limit: Maximum number of results (1-50)

    Returns:
        LocationSearchResponse with matching cities
    """
    if not GEO_DB_PATH.exists():
        return LocationSearchResponse(results=[], query=q, count=0)

    conn = _get_db_connection()
    cursor = conn.cursor()

    # Use FTS5 for fast prefix search
    search_query = q.replace('"', '""')  # Escape quotes

    try:
        if country:
            # Filter by country
            cursor.execute(
                """
                SELECT c.id, c.name, c.ascii_name, c.country_code, c.admin1_code,
                       c.latitude, c.longitude, c.population, c.timezone,
                       co.name as country_name, a.name as region_name
                FROM cities c
                LEFT JOIN countries co ON c.country_code = co.code
                LEFT JOIN admin1 a ON c.admin1_code = a.code
                WHERE c.id IN (
                    SELECT rowid FROM cities_fts WHERE cities_fts MATCH ?
                )
                AND c.country_code = ?
                ORDER BY c.population DESC
                LIMIT ?
                """,
                (f'"{search_query}"*', country.upper(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT c.id, c.name, c.ascii_name, c.country_code, c.admin1_code,
                       c.latitude, c.longitude, c.population, c.timezone,
                       co.name as country_name, a.name as region_name
                FROM cities c
                LEFT JOIN countries co ON c.country_code = co.code
                LEFT JOIN admin1 a ON c.admin1_code = a.code
                WHERE c.id IN (
                    SELECT rowid FROM cities_fts WHERE cities_fts MATCH ?
                )
                ORDER BY c.population DESC
                LIMIT ?
                """,
                (f'"{search_query}"*', limit),
            )

        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Fallback to LIKE search if FTS fails
        if country:
            cursor.execute(
                """
                SELECT c.id, c.name, c.ascii_name, c.country_code, c.admin1_code,
                       c.latitude, c.longitude, c.population, c.timezone,
                       co.name as country_name, a.name as region_name
                FROM cities c
                LEFT JOIN countries co ON c.country_code = co.code
                LEFT JOIN admin1 a ON c.admin1_code = a.code
                WHERE (c.name LIKE ? OR c.ascii_name LIKE ?)
                AND c.country_code = ?
                ORDER BY c.population DESC
                LIMIT ?
                """,
                (f"{q}%", f"{q}%", country.upper(), limit),
            )
        else:
            cursor.execute(
                """
                SELECT c.id, c.name, c.ascii_name, c.country_code, c.admin1_code,
                       c.latitude, c.longitude, c.population, c.timezone,
                       co.name as country_name, a.name as region_name
                FROM cities c
                LEFT JOIN countries co ON c.country_code = co.code
                LEFT JOIN admin1 a ON c.admin1_code = a.code
                WHERE c.name LIKE ? OR c.ascii_name LIKE ?
                ORDER BY c.population DESC
                LIMIT ?
                """,
                (f"{q}%", f"{q}%", limit),
            )
        rows = cursor.fetchall()

    results = []
    for row in rows:
        region_name = row["region_name"]
        country_name = row["country_name"] or row["country_code"]

        # Build display name
        if region_name:
            display_name = f"{row['name']}, {region_name}, {country_name}"
        else:
            display_name = f"{row['name']}, {country_name}"

        results.append(
            LocationResult(
                city=row["name"],
                region=region_name,
                country=country_name,
                country_code=row["country_code"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                population=row["population"],
                timezone=row["timezone"],
                display_name=display_name,
            )
        )

    conn.close()
    return LocationSearchResponse(results=results, query=q, count=len(results))


@router.get("/location-search")
async def search_locations(
    q: Annotated[str, Query(..., min_length=2, max_length=100, description="Search query (city name or partial)")],
    country: Annotated[
        Optional[str], Query(max_length=2, description="Filter by country code (ISO 3166-1 alpha-2)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum number of results")] = 10,
) -> LocationSearchResponse:
    """Search for cities by name.

    Supports typeahead/autocomplete search with optional country filtering.
    Results are sorted by population (largest cities first).

    Examples:
    - /setup/location-search?q=New - Returns "New York", "New Delhi", "New Orleans", etc.
    - /setup/location-search?q=Paris - Returns Paris, France and other cities named Paris
    - /setup/location-search?q=Tok&country=JP - Returns Tokyo, Japan
    """
    return _search_locations_impl(q=q, country=country, limit=limit)


@router.get("/countries")
async def list_countries() -> CountriesResponse:
    """Get list of all countries with currency information.

    Returns countries sorted alphabetically by name.
    """
    if not GEO_DB_PATH.exists():
        return CountriesResponse(countries=[], count=0)

    conn = _get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT code, name, currency_code, currency_name
        FROM countries
        ORDER BY name
        """
    )

    countries = [
        CountryInfo(
            code=row["code"],
            name=row["name"],
            currency_code=row["currency_code"] if row["currency_code"] else None,
            currency_name=row["currency_name"] if row["currency_name"] else None,
        )
        for row in cursor.fetchall()
    ]

    conn.close()
    return CountriesResponse(countries=countries, count=len(countries))


class UpdateLocationRequest(BaseModel):
    """Request to update user location."""

    city: str = Field(..., description="City name")
    region: Optional[str] = Field(None, description="State/province/region name")
    country: str = Field(..., description=DESC_COUNTRY_NAME)
    country_code: str = Field(..., description=DESC_COUNTRY_CODE)
    latitude: float = Field(..., description="Latitude")
    longitude: float = Field(..., description="Longitude")
    timezone: Optional[str] = Field(None, description="IANA timezone")


class UpdateLocationResponse(BaseModel):
    """Response from update location endpoint."""

    success: bool = Field(..., description="Whether update succeeded")
    message: str = Field(..., description="Status message")
    location_display: str = Field(..., description="Formatted location display string")


def _build_location_display(city: str, region: Optional[str], country: str) -> str:
    """Build formatted location display string."""
    parts = [p for p in [city, region, country] if p]
    return ", ".join(parts)


def _build_location_updates(request: UpdateLocationRequest, location_display: str) -> dict[str, str]:
    """Build dict of env var updates from request."""
    return {
        "CIRIS_USER_CITY": request.city,
        "CIRIS_USER_REGION": request.region or "",
        "CIRIS_USER_COUNTRY": request.country,
        "CIRIS_USER_LOCATION": location_display,
        "CIRIS_USER_LATITUDE": str(request.latitude),
        "CIRIS_USER_LONGITUDE": str(request.longitude),
        "CIRIS_USER_TIMEZONE": request.timezone or "",
    }


def _update_env_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    """Update or append env var lines."""
    for key, value in updates.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f'{key}="{value}"' if value else f"{key}="
                found = True
                break
        if not found and value:
            lines.append(f'{key}="{value}"')
    return lines


def _apply_env_updates(updates: dict[str, str]) -> None:
    """Apply updates to os.environ for immediate effect."""
    for key, value in updates.items():
        if value:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


def _refresh_location_aware_adapters(request: Request) -> None:
    """Notify location-aware adapters (weather, navigation) to refresh their location cache.

    This is called after location updates to ensure adapters pick up new coordinates
    without requiring a full adapter reload.
    """
    try:
        # Check if runtime is available
        if not hasattr(request.app.state, "runtime") or request.app.state.runtime is None:
            logger.debug("[LOCATION] No runtime available, skipping adapter refresh")
            return

        runtime = request.app.state.runtime

        # Check if adapter manager is available
        if not hasattr(runtime, "adapter_manager") or runtime.adapter_manager is None:
            logger.debug("[LOCATION] No adapter manager available, skipping adapter refresh")
            return

        adapter_manager = runtime.adapter_manager

        # Refresh weather adapter if loaded
        if "weather" in adapter_manager.loaded_adapters:
            weather_instance = adapter_manager.loaded_adapters["weather"]
            if hasattr(weather_instance.adapter, "weather_service"):
                weather_service = weather_instance.adapter.weather_service
                if hasattr(weather_service, "refresh_location"):
                    changed = weather_service.refresh_location()
                    if changed:
                        logger.info("[LOCATION] Weather adapter location refreshed")
                    else:
                        logger.debug("[LOCATION] Weather adapter location unchanged")

        # Refresh navigation adapter if loaded
        if "navigation" in adapter_manager.loaded_adapters:
            nav_instance = adapter_manager.loaded_adapters["navigation"]
            if hasattr(nav_instance.adapter, "navigation_service"):
                nav_service = nav_instance.adapter.navigation_service
                if hasattr(nav_service, "refresh_location"):
                    nav_service.refresh_location()
                    logger.info("[LOCATION] Navigation adapter location refreshed")

    except Exception as e:
        # Don't fail the location update if adapter refresh fails
        logger.warning(f"[LOCATION] Failed to refresh adapters: {type(e).__name__}: {e}")


@router.post("/location")
async def update_user_location(
    update_request: UpdateLocationRequest, request: Request
) -> UpdateLocationResponse:
    """Update user's location in the .env file.

    This persists the location so weather and other location-aware
    services can use it. Also notifies running adapters to refresh their
    location cache.
    """
    try:
        env_path = get_env_file_path()
        if not env_path or not env_path.exists():
            logger.error("[LOCATION] .env file not found")
            return UpdateLocationResponse(success=False, message="Configuration file not found", location_display="")

        location_display = _build_location_display(update_request.city, update_request.region, update_request.country)
        updates = _build_location_updates(update_request, location_display)

        # Read, update, and write .env
        lines = env_path.read_text().split("\n")
        lines = _update_env_lines(lines, updates)
        env_path.write_text("\n".join(lines))

        _apply_env_updates(updates)

        # Notify location-aware adapters to refresh their cached location
        _refresh_location_aware_adapters(request)

        logger.info("[LOCATION] User location updated successfully")
        return UpdateLocationResponse(success=True, message="Location updated successfully", location_display=location_display)

    except Exception as e:
        logger.error("[LOCATION] Failed to update location: %s", type(e).__name__)
        return UpdateLocationResponse(success=False, message=f"Failed to update location: {e}", location_display="")
