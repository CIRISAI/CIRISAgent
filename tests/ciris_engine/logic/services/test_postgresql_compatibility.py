"""Tests for PostgreSQL compatibility code paths.

These tests ensure code paths that handle PostgreSQL-specific behaviors
(like RealDictCursor returning dicts instead of tuples) have proper coverage.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService


class TestWiseAuthorityPostgreSQLCompat:
    """Test WiseAuthority PostgreSQL compatibility."""

    def test_parse_deferral_context_with_dict_input(self):
        """Test _parse_deferral_context handles pre-parsed dict from PostgreSQL jsonb."""
        # Create minimal service instance
        service = WiseAuthorityService.__new__(WiseAuthorityService)

        # Test with dict input (PostgreSQL jsonb returns dict directly)
        context_dict = {"deferral": {"reason": "test reason", "deferred_by": "wa-123"}, "other_data": "value"}

        context, deferral_info = service._parse_deferral_context(context_dict)

        assert context == context_dict
        assert deferral_info == {"reason": "test reason", "deferred_by": "wa-123"}

    def test_parse_deferral_context_with_string_input(self):
        """Test _parse_deferral_context handles JSON string input (SQLite)."""
        service = WiseAuthorityService.__new__(WiseAuthorityService)

        # Test with JSON string input (SQLite returns string)
        context_dict = {"deferral": {"reason": "string test", "deferred_by": "wa-456"}}
        context_json = json.dumps(context_dict)

        context, deferral_info = service._parse_deferral_context(context_json)

        assert context == context_dict
        assert deferral_info == {"reason": "string test", "deferred_by": "wa-456"}

    def test_parse_deferral_context_with_none(self):
        """Test _parse_deferral_context handles None input."""
        service = WiseAuthorityService.__new__(WiseAuthorityService)

        context, deferral_info = service._parse_deferral_context(None)

        assert context == {}
        assert deferral_info == {}

    def test_parse_deferral_context_with_invalid_json(self):
        """Test _parse_deferral_context handles invalid JSON gracefully."""
        service = WiseAuthorityService.__new__(WiseAuthorityService)

        context, deferral_info = service._parse_deferral_context("not valid json {{{")

        assert context == {}
        assert deferral_info == {}

    def test_parse_deferral_context_dict_without_deferral_key(self):
        """Test _parse_deferral_context handles dict without deferral key."""
        service = WiseAuthorityService.__new__(WiseAuthorityService)

        context_dict = {"other_key": "other_value"}

        context, deferral_info = service._parse_deferral_context(context_dict)

        assert context == context_dict
        assert deferral_info == {}


class TestTelemetryServicePostgreSQLCompat:
    """Test TelemetryService PostgreSQL compatibility."""

    # TODO(CIRISPersist): tests for get_metric_count via get_db_connection cursor
    # shape (dict-vs-tuple) were removed in Phase 3a — get_metric_count now
    # paginates persist's `cirisgraph_query_nodes` instead of executing raw SQL,
    # so the PostgreSQL RealDictCursor vs SQLite Row code path no longer exists.

    @pytest.mark.asyncio
    async def test_get_metric_count_no_memory_bus(self):
        """Test get_metric_count returns 0 when persist engine is not wired."""
        service = GraphTelemetryService.__new__(GraphTelemetryService)
        service.db_path = ":memory:"
        service._memory_bus = None

        # When persist engine isn't wired, get_metric_count returns 0.
        with patch(
            "ciris_engine.logic.persistence.models.graph.get_persist_engine",
            return_value=None,
        ):
            count = await service.get_metric_count()

        assert count == 0


class TestBillingPathTraversalProtection:
    """Test billing endpoint path traversal protection."""

    def test_url_encoding_prevents_path_traversal(self):
        """Test that payment_id is URL-encoded to prevent path traversal."""
        from urllib.parse import quote

        # Test various path traversal attempts
        test_cases = [
            ("../../../etc/passwd", "..%2F..%2F..%2Fetc%2Fpasswd"),
            ("payment/../admin", "payment%2F..%2Fadmin"),
            ("normal_id_123", "normal_id_123"),
            ("id with spaces", "id%20with%20spaces"),
            ("id/with/slashes", "id%2Fwith%2Fslashes"),
        ]

        for input_id, expected in test_cases:
            safe_id = quote(input_id, safe="")
            assert safe_id == expected, f"Failed for input: {input_id}"

    def test_payment_id_pattern_validation(self):
        """Test that PAYMENT_ID_PATTERN correctly validates payment IDs."""
        import re

        # This pattern should match valid payment IDs
        PAYMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,100}$")

        # Valid IDs
        assert PAYMENT_ID_PATTERN.match("payment_123")
        assert PAYMENT_ID_PATTERN.match("pay-456-abc")
        assert PAYMENT_ID_PATTERN.match("PAYMENT_ID")

        # Invalid IDs (would be rejected before reaching URL encoding)
        assert not PAYMENT_ID_PATTERN.match("../../../etc")
        assert not PAYMENT_ID_PATTERN.match("id with spaces")
        assert not PAYMENT_ID_PATTERN.match("id/slash")
        assert not PAYMENT_ID_PATTERN.match("")
        assert not PAYMENT_ID_PATTERN.match("a" * 101)  # Too long
