"""Tests for context enrichment API endpoint."""

from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.system.adapters import (
    get_context_enrichment_cache,
    router,
)


# Patch path for functions imported inside the endpoint
PATCH_MODULE = "ciris_engine.logic.context.system_snapshot_helpers"


@pytest.fixture
def app():
    """Create test FastAPI app with adapters router."""
    app = FastAPI()
    app.include_router(router, prefix="/v1/system")

    # Mock runtime with enrichment cache
    app.state.runtime = Mock()

    return app


@pytest.fixture
def mock_auth():
    """Mock auth dependency."""
    with patch(
        "ciris_engine.logic.adapters.api.routes.system.adapters.require_observer"
    ) as mock:
        mock.return_value = Mock()
        yield mock


@pytest.fixture
def mock_enrichment_cache():
    """Mock enrichment cache with test data."""
    with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache:
        cache = Mock()
        cache.get_all_entries.return_value = {
            "home:ha_list_entities": {
                "count": 5,
                "entities": [
                    {"entity_id": "light.living_room", "state": "on"},
                    {"entity_id": "switch.garage", "state": "off"},
                ],
            }
        }
        cache.stats = {
            "entries": 1,
            "hits": 10,
            "misses": 5,
            "hit_rate_pct": 66.7,
            "startup_populated": True,
        }
        mock_get_cache.return_value = cache
        yield cache


class TestGetContextEnrichmentCache:
    """Tests for GET /adapters/context-enrichment endpoint."""

    @pytest.mark.asyncio
    async def test_returns_enrichment_data(self, mock_enrichment_cache):
        """Returns enrichment data from cache."""
        # Create mock request
        request = Mock()
        request.app = Mock()
        request.app.state = Mock()
        request.app.state.runtime = None

        auth = Mock()

        # Import directly since we can't use TestClient easily with async
        result = await get_context_enrichment_cache(request, auth, refresh=False)

        assert result.data["entries"] == mock_enrichment_cache.get_all_entries()
        assert result.data["stats"]["entry_count"] == 1
        assert result.data["stats"]["hits"] == 10
        assert result.data["stats"]["misses"] == 5
        assert result.data["stats"]["hit_rate_pct"] == 66.7
        assert result.data["stats"]["startup_populated"] is True

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_entries(self):
        """Returns empty entries when cache is empty."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache:
            cache = Mock()
            cache.get_all_entries.return_value = {}
            cache.stats = {
                "entries": 0,
                "hits": 0,
                "misses": 0,
                "hit_rate_pct": 0.0,
                "startup_populated": False,
            }
            mock_get_cache.return_value = cache

            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = None

            result = await get_context_enrichment_cache(request, Mock(), refresh=False)

            assert result.data["entries"] == {}
            assert result.data["stats"]["entry_count"] == 0

    @pytest.mark.asyncio
    async def test_refresh_triggers_cache_refresh(self):
        """Refresh parameter triggers cache refresh."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache, patch(
            f"{PATCH_MODULE}.refresh_enrichment_cache", new_callable=AsyncMock
        ) as mock_refresh:
            cache = Mock()
            cache.get_all_entries.return_value = {"test:tool": {"data": "refreshed"}}
            cache.stats = {"entries": 1, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "startup_populated": False}
            mock_get_cache.return_value = cache
            mock_refresh.return_value = {"test:tool": {"data": "refreshed"}}

            runtime = Mock()
            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = runtime

            result = await get_context_enrichment_cache(request, Mock(), refresh=True)

            mock_refresh.assert_called_once_with(runtime)
            assert result.data["entries"]["test:tool"]["data"] == "refreshed"

    @pytest.mark.asyncio
    async def test_refresh_skipped_when_no_runtime(self):
        """Refresh is skipped when runtime is not available."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache, patch(
            f"{PATCH_MODULE}.refresh_enrichment_cache", new_callable=AsyncMock
        ) as mock_refresh:
            cache = Mock()
            cache.get_all_entries.return_value = {}
            cache.stats = {"entries": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "startup_populated": False}
            mock_get_cache.return_value = cache

            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = None

            await get_context_enrichment_cache(request, Mock(), refresh=True)

            mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_refresh_by_default(self):
        """Refresh is not triggered by default (refresh=False)."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache, patch(
            f"{PATCH_MODULE}.refresh_enrichment_cache", new_callable=AsyncMock
        ) as mock_refresh:
            cache = Mock()
            cache.get_all_entries.return_value = {}
            cache.stats = {"entries": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "startup_populated": False}
            mock_get_cache.return_value = cache

            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = Mock()

            await get_context_enrichment_cache(request, Mock(), refresh=False)

            mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_cache_exception(self):
        """Handles exceptions from cache gracefully."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache:
            mock_get_cache.side_effect = Exception("Cache error")

            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = None

            with pytest.raises(Exception) as exc_info:
                await get_context_enrichment_cache(request, Mock(), refresh=False)

            assert "Cache error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_refresh_exception(self):
        """Handles exceptions from refresh gracefully."""
        with patch(f"{PATCH_MODULE}.get_enrichment_cache") as mock_get_cache, patch(
            f"{PATCH_MODULE}.refresh_enrichment_cache", new_callable=AsyncMock
        ) as mock_refresh:
            cache = Mock()
            cache.get_all_entries.return_value = {}
            cache.stats = {"entries": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "startup_populated": False}
            mock_get_cache.return_value = cache
            mock_refresh.side_effect = Exception("Refresh error")

            request = Mock()
            request.app = Mock()
            request.app.state = Mock()
            request.app.state.runtime = Mock()

            with pytest.raises(Exception) as exc_info:
                await get_context_enrichment_cache(request, Mock(), refresh=True)

            assert "Refresh error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_returns_correct_stats_structure(self, mock_enrichment_cache):
        """Returns stats in correct structure."""
        request = Mock()
        request.app = Mock()
        request.app.state = Mock()
        request.app.state.runtime = None

        result = await get_context_enrichment_cache(request, Mock(), refresh=False)

        stats = result.data["stats"]
        assert "entry_count" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate_pct" in stats
        assert "startup_populated" in stats
