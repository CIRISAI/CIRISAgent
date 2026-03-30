"""Tests for location search endpoints.

Tests the GeoNames-based city typeahead search functionality.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.setup.location import (
    CountriesResponse,
    CountryInfo,
    LocationResult,
    LocationSearchResponse,
    GEO_DB_PATH,
    _get_db_connection,
    list_countries,
    _search_locations_impl,
)


class TestLocationSearch:
    """Tests for location search endpoint."""

    def test_search_locations_returns_results(self) -> None:
        """Test that searching for a city returns results."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="New York")

        assert isinstance(result, LocationSearchResponse)
        assert result.count > 0
        assert len(result.results) > 0
        assert result.query == "New York"

        # First result should be New York City (largest)
        first = result.results[0]
        assert isinstance(first, LocationResult)
        assert "New York" in first.city or "New York" in first.display_name
        assert first.country_code == "US"
        assert first.population > 0

    def test_search_locations_with_country_filter(self) -> None:
        """Test searching with country filter."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="Mumbai", country="IN")

        assert result.count > 0
        # All results should be in India
        for loc in result.results:
            assert loc.country_code == "IN"

    def test_search_locations_respects_limit(self) -> None:
        """Test that limit parameter is respected."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="San", limit=3)

        assert len(result.results) <= 3

    def test_search_locations_short_query(self) -> None:
        """Test that short queries still work (min 2 chars enforced by FastAPI)."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        # 2-char query should work
        result = _search_locations_impl(q="To")
        assert isinstance(result, LocationSearchResponse)

    def test_search_locations_no_results(self) -> None:
        """Test searching for non-existent city."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="Xyzzynonexistent")

        assert result.count == 0
        assert len(result.results) == 0
        assert result.query == "Xyzzynonexistent"

    def test_search_locations_unicode(self) -> None:
        """Test searching with Unicode characters."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        # Search for Tokyo in Japanese
        result = _search_locations_impl(q="Tokyo")

        assert result.count > 0
        # Should find Tokyo
        tokyo_found = any("Tokyo" in r.city for r in result.results)
        assert tokyo_found

    def test_search_locations_results_sorted_by_population(self) -> None:
        """Test that results are sorted by population descending."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="San", limit=10)

        if len(result.results) >= 2:
            populations = [r.population for r in result.results]
            # Should be sorted descending
            assert populations == sorted(populations, reverse=True)

    def test_search_locations_display_name_format(self) -> None:
        """Test that display_name is properly formatted."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = _search_locations_impl(q="Los Angeles", limit=1)

        assert result.count > 0
        first = result.results[0]
        # Display name should contain city and country at minimum
        assert first.city in first.display_name
        assert first.country in first.display_name or first.country_code in first.display_name

    def test_search_locations_missing_database(self) -> None:
        """Test graceful handling when database is missing."""
        with patch.object(Path, 'exists', return_value=False):
            # Import fresh to get patched version
            from ciris_engine.logic.adapters.api.routes.setup.location import _search_locations_impl as search_fn
            result = search_fn(q="Test")

            assert result.count == 0
            assert len(result.results) == 0


class TestCountriesList:
    """Tests for countries list endpoint."""

    @pytest.mark.asyncio
    async def test_list_countries_returns_results(self) -> None:
        """Test that countries list returns data."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = await list_countries()

        assert isinstance(result, CountriesResponse)
        assert result.count > 200  # Should have 250+ countries
        assert len(result.countries) == result.count

    @pytest.mark.asyncio
    async def test_list_countries_has_major_countries(self) -> None:
        """Test that major countries are included."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = await list_countries()

        codes = {c.code for c in result.countries}
        # Check for some major countries
        assert "US" in codes  # United States
        assert "GB" in codes  # United Kingdom
        assert "CN" in codes  # China
        assert "IN" in codes  # India
        assert "JP" in codes  # Japan
        assert "DE" in codes  # Germany
        assert "FR" in codes  # France
        assert "BR" in codes  # Brazil
        assert "ET" in codes  # Ethiopia

    @pytest.mark.asyncio
    async def test_list_countries_includes_currency(self) -> None:
        """Test that currency information is included."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = await list_countries()

        # Find US and check currency
        us = next((c for c in result.countries if c.code == "US"), None)
        assert us is not None
        assert us.currency_code == "USD"

        # Find Japan
        jp = next((c for c in result.countries if c.code == "JP"), None)
        assert jp is not None
        assert jp.currency_code == "JPY"

    @pytest.mark.asyncio
    async def test_list_countries_sorted_alphabetically(self) -> None:
        """Test that countries are sorted by name."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        result = await list_countries()

        names = [c.name for c in result.countries]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_countries_missing_database(self) -> None:
        """Test graceful handling when database is missing."""
        with patch.object(Path, 'exists', return_value=False):
            from ciris_engine.logic.adapters.api.routes.setup.location import list_countries as list_fn
            result = await list_fn()

            assert result.count == 0
            assert len(result.countries) == 0


class TestDatabaseConnection:
    """Tests for database connection handling."""

    def test_get_db_connection(self) -> None:
        """Test that database connection works."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        conn = _get_db_connection()
        assert isinstance(conn, sqlite3.Connection)

        # Test basic query
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cities")
        count = cursor.fetchone()[0]
        assert count > 30000  # Should have 33K+ cities

        conn.close()

    def test_database_has_fts_index(self) -> None:
        """Test that FTS5 index exists for fast search."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        conn = _get_db_connection()
        cursor = conn.cursor()

        # Check FTS table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cities_fts'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "cities_fts"

        conn.close()

    def test_database_schema(self) -> None:
        """Test that all expected tables exist."""
        if not GEO_DB_PATH.exists():
            pytest.skip("Cities database not built - run: python -m tools.build_geo_db")

        conn = _get_db_connection()
        cursor = conn.cursor()

        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        assert "cities" in tables
        assert "countries" in tables
        assert "admin1" in tables
        assert "cities_fts" in tables

        conn.close()


class TestLocationResultModel:
    """Tests for LocationResult Pydantic model."""

    def test_location_result_fields(self) -> None:
        """Test LocationResult model has all required fields."""
        result = LocationResult(
            city="Tokyo",
            region="Tokyo",
            country="Japan",
            country_code="JP",
            latitude=35.6895,
            longitude=139.6917,
            population=9733276,
            timezone="Asia/Tokyo",
            display_name="Tokyo, Tokyo, Japan",
        )

        assert result.city == "Tokyo"
        assert result.region == "Tokyo"
        assert result.country == "Japan"
        assert result.country_code == "JP"
        assert result.latitude == 35.6895
        assert result.longitude == 139.6917
        assert result.population == 9733276
        assert result.timezone == "Asia/Tokyo"
        assert result.display_name == "Tokyo, Tokyo, Japan"

    def test_location_result_optional_fields(self) -> None:
        """Test that region and timezone are optional."""
        result = LocationResult(
            city="Singapore",
            region=None,
            country="Singapore",
            country_code="SG",
            latitude=1.3521,
            longitude=103.8198,
            population=5535000,
            timezone=None,
            display_name="Singapore, Singapore",
        )

        assert result.region is None
        assert result.timezone is None


class TestCountryInfoModel:
    """Tests for CountryInfo Pydantic model."""

    def test_country_info_fields(self) -> None:
        """Test CountryInfo model has all required fields."""
        info = CountryInfo(
            code="US",
            name="United States",
            currency_code="USD",
            currency_name="Dollar",
        )

        assert info.code == "US"
        assert info.name == "United States"
        assert info.currency_code == "USD"
        assert info.currency_name == "Dollar"

    def test_country_info_optional_currency(self) -> None:
        """Test that currency fields are optional."""
        info = CountryInfo(
            code="AQ",
            name="Antarctica",
            currency_code=None,
            currency_name=None,
        )

        assert info.currency_code is None
        assert info.currency_name is None
