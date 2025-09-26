"""
Tests for Discord error classification utility.
"""

import pytest

from ciris_engine.logic.adapters.discord.discord_error_classifier import (
    DiscordErrorClassifier,
    ErrorCategory,
    ErrorClassification,
)


class TestDiscordErrorClassifier:
    """Test Discord error classification and retry logic."""

    def test_network_error_classification(self):
        """Test network error classification."""
        network_error = ConnectionResetError("Connection reset by peer")

        classification = DiscordErrorClassifier.classify_error(network_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.NETWORK
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.retry_delay == 5.0  # 5.0 * (2 ** max(0, 0 - 1)) = 5.0 * 0.5 = 2.5, capped to 5.0
        assert classification.max_retries == 10

    def test_network_error_exponential_backoff(self):
        """Test exponential backoff for network errors."""
        network_error = ConnectionResetError("Connection reset by peer")

        # Test progression of retry delays
        delays = []
        for attempt in range(5):
            classification = DiscordErrorClassifier.classify_error(network_error, reconnect_attempts=attempt)
            delays.append(classification.retry_delay)

        # Should be: 5.0, 5.0, 10.0, 20.0, 40.0 (using 5.0 * (2 ** max(0, attempt - 1)) formula)
        expected = [5.0, 5.0, 10.0, 20.0, 40.0]
        assert delays == expected

    def test_network_error_max_delay_cap(self):
        """Test that network error delays are capped at 60 seconds."""
        network_error = ConnectionResetError("Connection reset by peer")

        classification = DiscordErrorClassifier.classify_error(network_error, reconnect_attempts=10)

        assert classification.retry_delay == 60.0  # Capped at max
        assert classification.should_retry is False  # Exceeded max retries

    def test_websocket_error_classification(self):
        """Test WebSocket error classification."""
        ws_error = Exception("WebSocket connection is closed.")

        classification = DiscordErrorClassifier.classify_error(ws_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.WEBSOCKET
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.max_retries == 15

    def test_server_error_classification(self):
        """Test server error classification."""
        server_error = Exception("HTTP 502 Bad Gateway")

        classification = DiscordErrorClassifier.classify_error(server_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.SERVER
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.retry_delay == 3.0  # 3.0 * (0 + 1)

    def test_rate_limit_error_classification(self):
        """Test rate limit error classification."""
        rate_limit_error = Exception("Rate limit exceeded")

        classification = DiscordErrorClassifier.classify_error(rate_limit_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.RATE_LIMIT
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.retry_delay == 60.0  # Base delay for rate limits

    def test_rate_limit_progressive_delays(self):
        """Test progressive delays for rate limit errors."""
        rate_limit_error = Exception("429 Too Many Requests")

        delays = []
        for attempt in range(3):
            classification = DiscordErrorClassifier.classify_error(rate_limit_error, reconnect_attempts=attempt)
            delays.append(classification.retry_delay)

        # Should be: 60, 90, 120 (60 + attempt * 30)
        expected = [60.0, 90.0, 120.0]
        assert delays == expected

    def test_ssl_error_classification(self):
        """Test SSL/TLS error classification."""
        ssl_error = Exception("SSL certificate verification failed")

        classification = DiscordErrorClassifier.classify_error(ssl_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.SSL_TLS
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.max_retries == 3

    def test_auth_error_no_retry(self):
        """Test authentication errors are not retried."""
        auth_error = Exception("401 Unauthorized")

        classification = DiscordErrorClassifier.classify_error(auth_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.AUTHENTICATION
        assert classification.is_transient is False
        assert classification.should_retry is False
        assert classification.retry_delay == 0.0
        assert classification.max_retries == 0

    def test_permission_error_no_retry(self):
        """Test permission errors are not retried."""
        perm_error = Exception("Missing Permissions")

        classification = DiscordErrorClassifier.classify_error(perm_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.PERMISSION
        assert classification.is_transient is False
        assert classification.should_retry is False

    def test_unknown_error_cautious_retry(self):
        """Test unknown errors get cautious retry strategy."""
        unknown_error = Exception("Some unknown error")

        classification = DiscordErrorClassifier.classify_error(unknown_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.UNKNOWN
        assert classification.is_transient is True
        assert classification.should_retry is True
        assert classification.max_retries == 3
        assert classification.retry_delay == 10.0

    def test_unknown_error_max_retries(self):
        """Test unknown errors stop retrying after max attempts."""
        unknown_error = Exception("Some unknown error")

        classification = DiscordErrorClassifier.classify_error(unknown_error, reconnect_attempts=3)

        assert classification.should_retry is False

    def test_case_insensitive_matching(self):
        """Test error matching is case insensitive."""
        lower_error = Exception("connection reset by peer")
        upper_error = Exception("CONNECTION RESET BY PEER")
        mixed_error = Exception("Connection Reset By Peer")

        for error in [lower_error, upper_error, mixed_error]:
            classification = DiscordErrorClassifier.classify_error(error, reconnect_attempts=0)
            assert classification.category == ErrorCategory.NETWORK

    def test_partial_string_matching(self):
        """Test partial string matching works."""
        full_error = Exception("The Connection reset by peer unexpectedly")

        classification = DiscordErrorClassifier.classify_error(full_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.NETWORK

    def test_cloudflare_variations(self):
        """Test both CloudFlare and Cloudflare spelling variations."""
        cf_error1 = Exception("CloudFlare error occurred")
        cf_error2 = Exception("Cloudflare protection triggered")

        for error in [cf_error1, cf_error2]:
            classification = DiscordErrorClassifier.classify_error(error, reconnect_attempts=0)
            assert classification.category == ErrorCategory.SERVER

    def test_rate_limit_variations(self):
        """Test various rate limit error formats."""
        rate_errors = [
            Exception("Rate limit exceeded"),
            Exception("rate limit reached"),
            Exception("HTTP 429 Too Many Requests"),
            Exception("Error 429: Rate limited"),
        ]

        for error in rate_errors:
            classification = DiscordErrorClassifier.classify_error(error, reconnect_attempts=0)
            assert classification.category == ErrorCategory.RATE_LIMIT

    def test_websocket_concurrent_call_error(self):
        """Test specific WebSocket concurrent call error."""
        ws_error = Exception("Concurrent call to receive() is not allowed")

        classification = DiscordErrorClassifier.classify_error(ws_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.WEBSOCKET
        assert classification.should_retry is True

    def test_shard_error_classification(self):
        """Test Discord shard-specific error."""
        shard_error = Exception("Shard ID None has stopped responding to the gateway.")

        classification = DiscordErrorClassifier.classify_error(shard_error, reconnect_attempts=0)

        assert classification.category == ErrorCategory.WEBSOCKET
        assert classification.should_retry is True

    def test_error_classification_logging(self, caplog):
        """Test error classification logging."""
        import logging

        network_error = Exception("Connection reset by peer")
        classification = DiscordErrorClassifier.classify_error(network_error, reconnect_attempts=0)

        with caplog.at_level(logging.WARNING):
            DiscordErrorClassifier.log_error_classification(classification, attempt=1)

        assert "Discord network error" in caplog.text
        assert "attempt 1/10" in caplog.text
        assert "Retrying in 5.0s" in caplog.text

    def test_non_recoverable_error_logging(self, caplog):
        """Test non-recoverable error logging."""
        import logging

        auth_error = Exception("401 Unauthorized")
        classification = DiscordErrorClassifier.classify_error(auth_error, reconnect_attempts=0)

        with caplog.at_level(logging.ERROR):
            DiscordErrorClassifier.log_error_classification(classification, attempt=1)

        assert "Discord authentication error" in caplog.text
        assert "non-recoverable" in caplog.text

    def test_matches_any_helper_method(self):
        """Test the _matches_any helper method."""
        test_patterns = {"test", "example", "pattern"}

        # Should match
        assert DiscordErrorClassifier._matches_any("This is a test message", test_patterns)
        assert DiscordErrorClassifier._matches_any("An example error", test_patterns)
        assert DiscordErrorClassifier._matches_any("Pattern found here", test_patterns)

        # Should not match
        assert not DiscordErrorClassifier._matches_any("No matches here", test_patterns)
        assert not DiscordErrorClassifier._matches_any("Different message", test_patterns)

    def test_error_description_format(self):
        """Test error description formatting."""
        test_error = Exception("Test error message")
        classification = DiscordErrorClassifier.classify_error(test_error, reconnect_attempts=0)

        assert "Test error message" in classification.description
        assert classification.description.startswith("Unknown error")