"""Tests for MCP server adapter security module."""

import asyncio
from datetime import datetime, timezone

import pytest

from ciris_modular_services.mcp_server.config import AuthMethod, MCPServerSecurityConfig
from ciris_modular_services.mcp_server.security import (
    AuthResult,
    ClientSession,
    MCPServerAuthenticator,
    MCPServerRateLimiter,
    MCPServerSecurityManager,
)


class TestClientSession:
    """Tests for ClientSession dataclass."""

    def test_create_session(self) -> None:
        """Test creating a client session."""
        now = datetime.now(timezone.utc)
        session = ClientSession(
            client_id="test_client",
            client_name="Test Client",
            auth_method=AuthMethod.API_KEY,
            authenticated_at=now,
            last_activity=now,
        )
        assert session.client_id == "test_client"
        assert session.client_name == "Test Client"
        assert session.request_count == 0

    def test_session_expiry(self) -> None:
        """Test session expiry check."""
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        session = ClientSession(
            client_id="test",
            client_name="Test",
            auth_method=AuthMethod.NONE,
            authenticated_at=old_time,
            last_activity=old_time,
        )
        assert session.is_expired(timeout_seconds=3600) is True

    def test_session_touch(self) -> None:
        """Test session touch updates activity."""
        now = datetime.now(timezone.utc)
        session = ClientSession(
            client_id="test",
            client_name="Test",
            auth_method=AuthMethod.NONE,
            authenticated_at=now,
            last_activity=now,
        )
        old_count = session.request_count
        session.touch()
        assert session.request_count == old_count + 1


class TestMCPServerRateLimiter:
    """Tests for MCPServerRateLimiter."""

    @pytest.mark.asyncio
    async def test_allows_within_limits(self) -> None:
        """Test requests within limits are allowed."""
        limiter = MCPServerRateLimiter(
            max_requests_per_minute=100,
            max_concurrent=10,
        )

        allowed, reason = await limiter.check_rate_limit("client1")
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_blocks_when_rate_exceeded(self) -> None:
        """Test requests blocked when rate exceeded."""
        limiter = MCPServerRateLimiter(
            max_requests_per_minute=2,
            max_concurrent=10,
        )

        await limiter.acquire("client1")
        await limiter.acquire("client1")

        allowed, reason = await limiter.check_rate_limit("client1")
        assert allowed is False
        assert "Rate limit exceeded" in reason

    @pytest.mark.asyncio
    async def test_blocks_when_concurrent_exceeded(self) -> None:
        """Test requests blocked when concurrent limit exceeded."""
        limiter = MCPServerRateLimiter(
            max_requests_per_minute=100,
            max_concurrent=2,
        )

        await limiter.acquire("client1")
        await limiter.acquire("client1")

        allowed, reason = await limiter.check_rate_limit("client1")
        assert allowed is False
        assert "Concurrent limit exceeded" in reason

    @pytest.mark.asyncio
    async def test_acquire_and_release(self) -> None:
        """Test acquiring and releasing slots."""
        limiter = MCPServerRateLimiter(
            max_requests_per_minute=100,
            max_concurrent=1,
        )

        assert await limiter.acquire("client1") is True
        assert await limiter.acquire("client1") is False  # At limit

        await limiter.release("client1")
        assert await limiter.acquire("client1") is True  # Slot available

    def test_get_client_stats(self) -> None:
        """Test getting client statistics."""
        limiter = MCPServerRateLimiter(
            max_requests_per_minute=100,
            max_concurrent=10,
        )

        stats = limiter.get_client_stats("new_client")
        assert stats["requests_last_minute"] == 0
        assert stats["concurrent_requests"] == 0
        assert stats["limit_requests_per_minute"] == 100
        assert stats["limit_concurrent"] == 10


class TestMCPServerAuthenticator:
    """Tests for MCPServerAuthenticator."""

    @pytest.fixture
    def config_no_auth(self) -> MCPServerSecurityConfig:
        """Config with no auth required."""
        return MCPServerSecurityConfig(require_auth=False)

    @pytest.fixture
    def config_api_key(self) -> MCPServerSecurityConfig:
        """Config with API key auth."""
        return MCPServerSecurityConfig(
            require_auth=True,
            auth_methods=[AuthMethod.API_KEY],
            api_keys=["valid_key_123"],
        )

    @pytest.fixture
    def config_with_allowlist(self) -> MCPServerSecurityConfig:
        """Config with client allowlist."""
        return MCPServerSecurityConfig(
            require_auth=False,
            allowed_clients=["allowed-client"],
            blocked_clients=["blocked-client"],
        )

    @pytest.mark.asyncio
    async def test_auth_without_requirement(self, config_no_auth: MCPServerSecurityConfig) -> None:
        """Test authentication when not required."""
        auth = MCPServerAuthenticator(config_no_auth)

        result, session = await auth.authenticate(
            client_info={"name": "test-client", "version": "1.0"},
        )

        assert result == AuthResult.SUCCESS
        assert session is not None
        assert session.auth_method == AuthMethod.NONE

    @pytest.mark.asyncio
    async def test_auth_with_valid_api_key(self, config_api_key: MCPServerSecurityConfig) -> None:
        """Test authentication with valid API key."""
        auth = MCPServerAuthenticator(config_api_key)

        result, session = await auth.authenticate(
            client_info={"name": "test-client", "version": "1.0"},
            credentials={"api_key": "valid_key_123"},
        )

        assert result == AuthResult.SUCCESS
        assert session is not None
        assert session.auth_method == AuthMethod.API_KEY

    @pytest.mark.asyncio
    async def test_auth_with_invalid_api_key(self, config_api_key: MCPServerSecurityConfig) -> None:
        """Test authentication with invalid API key."""
        auth = MCPServerAuthenticator(config_api_key)

        result, session = await auth.authenticate(
            client_info={"name": "test-client", "version": "1.0"},
            credentials={"api_key": "invalid_key"},
        )

        assert result == AuthResult.FAILED
        assert session is None

    @pytest.mark.asyncio
    async def test_auth_missing_credentials(self, config_api_key: MCPServerSecurityConfig) -> None:
        """Test authentication with missing credentials."""
        auth = MCPServerAuthenticator(config_api_key)

        result, session = await auth.authenticate(
            client_info={"name": "test-client", "version": "1.0"},
        )

        assert result == AuthResult.FAILED
        assert session is None

    @pytest.mark.asyncio
    async def test_blocked_client(self, config_with_allowlist: MCPServerSecurityConfig) -> None:
        """Test blocked client is rejected."""
        auth = MCPServerAuthenticator(config_with_allowlist)

        result, session = await auth.authenticate(
            client_info={"name": "blocked-client", "version": "1.0"},
        )

        assert result == AuthResult.BLOCKED
        assert session is None

    @pytest.mark.asyncio
    async def test_client_not_in_allowlist(self, config_with_allowlist: MCPServerSecurityConfig) -> None:
        """Test client not in allowlist is rejected."""
        auth = MCPServerAuthenticator(config_with_allowlist)

        result, session = await auth.authenticate(
            client_info={"name": "unknown-client", "version": "1.0"},
        )

        assert result == AuthResult.FAILED
        assert session is None

    @pytest.mark.asyncio
    async def test_allowed_client(self, config_with_allowlist: MCPServerSecurityConfig) -> None:
        """Test allowed client is accepted."""
        auth = MCPServerAuthenticator(config_with_allowlist)

        result, session = await auth.authenticate(
            client_info={"name": "allowed-client", "version": "1.0"},
        )

        assert result == AuthResult.SUCCESS
        assert session is not None

    @pytest.mark.asyncio
    async def test_session_management(self, config_no_auth: MCPServerSecurityConfig) -> None:
        """Test session get and end."""
        auth = MCPServerAuthenticator(config_no_auth)

        # Create session
        result, session = await auth.authenticate(
            client_info={"name": "test", "version": "1.0"},
        )
        assert session is not None
        client_id = session.client_id

        # Get session
        retrieved = await auth.get_session(client_id)
        assert retrieved is not None
        assert retrieved.client_id == client_id

        # End session
        await auth.end_session(client_id)
        retrieved = await auth.get_session(client_id)
        assert retrieved is None


class TestMCPServerSecurityManager:
    """Tests for MCPServerSecurityManager."""

    @pytest.fixture
    def security_manager(self) -> MCPServerSecurityManager:
        """Create security manager for testing."""
        config = MCPServerSecurityConfig(
            require_auth=False,
            rate_limit_enabled=True,
            max_requests_per_minute=100,
            max_concurrent_requests=10,
            audit_requests=True,
        )
        return MCPServerSecurityManager(config)

    @pytest.mark.asyncio
    async def test_authenticate_client(self, security_manager: MCPServerSecurityManager) -> None:
        """Test client authentication through manager."""
        result, session = await security_manager.authenticate_client(
            client_info={"name": "test", "version": "1.0"},
        )
        assert result == AuthResult.SUCCESS
        assert session is not None

    @pytest.mark.asyncio
    async def test_authorize_request(self, security_manager: MCPServerSecurityManager) -> None:
        """Test request authorization."""
        _, session = await security_manager.authenticate_client(
            client_info={"name": "test", "version": "1.0"},
        )
        assert session is not None

        authorized, reason = await security_manager.authorize_request(
            session=session,
            method="tools/list",
            params={},
        )
        assert authorized is True

    @pytest.mark.asyncio
    async def test_authorize_request_no_permission(self, security_manager: MCPServerSecurityManager) -> None:
        """Test request authorization when no permission."""
        _, session = await security_manager.authenticate_client(
            client_info={"name": "test", "version": "1.0"},
        )
        assert session is not None

        # Remove permissions
        session.permissions = set()

        authorized, reason = await security_manager.authorize_request(
            session=session,
            method="tools/list",
            params={},
        )
        assert authorized is False
        assert "No permission" in reason

    @pytest.mark.asyncio
    async def test_record_request(self, security_manager: MCPServerSecurityManager) -> None:
        """Test request recording for audit."""
        await security_manager.record_request(
            client_id="test_client",
            method="tools/list",
            params={"cursor": "abc"},
            result="success",
            duration_ms=50.0,
        )

        records = security_manager.get_audit_records()
        assert len(records) == 1
        assert records[0]["client_id"] == "test_client"
        assert records[0]["method"] == "tools/list"
        assert records[0]["result"] == "success"

    @pytest.mark.asyncio
    async def test_rate_limit_integration(self, security_manager: MCPServerSecurityManager) -> None:
        """Test rate limiting through manager."""
        acquired = await security_manager.acquire_rate_limit("client1")
        assert acquired is True

        await security_manager.release_rate_limit("client1")

    def test_get_metrics(self, security_manager: MCPServerSecurityManager) -> None:
        """Test getting security metrics."""
        metrics = security_manager.get_metrics()
        assert "active_sessions" in metrics
        assert "audit_records" in metrics
        assert "auth_required" in metrics
        assert "rate_limit_enabled" in metrics
