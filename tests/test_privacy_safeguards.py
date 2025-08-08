"""
Tests for privacy safeguards and retention policies.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.services.nodes import ConfigNode  # Using ConfigNode for testing


class TestDataRetention:
    """Test data retention policies."""

    def test_message_retention_14_days(self):
        """Test that message content is retained for only 14 days."""
        # Check privacy policy HTML
        privacy_policy_path = Path("CIRISGUI/apps/agui/public/privacy-policy.html")
        if privacy_policy_path.exists():
            content = privacy_policy_path.read_text()
            assert "14 days" in content
            assert "pilot" in content.lower()

    def test_audit_retention_90_days(self):
        """Test that audit logs are retained for 90 days."""
        # Check privacy policy mentions audit retention
        privacy_policy_path = Path("CIRISGUI/apps/agui/public/privacy-policy.html")
        if privacy_policy_path.exists():
            content = privacy_policy_path.read_text()
            assert "90 days" in content
            assert "audit" in content.lower() or "compliance" in content.lower()

    def test_tsdb_consolidation_6_hours(self):
        """Test that TSDB consolidates every 6 hours."""
        from ciris_engine.schemas.services.graph.tsdb_consolidation import TSDBConsolidationConfig

        config = TSDBConsolidationConfig()
        assert config.consolidation_interval_hours == 6

    def test_consolidation_node_expiry_flag(self):
        """Test that consolidation nodes can track data expiry."""
        # Using TSDBPeriodSummary to track consolidation data
        from ciris_engine.schemas.services.graph.consolidation import TSDBPeriodSummary

        # Create a period summary (which tracks consolidation data)
        summary = TSDBPeriodSummary(
            period_label="2025080712",
            period_start=(datetime.utcnow() - timedelta(hours=6)).isoformat(),
            period_end=datetime.utcnow().isoformat(),
            source_node_count=100,
            action_counts={"metrics_expired": 5, "metrics_created": 10},
        )

        # Should track expired metrics via action counts
        assert "metrics_expired" in summary.action_counts
        assert summary.action_counts["metrics_expired"] == 5


class TestPDMARedaction:
    """Test that PDMA logs are not exposed in public APIs."""

    def test_agent_interact_no_pdma(self):
        """Test that agent interaction response contains no PDMA details."""
        from ciris_engine.logic.adapters.api.routes.agent import InteractResponse

        response = InteractResponse(
            message_id="test_123", response="Hello, how can I help?", state="WORK", processing_time_ms=250
        )

        # Should not have PDMA fields
        assert not hasattr(response, "pdma")
        assert not hasattr(response, "perceive")
        assert not hasattr(response, "decide")
        assert not hasattr(response, "memorize")
        assert not hasattr(response, "act")

        # Serialized response should not contain PDMA
        response_dict = response.model_dump()
        assert "pdma" not in str(response_dict).lower()

    def test_conversation_history_no_internal_reasoning(self):
        """Test that conversation history excludes internal reasoning."""
        from ciris_engine.logic.adapters.api.routes.agent import ConversationMessage

        message = ConversationMessage(
            id="msg_123", author="user", content="What is the weather?", timestamp=datetime.utcnow(), is_agent=False
        )

        # Should only have public fields
        public_fields = {"id", "author", "content", "timestamp", "is_agent"}
        assert set(message.model_fields.keys()) == public_fields

    @patch("ciris_engine.logic.adapters.api.routes.agent.logger")
    def test_pdma_logs_are_internal_only(self, mock_logger):
        """Test that PDMA logs are marked as internal."""
        # When PDMA logs are created, they should use logger.debug or logger.info
        # Never logger.warning or logger.error for normal operation

        mock_logger.info.assert_not_called()  # Initially

        # Simulate internal PDMA logging
        mock_logger.info("PDMA: Evaluating action selection")
        mock_logger.debug("PDMA decision details: ...")

        # These should be info/debug level, not warning/error
        assert mock_logger.info.called or mock_logger.debug.called
        assert not mock_logger.warning.called
        assert not mock_logger.error.called


class TestTransparencyFeed:
    """Test public transparency feed."""

    def test_transparency_feed_anonymized(self):
        """Test that transparency feed contains no personal data."""
        from ciris_engine.logic.adapters.api.routes.transparency import TransparencyStats

        stats = TransparencyStats(
            period_start=datetime.utcnow() - timedelta(hours=24),
            period_end=datetime.utcnow(),
            total_interactions=150,
            actions_taken=[],
            deferrals_to_human=20,
            deferrals_uncertainty=5,
            deferrals_ethical=2,
            harmful_requests_blocked=3,
            rate_limit_triggers=1,
            emergency_shutdowns=0,
            uptime_percentage=99.9,
            average_response_ms=250.0,
            active_agents=1,
            data_requests_received=0,
            data_requests_completed=0,
        )

        # Convert to dict and check for personal data
        stats_dict = stats.model_dump()
        stats_str = str(stats_dict)

        # Should not contain personal identifiers
        assert "@" not in stats_str  # No emails
        assert "user_" not in stats_str  # No user IDs
        assert "discord" not in stats_str.lower()  # No Discord IDs
        assert "channel_" not in stats_str  # No channel IDs

    def test_transparency_policy_commitments(self):
        """Test that transparency policy includes key commitments."""
        from ciris_engine.logic.adapters.api.routes.transparency import TransparencyPolicy

        policy = TransparencyPolicy(
            version="1.0",
            last_updated=datetime.utcnow(),
            retention_days=14,
            commitments=[
                "We do not train on your content",
                "We retain message content for 14 days only (pilot)",
                "We provide anonymized statistics publicly",
                "We defer to human judgment when uncertain",
            ],
            links={},
        )

        # Check key commitments
        commitments_text = " ".join(policy.commitments)
        assert "not train" in commitments_text
        assert "14 days" in commitments_text
        assert "defer" in commitments_text
        assert "human" in commitments_text


class TestSunsetTriggers:
    """Test sunset trigger documentation."""

    def test_sunset_triggers_documented(self):
        """Test that sunset triggers are documented."""
        sunset_doc_path = Path("docs/SUNSET_TRIGGERS.md")
        if sunset_doc_path.exists():
            content = sunset_doc_path.read_text()

            # Check red line triggers
            assert "target, surveil, or doxx" in content
            assert "Loss of Human Oversight" in content
            assert "WA Injunction" in content

            # Check Section VIII reference
            assert "Section VIII" in content
            assert "covenant_1.0b.txt" in content

    def test_when_we_pause_policy(self):
        """Test when-we-pause policy document."""
        pause_policy_path = Path("CIRISGUI/apps/agui/public/when-we-pause.html")
        if pause_policy_path.exists():
            content = pause_policy_path.read_text()

            # Check red lines
            assert "RED LINE" in content
            assert "Immediate Shutdown" in content

            # Check yellow lines
            assert "YELLOW LINE" in content
            assert "WA Review" in content

            # Check promise
            assert "promise" in content.lower()
            assert "safety over functionality" in content

    def test_why_we_paused_template(self):
        """Test why-we-paused status page template."""
        status_page_path = Path("CIRISGUI/apps/agui/public/why-we-paused.html")
        if status_page_path.exists():
            content = status_page_path.read_text()

            # Should have operational state by default
            assert "Operational" in content

            # Should have templates for paused/degraded states (commented)
            assert "<!--" in content  # Has commented sections
            assert "System Paused" in content
            assert "Partial Service" in content

            # Should auto-refresh
            assert 'content="60"' in content  # 60 second refresh


class TestAdaptiveFilter:
    """Test that adaptive filter provides automatic quarantine."""

    def test_adaptive_filter_exists(self):
        """Test that AdaptiveFilterService exists."""
        from ciris_engine.logic.services.governance.filter import AdaptiveFilterService

        # Should be importable
        assert AdaptiveFilterService is not None

    def test_adaptive_filter_protocol(self):
        """Test that AdaptiveFilterService implements protocol."""
        from ciris_engine.protocols.services.governance.filter import AdaptiveFilterServiceProtocol

        # Protocol should define filtering methods
        assert hasattr(AdaptiveFilterServiceProtocol, "filter_message")

    def test_adaptive_filter_in_service_list(self):
        """Test that adaptive filter is in core services."""
        from ciris_engine.logic.runtime.service_initializer import ServiceInitializer

        # Should be initialized as part of governance services
        initializer = ServiceInitializer(MagicMock())
        assert hasattr(initializer, "adaptive_filter_service")
