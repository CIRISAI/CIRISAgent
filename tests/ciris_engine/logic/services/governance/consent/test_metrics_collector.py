"""
Tests for ConsentMetricsCollector.

Focuses on testing metrics collection methods with new schema-based parameter grouping.
"""

import pytest
from datetime import datetime, timedelta, timezone

from ciris_engine.logic.services.governance.consent.metrics import ConsentMetricsCollector
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentStatus,
    ConsentStream,
    DecayCounters,
    OperationalCounters,
    PartnershipCounters,
)


class TestMetricsCollector:
    """Test metrics collector with new schema-based approach."""

    def test_collect_stream_distribution_empty_cache(self, metrics_collector, mock_time_service):
        """Test collect_stream_distribution with empty cache."""
        # Setup
        consent_cache = {}
        now = mock_time_service.now()

        # Execute
        metrics = metrics_collector.collect_stream_distribution(consent_cache, now)

        # Assert
        assert metrics["consent_active_users"] == 0.0
        assert metrics["consent_temporary_percent"] == 0.0
        assert metrics["consent_partnered_percent"] == 0.0
        assert metrics["consent_anonymous_percent"] == 0.0
        assert metrics["consent_average_age_days"] == 0.0

    def test_collect_stream_distribution_with_mixed_cache(
        self, metrics_collector, mixed_consent_cache, mock_time_service
    ):
        """Test collect_stream_distribution calculates distribution correctly."""
        # Setup
        now = mock_time_service.now()

        # Execute
        metrics = metrics_collector.collect_stream_distribution(mixed_consent_cache, now)

        # Assert
        total_users = len(mixed_consent_cache)
        assert metrics["consent_active_users"] == float(total_users)

        # Verify percentages add up correctly
        total_percent = (
            metrics["consent_temporary_percent"]
            + metrics["consent_partnered_percent"]
            + metrics["consent_anonymous_percent"]
        )
        # Should be close to 100% (allowing for rounding)
        assert abs(total_percent - 100.0) < 1.0

    def test_collect_stream_distribution_calculates_average_age(
        self, metrics_collector, mock_time_service
    ):
        """Test collect_stream_distribution calculates average age correctly."""
        # Setup: create consents with known ages
        now = mock_time_service.now()
        consent_cache = {
            "user_30d": ConsentStatus(
                user_id="user_30d",
                stream=ConsentStream.TEMPORARY,
                granted_at=now - timedelta(days=30),
                expires_at=now + timedelta(days=14),
                last_modified=now,
                categories=[],
                impact_score=0.0,
                attribution_count=0,
            ),
            "user_60d": ConsentStatus(
                user_id="user_60d",
                stream=ConsentStream.PARTNERED,
                granted_at=now - timedelta(days=60),
                expires_at=None,
                last_modified=now,
                categories=[],
                impact_score=0.0,
                attribution_count=0,
            ),
        }

        # Execute
        metrics = metrics_collector.collect_stream_distribution(consent_cache, now)

        # Assert: average should be (30 + 60) / 2 = 45 days
        assert abs(metrics["consent_average_age_days"] - 45.0) < 0.1

    def test_collect_partnership_metrics(self, metrics_collector, sample_partnership_counters):
        """Test collect_partnership_metrics with sample counters."""
        # Execute
        metrics = metrics_collector.collect_partnership_metrics(
            sample_partnership_counters.requests,
            sample_partnership_counters.approvals,
            sample_partnership_counters.rejections,
            sample_partnership_counters.pending_count,
        )

        # Assert
        assert metrics["consent_partnership_requests_total"] == 10.0
        assert metrics["consent_partnership_approvals_total"] == 7.0
        assert metrics["consent_partnership_rejections_total"] == 2.0
        assert metrics["consent_pending_partnerships"] == 1.0

        # Success rate: 7/10 = 70%
        assert abs(metrics["consent_partnership_success_rate"] - 70.0) < 0.1

    def test_collect_partnership_metrics_zero_requests(self, metrics_collector):
        """Test collect_partnership_metrics handles zero requests."""
        # Execute
        metrics = metrics_collector.collect_partnership_metrics(0, 0, 0, 0)

        # Assert
        assert metrics["consent_partnership_success_rate"] == 0.0
        assert metrics["consent_partnership_requests_total"] == 0.0

    def test_collect_decay_metrics(self, metrics_collector, sample_decay_counters):
        """Test collect_decay_metrics with sample counters."""
        # Execute
        metrics = metrics_collector.collect_decay_metrics(
            sample_decay_counters.total_initiated,
            sample_decay_counters.completed,
            sample_decay_counters.active_count,
        )

        # Assert
        assert metrics["consent_total_decays_initiated"] == 15.0
        assert metrics["consent_decays_completed_total"] == 12.0
        assert metrics["consent_active_decays"] == 3.0

        # Completion rate: 12/15 = 80%
        assert abs(metrics["consent_decay_completion_rate"] - 80.0) < 0.1

    def test_collect_decay_metrics_zero_decays(self, metrics_collector):
        """Test collect_decay_metrics handles zero decays."""
        # Execute
        metrics = metrics_collector.collect_decay_metrics(0, 0, 0)

        # Assert
        assert metrics["consent_decay_completion_rate"] == 0.0
        assert metrics["consent_total_decays_initiated"] == 0.0

    def test_collect_operational_metrics(self, metrics_collector, sample_operational_counters):
        """Test collect_operational_metrics with sample counters."""
        # Execute
        metrics = metrics_collector.collect_operational_metrics(
            sample_operational_counters.consent_checks,
            sample_operational_counters.consent_grants,
            sample_operational_counters.consent_revokes,
            sample_operational_counters.expired_cleanups,
            sample_operational_counters.tool_executions,
            sample_operational_counters.tool_failures,
        )

        # Assert
        assert metrics["consent_checks_total"] == 500.0
        assert metrics["consent_grants_total"] == 100.0
        assert metrics["consent_revokes_total"] == 25.0
        assert metrics["consent_expired_cleanups_total"] == 10.0
        assert metrics["consent_tool_executions_total"] == 200.0
        assert metrics["consent_tool_failures_total"] == 5.0

    def test_collect_all_metrics_integration(
        self,
        metrics_collector,
        mixed_consent_cache,
        mock_time_service,
        sample_partnership_counters,
        sample_decay_counters,
        sample_operational_counters,
    ):
        """Test collect_all_metrics integrates all metric types."""
        # Setup
        now = mock_time_service.now()

        # Execute
        metrics = metrics_collector.collect_all_metrics(
            mixed_consent_cache,
            now,
            sample_partnership_counters,
            sample_decay_counters,
            sample_operational_counters,
            uptime_calculator=None,
        )

        # Assert: verify all metric categories are present
        # Stream distribution metrics
        assert "consent_active_users" in metrics
        assert "consent_temporary_percent" in metrics

        # Partnership metrics
        assert "consent_partnership_success_rate" in metrics
        assert "consent_partnership_requests_total" in metrics

        # Decay metrics
        assert "consent_decay_completion_rate" in metrics
        assert "consent_active_decays" in metrics

        # Operational metrics
        assert "consent_checks_total" in metrics
        assert "consent_tool_executions_total" in metrics

        # Service health metric
        assert "consent_service_uptime_seconds" in metrics

    def test_collect_all_metrics_with_uptime_calculator(
        self,
        metrics_collector,
        mixed_consent_cache,
        mock_time_service,
        sample_partnership_counters,
        sample_decay_counters,
        sample_operational_counters,
    ):
        """Test collect_all_metrics includes uptime when calculator provided."""
        # Setup
        now = mock_time_service.now()
        uptime_calc = type("UptimeCalc", (), {"_calculate_uptime": lambda self: 3600.0})()

        # Execute
        metrics = metrics_collector.collect_all_metrics(
            mixed_consent_cache,
            now,
            sample_partnership_counters,
            sample_decay_counters,
            sample_operational_counters,
            uptime_calculator=uptime_calc,
        )

        # Assert
        assert metrics["consent_service_uptime_seconds"] == 3600.0

    def test_calculate_health_score_perfect_health(self, metrics_collector):
        """Test calculate_health_score with perfect metrics."""
        # Setup: perfect metrics
        metrics = {
            "consent_partnership_success_rate": 100.0,  # 30 points
            "consent_decay_completion_rate": 100.0,  # 30 points
            "consent_tool_executions_total": 100.0,
            "consent_tool_failures_total": 0.0,  # 20 points (100% success)
            "consent_active_users": 100.0,  # 20 points (100 users)
        }

        # Execute
        health_score = metrics_collector.calculate_health_score(metrics)

        # Assert: 30 + 30 + 20 + 20 = 100
        assert health_score == 100.0

    def test_calculate_health_score_partial_health(self, metrics_collector):
        """Test calculate_health_score with partial metrics."""
        # Setup
        metrics = {
            "consent_partnership_success_rate": 70.0,  # 21 points (70 * 0.3)
            "consent_decay_completion_rate": 80.0,  # 24 points (80 * 0.3)
            "consent_tool_executions_total": 100.0,
            "consent_tool_failures_total": 10.0,  # 18 points (90% success * 0.2)
            "consent_active_users": 50.0,  # 10 points (50 * 0.2)
        }

        # Execute
        health_score = metrics_collector.calculate_health_score(metrics)

        # Assert: 21 + 24 + 18 + 10 = 73
        assert abs(health_score - 73.0) < 1.0

    def test_calculate_health_score_zero_health(self, metrics_collector):
        """Test calculate_health_score with zero metrics."""
        # Setup
        metrics = {
            "consent_partnership_success_rate": 0.0,
            "consent_decay_completion_rate": 0.0,
            "consent_tool_executions_total": 0.0,
            "consent_tool_failures_total": 0.0,
            "consent_active_users": 0.0,
        }

        # Execute
        health_score = metrics_collector.calculate_health_score(metrics)

        # Assert: 0 + 0 + 20 (no failures = 100% success) + 0 = 20
        # (Tool health defaults to 100% when no executions)
        assert abs(health_score - 20.0) < 1.0

    def test_calculate_health_score_caps_at_100(self, metrics_collector):
        """Test calculate_health_score caps maximum at 100."""
        # Setup: impossibly high metrics
        metrics = {
            "consent_partnership_success_rate": 200.0,
            "consent_decay_completion_rate": 200.0,
            "consent_tool_executions_total": 100.0,
            "consent_tool_failures_total": 0.0,
            "consent_active_users": 200.0,
        }

        # Execute
        health_score = metrics_collector.calculate_health_score(metrics)

        # Assert: should be capped at 100
        assert health_score == 100.0

    def test_calculate_health_score_user_health_capped_at_100_users(self, metrics_collector):
        """Test calculate_health_score caps user health at 100 users."""
        # Setup
        metrics = {
            "consent_partnership_success_rate": 0.0,
            "consent_decay_completion_rate": 0.0,
            "consent_tool_executions_total": 0.0,
            "consent_tool_failures_total": 0.0,
            "consent_active_users": 500.0,  # More than 100
        }

        # Execute
        health_score = metrics_collector.calculate_health_score(metrics)

        # Assert: user health should be capped at 20 points (100 users * 0.2)
        # Total: 0 + 0 + 20 (tool default) + 20 (user cap) = 40
        assert abs(health_score - 40.0) < 1.0

    def test_schema_based_parameter_reduction(
        self,
        metrics_collector,
        comprehensive_counters,
        mixed_consent_cache,
        mock_time_service,
    ):
        """Test that new schema-based approach reduces parameter count."""
        # This test verifies the architectural improvement:
        # Instead of 16 parameters, we now have 6 (cache, now, 3 counter objects, uptime)

        # Execute: using schema objects
        metrics = metrics_collector.collect_all_metrics(
            consent_cache=mixed_consent_cache,
            now=mock_time_service.now(),
            partnership_counters=comprehensive_counters["partnership"],
            decay_counters=comprehensive_counters["decay"],
            operational_counters=comprehensive_counters["operational"],
            uptime_calculator=None,
        )

        # Assert: verify all metrics are collected correctly
        assert len(metrics) > 15  # Should have many metrics
        assert metrics["consent_partnership_requests_total"] == 10.0
        assert metrics["consent_total_decays_initiated"] == 15.0
        assert metrics["consent_checks_total"] == 500.0
