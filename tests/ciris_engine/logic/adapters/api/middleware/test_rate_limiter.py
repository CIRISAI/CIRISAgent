"""
Comprehensive tests for API rate limiter middleware.

Tests token bucket algorithm, client identification, rate limit enforcement,
and all edge cases.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ciris_engine.logic.adapters.api.middleware.rate_limiter import RateLimiter, RateLimitMiddleware

# =============================================================================
# RateLimiter Tests (Token Bucket Algorithm)
# =============================================================================


class TestRateLimiterInitialization:
    """Test rate limiter initialization."""

    def test_default_initialization(self):
        """Test rate limiter initializes with default values."""
        limiter = RateLimiter()
        assert limiter.rate == 60
        assert limiter.buckets == {}
        assert limiter._cleanup_interval == 300
        assert isinstance(limiter._last_cleanup, datetime)

    def test_custom_rate_initialization(self):
        """Test rate limiter with custom rate."""
        limiter = RateLimiter(requests_per_minute=100)
        assert limiter.rate == 100
        assert limiter.buckets == {}


class TestRateLimiterTokenBucket:
    """Test token bucket algorithm implementation."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        """Test first request from new client is always allowed."""
        limiter = RateLimiter(requests_per_minute=60)
        allowed = await limiter.check_rate_limit("client1")
        assert allowed is True
        assert "client1" in limiter.buckets

    @pytest.mark.asyncio
    async def test_bucket_created_with_full_tokens(self):
        """Test new client bucket starts with full tokens."""
        limiter = RateLimiter(requests_per_minute=60)
        await limiter.check_rate_limit("client1")
        tokens, _ = limiter.buckets["client1"]
        # After consuming 1 token for the request
        assert tokens == 59.0

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self):
        """Test tokens refill at correct rate."""
        limiter = RateLimiter(requests_per_minute=60)

        # Make first request
        await limiter.check_rate_limit("client1")

        # Manually set last_update to 1 second ago
        tokens, _ = limiter.buckets["client1"]
        limiter.buckets["client1"] = (tokens, datetime.now() - timedelta(seconds=1))

        # Check rate limit again - should have refilled 1 token (60 tokens/60 seconds = 1 token/sec)
        await limiter.check_rate_limit("client1")
        tokens, _ = limiter.buckets["client1"]
        # Started with 59, gained 1, consumed 1 = 59
        assert tokens == pytest.approx(59.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_rate_limiting_blocks_after_depletion(self):
        """Test rate limiting blocks requests when tokens depleted."""
        limiter = RateLimiter(requests_per_minute=2)

        # Make 2 requests (deplete tokens)
        assert await limiter.check_rate_limit("client1") is True
        assert await limiter.check_rate_limit("client1") is True

        # Third request should be blocked
        assert await limiter.check_rate_limit("client1") is False

    @pytest.mark.asyncio
    async def test_tokens_cap_at_max_rate(self):
        """Test tokens don't exceed max rate."""
        limiter = RateLimiter(requests_per_minute=60)

        # Create bucket
        await limiter.check_rate_limit("client1")

        # Set last_update to far in the past (should refill to max, not beyond)
        limiter.buckets["client1"] = (0.0, datetime.now() - timedelta(hours=1))

        # Check rate - should refill to max (60), then consume 1
        await limiter.check_rate_limit("client1")
        tokens, _ = limiter.buckets["client1"]
        assert tokens == 59.0  # Capped at rate, minus 1 consumed

    @pytest.mark.asyncio
    async def test_concurrent_requests_thread_safe(self):
        """Test concurrent requests don't cause race conditions."""
        limiter = RateLimiter(requests_per_minute=10)

        # Make 10 concurrent requests
        tasks = [limiter.check_rate_limit("client1") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed (have enough tokens)
        assert all(results)

        # Next request should fail (tokens depleted)
        assert await limiter.check_rate_limit("client1") is False


class TestRateLimiterCleanup:
    """Test bucket cleanup mechanism."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_entries(self):
        """Test cleanup removes entries older than 1 hour."""
        limiter = RateLimiter(requests_per_minute=60)

        # Create some buckets
        await limiter.check_rate_limit("old_client")
        await limiter.check_rate_limit("new_client")

        # Make old_client's bucket old (>1 hour)
        limiter.buckets["old_client"] = (50.0, datetime.now() - timedelta(hours=2))

        # Trigger cleanup
        limiter._cleanup_old_entries()

        # Old client should be removed, new client retained
        assert "old_client" not in limiter.buckets
        assert "new_client" in limiter.buckets

    @pytest.mark.asyncio
    async def test_cleanup_triggered_periodically(self):
        """Test cleanup runs every 5 minutes during requests."""
        limiter = RateLimiter(requests_per_minute=60)

        # Set last cleanup to 6 minutes ago
        limiter._last_cleanup = datetime.now() - timedelta(minutes=6)

        # Add old bucket
        limiter.buckets["old_client"] = (50.0, datetime.now() - timedelta(hours=2))

        # Make request - should trigger cleanup
        await limiter.check_rate_limit("new_client")

        # Old bucket should be cleaned
        assert "old_client" not in limiter.buckets

    @pytest.mark.asyncio
    async def test_cleanup_preserves_recent_entries(self):
        """Test cleanup doesn't remove recent entries."""
        limiter = RateLimiter(requests_per_minute=60)

        # Create recent buckets
        await limiter.check_rate_limit("client1")
        await limiter.check_rate_limit("client2")

        # Run cleanup
        limiter._cleanup_old_entries()

        # Both should remain
        assert "client1" in limiter.buckets
        assert "client2" in limiter.buckets


class TestRateLimiterMaxClients:
    """Test max client limit enforcement."""

    @pytest.mark.asyncio
    async def test_max_clients_enforced(self):
        """Test max client limit prevents memory exhaustion."""
        limiter = RateLimiter(requests_per_minute=60, max_clients=5)

        # Add 5 clients (at limit)
        for i in range(5):
            await limiter.check_rate_limit(f"client{i}")

        assert len(limiter.buckets) == 5

        # Add 6th client - should evict oldest
        await limiter.check_rate_limit("client5")

        # Still at max limit
        assert len(limiter.buckets) == 5

        # Oldest client (client0) should be evicted
        assert "client0" not in limiter.buckets
        assert "client5" in limiter.buckets

    @pytest.mark.asyncio
    async def test_lru_eviction_order(self):
        """Test LRU-like eviction removes least recently updated client."""
        limiter = RateLimiter(requests_per_minute=60, max_clients=3)

        # Add 3 clients
        await limiter.check_rate_limit("client0")
        await limiter.check_rate_limit("client1")
        await limiter.check_rate_limit("client2")

        # Update client0's timestamp
        await limiter.check_rate_limit("client0")

        # Add 4th client - should evict client1 (oldest)
        await limiter.check_rate_limit("client3")

        assert "client1" not in limiter.buckets
        assert "client0" in limiter.buckets
        assert "client2" in limiter.buckets
        assert "client3" in limiter.buckets


class TestRateLimiterRetryAfter:
    """Test retry-after calculation."""

    @pytest.mark.asyncio
    async def test_retry_after_for_depleted_bucket(self):
        """Test retry-after calculation when tokens depleted."""
        limiter = RateLimiter(requests_per_minute=60)

        # Deplete tokens
        for _ in range(60):
            await limiter.check_rate_limit("client1")

        # Get retry-after
        retry_after = limiter.get_retry_after("client1")

        # Should be ~1 second (60 requests/min = 1 token/sec)
        assert retry_after == 1

    @pytest.mark.asyncio
    async def test_retry_after_zero_for_available_tokens(self):
        """Test retry-after is 0 when tokens available."""
        limiter = RateLimiter(requests_per_minute=60)

        # Make one request
        await limiter.check_rate_limit("client1")

        # Should have tokens remaining
        retry_after = limiter.get_retry_after("client1")
        assert retry_after == 0

    def test_retry_after_zero_for_unknown_client(self):
        """Test retry-after is 0 for unknown client."""
        limiter = RateLimiter(requests_per_minute=60)
        retry_after = limiter.get_retry_after("unknown_client")
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_retry_after_calculation_accuracy(self):
        """Test retry-after calculation is accurate."""
        limiter = RateLimiter(requests_per_minute=120)  # 2 tokens/sec

        # Deplete all tokens
        for _ in range(120):
            await limiter.check_rate_limit("client1")

        # Need 1 token, at 2 tokens/sec = 0.5 seconds
        retry_after = limiter.get_retry_after("client1")
        assert retry_after == 1  # Rounds up to 1


# =============================================================================
# RateLimitMiddleware Tests (FastAPI Integration)
# =============================================================================


class TestRateLimitMiddlewareInitialization:
    """Test middleware initialization."""

    def test_default_middleware_initialization(self):
        """Test middleware initializes with defaults."""
        middleware = RateLimitMiddleware()
        assert middleware.limiter.rate == 60
        assert len(middleware.exempt_paths) == 5

    def test_custom_rate_middleware_initialization(self):
        """Test middleware with custom rate."""
        middleware = RateLimitMiddleware(requests_per_minute=100)
        assert middleware.limiter.rate == 100

    def test_exempt_paths_defined(self):
        """Test critical paths are exempt from rate limiting."""
        middleware = RateLimitMiddleware()
        assert "/openapi.json" in middleware.exempt_paths
        assert "/docs" in middleware.exempt_paths
        assert "/redoc" in middleware.exempt_paths
        assert "/emergency/shutdown" in middleware.exempt_paths
        assert "/v1/system/health" in middleware.exempt_paths


class TestRateLimitMiddlewareExemptPaths:
    """Test exempt path handling."""

    @pytest.mark.asyncio
    async def test_exempt_path_bypasses_rate_limiting(self):
        """Test exempt paths bypass rate limiting."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        # Mock request to exempt path
        request = Mock(spec=Request)
        request.url.path = "/docs"
        request.client = None
        request.headers = {}

        # Mock call_next
        expected_response = Response(content="OK", status_code=200)
        call_next = AsyncMock(return_value=expected_response)

        # Should pass through without rate limiting
        response = await middleware(request, call_next)
        assert response == expected_response
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_endpoint_exempt(self):
        """Test health endpoint is exempt."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        request = Mock(spec=Request)
        request.url.path = "/v1/system/health"
        request.client = None
        request.headers = {}

        expected_response = Response(content="OK", status_code=200)
        call_next = AsyncMock(return_value=expected_response)

        # Make multiple requests - all should succeed
        for _ in range(5):
            response = await middleware(request, call_next)
            assert response.status_code == 200


class TestRateLimitMiddlewareClientIdentification:
    """Test client identification logic."""

    @pytest.mark.asyncio
    async def test_ip_based_identification(self):
        """Test client identified by IP address."""
        middleware = RateLimitMiddleware()

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        await middleware(request, call_next)

        # Should create bucket with IP prefix
        assert "ip_192.168.1.100" in middleware.limiter.buckets

    @pytest.mark.asyncio
    async def test_auth_based_identification(self):
        """Test authenticated client identified differently."""
        middleware = RateLimitMiddleware()

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers.get = Mock(return_value="Bearer eyJhbGciOiJIUzI1NiIs...")

        call_next = AsyncMock(return_value=Response(content="OK"))

        await middleware(request, call_next)

        # Should create bucket with auth prefix
        assert "auth_192.168.1.100" in middleware.limiter.buckets

    @pytest.mark.asyncio
    async def test_service_token_identification(self):
        """Test service tokens get service_ prefix."""
        middleware = RateLimitMiddleware()

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers.get = Mock(return_value="Bearer service:abc123")

        call_next = AsyncMock(return_value=Response(content="OK"))

        await middleware(request, call_next)

        # Should use service-based identification
        assert "service_192.168.1.100" in middleware.limiter.buckets

    @pytest.mark.asyncio
    async def test_unknown_client_fallback(self):
        """Test unknown client uses 'unknown' identifier."""
        middleware = RateLimitMiddleware()

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client = None  # No client info
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        await middleware(request, call_next)

        # Should use 'unknown' fallback
        assert "ip_unknown" in middleware.limiter.buckets


class TestRateLimitMiddlewareJWTExtraction:
    """Test JWT user ID extraction for per-user rate limiting."""

    def test_extract_user_id_from_valid_jwt(self):
        """Test extracting user ID from valid JWT."""
        import jwt

        secret = b"test_secret"
        middleware = RateLimitMiddleware(gateway_secret=secret)

        # Create a valid JWT with sub claim
        payload = {"sub": "wa-2025-01-01-ABC123", "name": "Test User", "exp": 9999999999}
        token = jwt.encode(payload, secret, algorithm="HS256")

        # Create mock request
        request = Mock(spec=Request)
        request.app.state = Mock()

        # Extract user ID
        user_id = middleware._extract_user_id_from_jwt(token, request)
        assert user_id == "wa-2025-01-01-ABC123"

    def test_extract_user_id_from_jwt_without_sub(self):
        """Test extracting user ID from JWT without sub claim."""
        import jwt

        secret = b"test_secret"
        middleware = RateLimitMiddleware(gateway_secret=secret)

        # Create JWT without sub claim
        payload = {"name": "Test User", "exp": 9999999999}
        token = jwt.encode(payload, secret, algorithm="HS256")

        # Create mock request
        request = Mock(spec=Request)
        request.app.state = Mock()

        # Extract should return None
        user_id = middleware._extract_user_id_from_jwt(token, request)
        assert user_id is None

    def test_extract_user_id_from_invalid_jwt(self):
        """Test extracting user ID from malformed JWT."""
        secret = b"test_secret"
        middleware = RateLimitMiddleware(gateway_secret=secret)

        # Create mock request
        request = Mock(spec=Request)
        request.app.state = Mock()

        # Invalid JWT
        user_id = middleware._extract_user_id_from_jwt("not-a-valid-jwt", request)
        assert user_id is None

    def test_extract_user_id_from_empty_token(self):
        """Test extracting user ID from empty token."""
        secret = b"test_secret"
        middleware = RateLimitMiddleware(gateway_secret=secret)

        # Create mock request
        request = Mock(spec=Request)
        request.app.state = Mock()

        user_id = middleware._extract_user_id_from_jwt("", request)
        assert user_id is None

    @pytest.mark.asyncio
    async def test_jwt_user_rate_limiting(self):
        """Test JWT tokens get per-user rate limiting."""
        import jwt

        secret = b"test_secret"
        middleware = RateLimitMiddleware(requests_per_minute=2, gateway_secret=secret)

        # Create JWT for user1
        payload1 = {"sub": "wa-2025-01-01-USER01", "exp": 9999999999}
        token1 = jwt.encode(payload1, secret, algorithm="HS256")

        # Create request with JWT
        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers.get = Mock(return_value=f"Bearer {token1}")
        request.app.state = Mock()

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Make 2 requests - should succeed
        response1 = await middleware(request, call_next)
        response2 = await middleware(request, call_next)
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Third request should be rate limited
        response3 = await middleware(request, call_next)
        assert response3.status_code == 429

        # Check bucket was created with user_ prefix
        assert "user_wa-2025-01-01-USER01" in middleware.limiter.buckets

    @pytest.mark.asyncio
    async def test_different_users_independent_limits(self):
        """Test different JWT users have independent rate limits."""
        import jwt

        secret = b"test_secret"
        middleware = RateLimitMiddleware(requests_per_minute=1, gateway_secret=secret)

        # Create JWTs for two different users
        payload1 = {"sub": "wa-user1", "exp": 9999999999}
        payload2 = {"sub": "wa-user2", "exp": 9999999999}
        token1 = jwt.encode(payload1, secret, algorithm="HS256")
        token2 = jwt.encode(payload2, secret, algorithm="HS256")

        # Create requests for each user
        request1 = Mock(spec=Request)
        request1.url.path = "/v1/test"
        request1.client.host = "192.168.1.100"
        request1.headers.get = Mock(return_value=f"Bearer {token1}")
        request1.app.state = Mock()

        request2 = Mock(spec=Request)
        request2.url.path = "/v1/test"
        request2.client.host = "192.168.1.100"  # Same IP
        request2.headers.get = Mock(return_value=f"Bearer {token2}")
        request2.app.state = Mock()

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Both users make 1 request - should succeed
        response1 = await middleware(request1, call_next)
        response2 = await middleware(request2, call_next)

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both have independent limits
        assert "user_wa-user1" in middleware.limiter.buckets
        assert "user_wa-user2" in middleware.limiter.buckets

    @pytest.mark.asyncio
    async def test_jwt_extraction_failure_fallback(self):
        """Test malformed JWT falls back to IP-based rate limiting."""
        middleware = RateLimitMiddleware()

        # Request with malformed JWT
        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers.get = Mock(return_value="Bearer invalid-jwt-token")

        call_next = AsyncMock(return_value=Response(content="OK"))

        await middleware(request, call_next)

        # Should fall back to auth_IP format
        assert "auth_192.168.1.100" in middleware.limiter.buckets


class TestRateLimitMiddlewareEnforcement:
    """Test rate limit enforcement and responses."""

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(self):
        """Test rate limited request returns 429."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # First request succeeds
        response = await middleware(request, call_next)
        assert response.status_code == 200

        # Second request rate limited
        response = await middleware(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_429_response_includes_retry_after(self):
        """Test 429 response includes Retry-After header."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Deplete tokens
        await middleware(request, call_next)

        # Get 429 response
        response = await middleware(request, call_next)

        # Check headers
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

    @pytest.mark.asyncio
    async def test_429_response_content(self):
        """Test 429 response has proper error content."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Deplete tokens
        await middleware(request, call_next)

        # Get 429 response
        response = await middleware(request, call_next)

        # Parse JSON content
        import json

        content = json.loads(response.body.decode())
        assert content["detail"] == "Rate limit exceeded"
        assert "retry_after" in content


class TestRateLimitMiddlewareHeaders:
    """Test rate limit response headers."""

    @pytest.mark.asyncio
    async def test_response_includes_rate_limit_headers(self):
        """Test successful response includes rate limit headers."""
        middleware = RateLimitMiddleware(requests_per_minute=60)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        mock_response = Response(content="OK", status_code=200)
        call_next = AsyncMock(return_value=mock_response)

        response = await middleware(request, call_next)

        # Check headers added
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Window" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "60"
        assert response.headers["X-RateLimit-Window"] == "60"

    @pytest.mark.asyncio
    async def test_remaining_tokens_decreases(self):
        """Test remaining tokens header decreases with requests."""
        middleware = RateLimitMiddleware(requests_per_minute=60)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # First request
        response1 = await middleware(request, call_next)
        remaining1 = int(response1.headers["X-RateLimit-Remaining"])

        # Second request
        response2 = await middleware(request, call_next)
        remaining2 = int(response2.headers["X-RateLimit-Remaining"])

        # Remaining should decrease
        assert remaining2 < remaining1


class TestRateLimitMiddlewareIntegration:
    """Integration tests for full middleware flow."""

    @pytest.mark.asyncio
    async def test_multiple_clients_independent_limits(self):
        """Test different clients have independent rate limits."""
        middleware = RateLimitMiddleware(requests_per_minute=1)

        request1 = Mock(spec=Request)
        request1.url.path = "/v1/test"
        request1.client.host = "192.168.1.100"
        request1.headers = {}

        request2 = Mock(spec=Request)
        request2.url.path = "/v1/test"
        request2.client.host = "192.168.1.101"
        request2.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Both clients make 1 request - should succeed
        response1 = await middleware(request1, call_next)
        response2 = await middleware(request2, call_next)

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both make second request - should be rate limited
        response1 = await middleware(request1, call_next)
        response2 = await middleware(request2, call_next)

        assert response1.status_code == 429
        assert response2.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_recovers_over_time(self):
        """Test rate limit recovers as tokens refill."""
        middleware = RateLimitMiddleware(requests_per_minute=60)

        request = Mock(spec=Request)
        request.url.path = "/v1/test"
        request.client.host = "192.168.1.100"
        request.headers = {}

        call_next = AsyncMock(return_value=Response(content="OK"))

        # Make request
        await middleware(request, call_next)

        # Manually advance time by setting old timestamp
        client_id = "ip_192.168.1.100"
        tokens, _ = middleware.limiter.buckets[client_id]
        middleware.limiter.buckets[client_id] = (tokens, datetime.now() - timedelta(seconds=2))

        # Make another request - should succeed with refilled tokens
        response = await middleware(request, call_next)
        assert response.status_code == 200
