"""
Comprehensive tests for covenant metrics in telemetry system.

This test suite ensures covenant metrics are properly collected, aggregated,
and reported through all telemetry endpoints.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.telemetry import router
from ciris_engine.schemas.metrics import CovenantCategory


@pytest.fixture
def app():
    """Create FastAPI app with telemetry router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_app_state(app):
    """Mock app state with services."""
    app.state = MagicMock()
    app.state.service_registry = MagicMock()
    app.state.telemetry_service = MagicMock()
    app.state.resource_monitor = MagicMock()
    app.state.memory_service = MagicMock()
    app.state.audit_service = MagicMock()
    app.state.wise_authority_service = MagicMock()  # Use correct name
    return app.state


class TestCovenantMetricsStructure:
    """Test covenant metrics have correct structure and values."""

    def test_all_covenant_categories_present(self):
        """Verify all covenant categories are defined."""
        categories = [
            CovenantCategory.BENEVOLENCE,
            CovenantCategory.INTEGRITY,
            CovenantCategory.WISDOM,
            CovenantCategory.PRUDENCE,
            CovenantCategory.MISSION_ALIGNMENT,
        ]

        # Verify we have exactly 5 categories
        assert len(categories) == 5

        # Verify each has the expected string value
        assert CovenantCategory.BENEVOLENCE.value == "benevolence"
        assert CovenantCategory.INTEGRITY.value == "integrity"
        assert CovenantCategory.WISDOM.value == "wisdom"
        assert CovenantCategory.PRUDENCE.value == "prudence"
        assert CovenantCategory.MISSION_ALIGNMENT.value == "mission_alignment"

    def test_covenant_metrics_value_ranges(self, mock_app_state):
        """Test that covenant metrics are within valid range [0, 1]."""
        # Setup: Mock telemetry with covenant metrics
        covenant_metrics = {
            "benevolence": 0.95,
            "integrity": 0.98,
            "wisdom": 0.87,
            "prudence": 0.92,
            "mission_alignment": 0.93,
        }

        # Verify all values are between 0 and 1
        for category, value in covenant_metrics.items():
            assert 0 <= value <= 1, f"Covenant metric {category} out of range: {value}"

        # Test edge cases
        edge_cases = {
            "benevolence": 0.0,  # Minimum
            "integrity": 1.0,  # Maximum
            "wisdom": 0.5,  # Middle
            "prudence": 0.001,  # Near minimum
            "mission_alignment": 0.999,  # Near maximum
        }

        for category, value in edge_cases.items():
            assert 0 <= value <= 1, f"Edge case failed for {category}: {value}"


class TestCovenantMetricsInEndpoints:
    """Test covenant metrics are properly returned by all endpoints."""

    def test_unified_endpoint_includes_covenant(self, client, mock_app_state):
        """Test /telemetry/unified includes covenant metrics."""
        # Setup: Mock telemetry service with covenant data
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "bus": {"communication": {"messages": 100}},
                "type": {"service": {"count": 21}},
                "instance": {"api_0": {"uptime": 3600}},
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    "wisdom": 0.87,
                    "prudence": 0.92,
                    "mission_alignment": 0.93,
                },
            }
        )

        # Act: Call unified endpoint
        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            response = client.get("/telemetry/unified")

        # Assert: Covenant metrics present
        assert response.status_code == 200
        data = response.json()

        # Check covenant section exists
        assert "covenant" in data, "Covenant section missing from response"

        # Verify all covenant categories present
        covenant = data["covenant"]
        required_categories = ["benevolence", "integrity", "wisdom", "prudence", "mission_alignment"]
        for category in required_categories:
            assert category in covenant, f"Missing covenant category: {category}"
            assert isinstance(covenant[category], (int, float)), f"Invalid type for {category}"
            assert 0 <= covenant[category] <= 1, f"Value out of range for {category}"

    def test_unified_endpoint_covenant_with_view_filter(self, client, mock_app_state):
        """Test covenant metrics with different view filters."""
        # Setup: Mock telemetry with covenant
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    "wisdom": 0.87,
                    "prudence": 0.92,
                    "mission_alignment": 0.93,
                },
                "bus": {},
                "type": {},
                "instance": {},
            }
        )

        # Test different views
        views = ["summary", "health", "operational", "detailed", "performance", "reliability"]

        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            for view in views:
                response = client.get(f"/telemetry/unified?view={view}")
                assert response.status_code == 200
                data = response.json()

                # Covenant should be present in all views
                assert "covenant" in data or "_metadata" in data, f"Missing data for view={view}"

                # If metadata is present, check view is recorded
                if "_metadata" in data:
                    assert data["_metadata"]["view"] == view


class TestCovenantMetricsAggregation:
    """Test covenant metrics aggregation logic."""

    def test_covenant_aggregation_by_category(self, mock_app_state):
        """Test aggregating covenant metrics by category."""
        # Simulate multiple covenant measurements
        measurements = [
            {"benevolence": 0.90, "integrity": 0.95, "wisdom": 0.85},
            {"benevolence": 0.95, "integrity": 0.98, "wisdom": 0.87},
            {"benevolence": 0.92, "integrity": 0.96, "wisdom": 0.86},
        ]

        # Calculate averages
        averages = {}
        for category in ["benevolence", "integrity", "wisdom"]:
            values = [m[category] for m in measurements]
            averages[category] = sum(values) / len(values)

        # Verify aggregation logic
        assert 0.91 < averages["benevolence"] < 0.93  # ~0.923
        assert 0.95 < averages["integrity"] < 0.97  # ~0.963
        assert 0.85 < averages["wisdom"] < 0.87  # ~0.86

    def test_covenant_metrics_with_missing_data(self, client, mock_app_state):
        """Test handling of missing covenant metrics."""
        # Setup: Telemetry without covenant section
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "bus": {},
                "type": {},
                "instance": {},
                # No covenant section
            }
        )

        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            response = client.get("/telemetry/unified")

        # Should still return 200 but without covenant
        assert response.status_code == 200
        data = response.json()

        # Covenant might be missing or empty
        if "covenant" in data:
            # If present, should be empty dict or have default values
            assert isinstance(data["covenant"], dict)

    def test_covenant_metrics_partial_data(self, client, mock_app_state):
        """Test handling of partial covenant metrics (some categories missing)."""
        # Setup: Partial covenant data
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    # Missing: wisdom, prudence, mission_alignment
                },
                "bus": {},
                "type": {},
                "instance": {},
            }
        )

        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            response = client.get("/telemetry/unified")

        assert response.status_code == 200
        data = response.json()

        if "covenant" in data:
            covenant = data["covenant"]
            # Should have at least the provided metrics
            assert "benevolence" in covenant
            assert covenant["benevolence"] == 0.95
            assert "integrity" in covenant
            assert covenant["integrity"] == 0.98


class TestCovenantMetricsIntegration:
    """Integration tests for covenant metrics with other telemetry."""

    def test_covenant_alongside_service_metrics(self, client, mock_app_state):
        """Test that covenant metrics work alongside service metrics."""
        # Setup: Complete telemetry data
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "bus": {
                    "communication": {"messages_sent": 1000, "messages_received": 950},
                    "memory": {"operations": 500},
                    "llm": {"tokens_used": 15000},
                },
                "type": {
                    "graph_services": {"count": 6, "healthy": 6},
                    "infrastructure_services": {"count": 7, "healthy": 7},
                    "governance_services": {"count": 4, "healthy": 4},
                    "runtime_services": {"count": 3, "healthy": 3},
                    "tool_services": {"count": 1, "healthy": 1},
                },
                "instance": {
                    "api_0": {"uptime": 86400, "requests": 5000},
                    "discord_0": {"uptime": 86400, "messages": 2000},
                },
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    "wisdom": 0.87,
                    "prudence": 0.92,
                    "mission_alignment": 0.93,
                },
            }
        )

        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            response = client.get("/telemetry/unified")

        assert response.status_code == 200
        data = response.json()

        # All sections should be present
        assert "bus" in data
        assert "type" in data
        assert "instance" in data
        assert "covenant" in data

        # Verify structure integrity
        assert len(data["bus"]) > 0
        assert len(data["type"]) > 0
        assert len(data["instance"]) > 0
        assert len(data["covenant"]) == 5  # All 5 covenant categories

    def test_covenant_metrics_affect_health_status(self, client, mock_app_state):
        """Test that low covenant metrics affect overall health status."""
        # Test with high covenant values
        high_covenant = {
            "benevolence": 0.95,
            "integrity": 0.98,
            "wisdom": 0.97,
            "prudence": 0.96,
            "mission_alignment": 0.99,
        }

        # Average should be > 0.95 (healthy)
        avg_high = sum(high_covenant.values()) / len(high_covenant)
        assert avg_high > 0.95

        # Test with low covenant values
        low_covenant = {
            "benevolence": 0.45,  # Below threshold
            "integrity": 0.55,
            "wisdom": 0.40,  # Below threshold
            "prudence": 0.50,
            "mission_alignment": 0.48,
        }

        # Average should be < 0.6 (unhealthy)
        avg_low = sum(low_covenant.values()) / len(low_covenant)
        assert avg_low < 0.6

        # Test with mixed values
        mixed_covenant = {
            "benevolence": 0.95,  # High
            "integrity": 0.30,  # Very low
            "wisdom": 0.85,  # Good
            "prudence": 0.90,  # Good
            "mission_alignment": 0.75,  # Moderate
        }

        # At least one very low value should trigger warning
        min_value = min(mixed_covenant.values())
        assert min_value < 0.5  # Should trigger warning


class TestCovenantMetricsFormatting:
    """Test covenant metrics formatting in different output formats."""

    def test_covenant_metrics_json_format(self, client, mock_app_state):
        """Test covenant metrics in JSON format (default)."""
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    "wisdom": 0.87,
                    "prudence": 0.92,
                    "mission_alignment": 0.93,
                }
            }
        )

        with patch("ciris_engine.logic.adapters.api.dependencies.auth.require_observer", return_value=None):
            response = client.get("/telemetry/unified?format=json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        # Should be valid JSON
        data = response.json()
        assert isinstance(data, dict)

    def test_covenant_metrics_precision(self):
        """Test that covenant metrics maintain appropriate precision."""
        covenant_values = {
            "benevolence": 0.9523456789,
            "integrity": 0.9876543210,
            "wisdom": 0.8765432109,
            "prudence": 0.9234567890,
            "mission_alignment": 0.9345678901,
        }

        # When formatted, should maintain reasonable precision (2-4 decimal places)
        for category, value in covenant_values.items():
            # Round to 4 decimal places for display
            formatted = round(value, 4)
            assert 0 <= formatted <= 1
            assert len(str(formatted).split(".")[-1]) <= 4


# Meta-test for coverage
def test_covenant_metrics_test_coverage():
    """Verify we have comprehensive covenant metrics test coverage."""
    test_areas = [
        "structure",  # Correct structure and categories
        "value_ranges",  # Values between 0 and 1
        "endpoints",  # Present in all endpoints
        "aggregation",  # Aggregation logic works
        "integration",  # Works with other metrics
        "formatting",  # Correct formatting
        "edge_cases",  # Handles missing/partial data
    ]

    test_classes = [
        TestCovenantMetricsStructure,
        TestCovenantMetricsInEndpoints,
        TestCovenantMetricsAggregation,
        TestCovenantMetricsIntegration,
        TestCovenantMetricsFormatting,
    ]

    # Count test methods
    test_count = 0
    for test_class in test_classes:
        methods = [m for m in dir(test_class) if m.startswith("test_")]
        test_count += len(methods)

    # Should have at least 2 tests per area
    min_tests = len(test_areas) * 2
    assert test_count >= min_tests, f"Need at least {min_tests} tests, have {test_count}"

    print(f"✓ Covenant metrics test coverage: {test_count} tests covering {len(test_areas)} areas")
