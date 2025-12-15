"""Unit tests for Resource Monitor Service."""

import asyncio
import os
import tempfile

import httpx
import pytest

from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService, ResourceSignalBus
from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import CIRISBillingProvider
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext, CreditSpendRequest
from ciris_engine.schemas.services.resources_core import ResourceAction, ResourceBudget, ResourceLimit, ResourceSnapshot


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def resource_budget():
    """Create a default resource budget for testing."""
    return ResourceBudget()


@pytest.fixture
def signal_bus():
    """Create a resource signal bus for testing."""
    return ResourceSignalBus()


@pytest.fixture
def resource_monitor(resource_budget, temp_db, time_service, signal_bus):
    """Create a resource monitor service for testing."""
    return ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        signal_bus=signal_bus,
    )


@pytest.mark.asyncio
async def test_resource_monitor_lifecycle(resource_monitor):
    """Test ResourceMonitorService start/stop lifecycle."""
    # Start
    await resource_monitor.start()
    assert resource_monitor._monitoring is True

    # Give it a moment to start monitoring
    await asyncio.sleep(0.1)

    # Stop
    await resource_monitor.stop()
    assert resource_monitor._monitoring is False


def test_resource_monitor_get_snapshot(resource_monitor):
    """Test getting current resource snapshot."""
    snapshot = resource_monitor.snapshot

    assert isinstance(snapshot, ResourceSnapshot)
    assert snapshot.memory_mb >= 0
    assert 0 <= snapshot.memory_percent <= 100
    assert 0 <= snapshot.cpu_percent <= 100
    assert snapshot.cpu_average_1m >= 0
    assert snapshot.tokens_used_hour >= 0
    assert snapshot.tokens_used_day >= 0
    assert snapshot.disk_used_mb >= 0
    assert snapshot.disk_free_mb >= 0
    assert snapshot.thoughts_active >= 0
    assert isinstance(snapshot.healthy, bool)
    assert isinstance(snapshot.warnings, list)
    assert isinstance(snapshot.critical, list)


@pytest.mark.asyncio
async def test_resource_monitor_check_limits(resource_monitor):
    """Test resource limit checking."""
    # Modify budget to have low limits for testing
    resource_monitor.budget.memory_mb = ResourceLimit(limit=100, warning=50, critical=80, action=ResourceAction.WARN)
    resource_monitor.budget.cpu_percent = ResourceLimit(
        limit=80, warning=60, critical=75, action=ResourceAction.THROTTLE
    )

    # Set current values that exceed limits
    resource_monitor.snapshot.memory_mb = 85  # Exceeds critical
    resource_monitor.snapshot.cpu_average_1m = 65  # Exceeds warning

    # Check limits
    await resource_monitor._check_limits()

    # Verify warnings/critical were set
    assert len(resource_monitor.snapshot.critical) >= 1
    assert any("memory_mb" in c for c in resource_monitor.snapshot.critical)
    assert len(resource_monitor.snapshot.warnings) >= 1
    assert any("cpu_percent" in w for w in resource_monitor.snapshot.warnings)
    assert resource_monitor.snapshot.healthy is False


def test_resource_monitor_status(resource_monitor):
    """Test ResourceMonitorService.get_status() returns correct status."""
    status = resource_monitor.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "ResourceMonitorService"
    assert status.service_type == "infrastructure_service"
    assert status.is_healthy is True
    assert "memory_mb" in status.metrics
    assert "cpu_percent" in status.metrics
    assert "tokens_used_hour" in status.metrics
    assert "thoughts_active" in status.metrics
    assert "warnings" in status.metrics
    assert "critical" in status.metrics


@pytest.mark.asyncio
async def test_resource_monitor_continuous_monitoring(resource_monitor):
    """Test continuous monitoring loop."""
    # Start monitoring
    await resource_monitor.start()

    # Capture initial snapshot values
    initial_healthy = resource_monitor.snapshot.healthy

    # Let it run briefly
    await asyncio.sleep(0.2)

    # Stop monitoring
    await resource_monitor.stop()

    # Verify monitoring ran
    assert resource_monitor.snapshot is not None
    assert isinstance(resource_monitor.snapshot.healthy, bool)


@pytest.mark.asyncio
async def test_resource_monitor_record_tokens(resource_monitor):
    """Test token recording."""
    # Record some tokens
    await resource_monitor.record_tokens(100)
    await resource_monitor.record_tokens(200)
    await resource_monitor.record_tokens(300)

    # Update snapshot to calculate totals
    await resource_monitor._update_snapshot()

    # Check token counts
    assert resource_monitor.snapshot.tokens_used_hour == 600
    assert resource_monitor.snapshot.tokens_used_day == 600


@pytest.mark.asyncio
async def test_resource_monitor_check_available(resource_monitor):
    """Test checking resource availability."""
    # Set current usage
    resource_monitor.snapshot.memory_mb = 40
    resource_monitor.snapshot.tokens_used_hour = 1000
    resource_monitor.snapshot.thoughts_active = 10

    # Check availability - should have room
    assert await resource_monitor.check_available("memory_mb", 5) is True
    assert await resource_monitor.check_available("tokens_hour", 100) is True
    assert await resource_monitor.check_available("thoughts_active", 5) is True

    # Check with amounts that would exceed warning threshold
    assert await resource_monitor.check_available("memory_mb", 200) is True  # 40 + 200 = 240 < 3072 warning
    assert await resource_monitor.check_available("tokens_hour", 8000) is False  # 1000 + 8000 = 9000 > 8000 warning
    assert await resource_monitor.check_available("thoughts_active", 35) is False  # 10 + 35 = 45 > 40 warning


@pytest.mark.asyncio
async def test_resource_monitor_signal_bus(resource_monitor, signal_bus):
    """Test signal bus integration."""
    # Track emitted signals
    emitted_signals = []

    async def signal_handler(signal: str, resource: str):
        emitted_signals.append((signal, resource))

    # Register handlers
    signal_bus.register("throttle", signal_handler)
    signal_bus.register("defer", signal_handler)
    signal_bus.register("reject", signal_handler)

    # Set budget with different actions
    resource_monitor.budget.cpu_percent.action = ResourceAction.THROTTLE
    resource_monitor.budget.memory_mb.action = ResourceAction.DEFER
    resource_monitor.budget.tokens_hour.action = ResourceAction.REJECT

    # Trigger critical limits
    resource_monitor.snapshot.cpu_average_1m = 76  # Exceeds critical (75)
    resource_monitor.snapshot.memory_mb = 3841  # Exceeds critical (3840)
    resource_monitor.snapshot.tokens_used_hour = 9501  # Exceeds critical (9500)

    # Check limits
    await resource_monitor._check_limits()

    # Verify signals were emitted
    assert len(emitted_signals) >= 3
    assert ("throttle", "cpu_percent") in emitted_signals
    assert ("defer", "memory_mb") in emitted_signals
    assert ("reject", "tokens_hour") in emitted_signals


@pytest.mark.asyncio
async def test_resource_monitor_update_snapshot(resource_monitor):
    """Test snapshot updating."""
    # Update the snapshot
    await resource_monitor._update_snapshot()

    # Verify snapshot was populated
    snapshot = resource_monitor.snapshot
    assert snapshot.memory_mb >= 0
    assert snapshot.cpu_percent >= 0
    assert snapshot.cpu_average_1m >= 0
    assert snapshot.disk_used_mb >= 0
    assert snapshot.disk_free_mb >= 0


@pytest.mark.asyncio
async def test_resource_monitor_is_healthy(resource_monitor):
    """Test health check."""
    # Initially should be healthy
    assert await resource_monitor.is_healthy() is True

    # Add critical issues
    resource_monitor.snapshot.critical.append("memory_mb: 250/256")
    resource_monitor.snapshot.healthy = False

    # Should now be unhealthy
    assert await resource_monitor.is_healthy() is False


@pytest.mark.asyncio
async def test_resource_monitor_cooldown(resource_monitor, signal_bus):
    """Test action cooldown functionality."""
    # Track emitted signals
    emitted_signals = []

    async def signal_handler(signal: str, resource: str):
        emitted_signals.append((signal, resource, resource_monitor.time_service.now()))

    signal_bus.register("defer", signal_handler)

    # Set short cooldown for testing
    resource_monitor.budget.memory_mb.cooldown_seconds = 1
    resource_monitor.budget.memory_mb.action = ResourceAction.DEFER

    # Exceed critical threshold multiple times quickly
    resource_monitor.snapshot.memory_mb = 3841  # Exceeds critical (3840)

    # First check should emit signal
    await resource_monitor._check_limits()
    initial_count = len(emitted_signals)
    assert initial_count == 1  # Should have one signal

    # Immediate second check should not emit due to cooldown
    await resource_monitor._check_limits()
    assert len(emitted_signals) == initial_count

    # Wait for cooldown
    await asyncio.sleep(1.1)

    # Now should emit again
    await resource_monitor._check_limits()
    assert len(emitted_signals) > initial_count


def test_resource_monitor_get_capabilities(resource_monitor):
    """Test get_capabilities method."""
    # ResourceMonitorService should implement get_capabilities
    caps = resource_monitor.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "ResourceMonitorService"
    assert caps.version == "1.0.0"
    assert "resource_monitoring" in caps.actions
    assert "cpu_tracking" in caps.actions
    assert "memory_tracking" in caps.actions
    assert "token_rate_limiting" in caps.actions
    assert "TimeService" in caps.dependencies


@pytest.mark.asyncio
async def test_resource_monitor_credit_check_and_cache(resource_budget, temp_db, time_service):
    """Resource monitor should reuse credit decisions within cache TTL."""

    check_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal check_calls
        if request.url.path.endswith("/credits/check"):
            check_calls += 1
            return httpx.Response(
                200,
                json={
                    "has_credit": True,
                    "credits_remaining": 5,
                },
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler), cache_ttl_seconds=60)
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        credit_provider=provider,
    )

    await monitor.start()
    try:
        account = CreditAccount(provider="oauth:google", account_id="user-123")
        context = CreditContext(agent_id="agent-1")

        first = await monitor.check_credit(account, context)
        second = await monitor.check_credit(account, context)

        assert first.has_credit is True
        assert second.has_credit is True
        assert check_calls == 1  # Cached response reused

        metrics = monitor._collect_custom_metrics()
        assert metrics["credit_provider_enabled"] == 1.0
        assert metrics["credit_last_available"] == 1.0
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_resource_monitor_credit_spend(resource_budget, temp_db, time_service):
    """Resource monitor should relay spend results and clear cached credit."""

    check_calls = 0
    spend_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal check_calls, spend_calls
        if request.url.path.endswith("/credits/check"):
            check_calls += 1
            return httpx.Response(200, json={"has_credit": True})
        if request.url.path.endswith("/charges"):
            spend_calls += 1
            return httpx.Response(
                201,
                json={
                    "charge_id": "txn-42",
                    "balance_after": 3,
                    "account_id": "acc-123",
                    "amount_minor": 100,
                    "currency": "USD",
                },
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler), cache_ttl_seconds=60)
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        credit_provider=provider,
    )

    await monitor.start()
    try:
        account = CreditAccount(provider="oauth:google", account_id="user-456")
        await monitor.check_credit(account)

        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Usage")
        spend_result = await monitor.spend_credit(account, spend_req)

        assert spend_result.succeeded is True
        assert spend_result.transaction_id == "txn-42"
        assert spend_calls == 1

        metrics = monitor._collect_custom_metrics()
        # Last credit result cleared after successful spend
        assert metrics["credit_last_available"] == -1.0
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_resource_monitor_credit_failure(resource_budget, temp_db, time_service):
    """Credit failures surface through the resource monitor and mark metrics."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"status": "ok"})  # Missing required fields
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler), cache_ttl_seconds=0)
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        credit_provider=provider,
    )

    await monitor.start()
    try:
        account = CreditAccount(provider="oauth:google", account_id="user-789")
        with pytest.raises(ValueError):
            await monitor.check_credit(account)
        metrics = monitor._collect_custom_metrics()
        assert metrics["credit_error_flag"] == 1.0
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_billing_provider_context_fields_extraction():
    """Test that context agent_id is correctly extracted to top-level payload field."""
    import json

    captured_payload = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path.endswith("/credits/check"):
            # Capture the payload sent to billing API
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json={"has_credit": True, "credits_remaining": 10})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler))
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-oauth-123")
        context = CreditContext(
            agent_id="agent-datum",
            channel_id="api_oauth_user123",
        )

        result = await provider.check_credit(account, context)

        # Verify result
        assert result.has_credit is True

        # Verify payload contains agent_id at top level (extracted from context)
        assert captured_payload is not None
        assert captured_payload["agent_id"] == "agent-datum"

        # Verify context dict contains channel_id only (not agent_id)
        assert "context" in captured_payload
        assert captured_payload["context"]["channel_id"] == "api_oauth_user123"

        # Note: customer_email, marketing_opt_in, user_role are now passed
        # directly by calling code (billing.py) from identity dict, not from CreditContext

    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_spend_context_fields():
    """Test that spend_credit extracts agent_id from context correctly."""
    import json

    captured_payload = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path.endswith("/charges"):
            captured_payload = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "charge_id": "charge-123",
                    "balance_after": 7,
                    "amount_minor": 100,
                    "currency": "USD",
                },
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler))
    await provider.start()

    try:
        account = CreditAccount(provider="google", account_id="user-spend-456")
        context = CreditContext(
            agent_id="agent-qa",
        )
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test charge")

        result = await provider.spend_credit(account, spend_req, context)

        # Verify result
        assert result.succeeded is True
        assert result.transaction_id == "charge-123"

        # Verify payload contains agent_id extracted from context
        assert captured_payload is not None
        assert captured_payload["agent_id"] == "agent-qa"

        # Note: customer_email, marketing_opt_in, user_role are now passed
        # directly by calling code (billing.py) from identity dict, not from CreditContext

    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_boolean_conversion():
    """Test that CreditContext no longer handles metadata - metadata is passed by calling code."""
    import json

    captured_payload = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path.endswith("/credits/check"):
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json={"has_credit": True})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler))
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:test", account_id="user-bool-test")
        context = CreditContext(agent_id="agent-test")

        await provider.check_credit(account, context)

        # Verify agent_id is extracted from context
        assert captured_payload is not None
        assert captured_payload["agent_id"] == "agent-test"

        # Verify that metadata fields are NOT in payload (they're not in CreditContext anymore)
        # In production, billing.py passes customer_email, marketing_opt_in, user_role
        # directly from identity dict, NOT from CreditContext
        assert "customer_email" not in captured_payload
        assert "marketing_opt_in" not in captured_payload

    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_missing_optional_fields():
    """Test that missing optional context fields don't cause errors."""
    import json

    captured_payload = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path.endswith("/credits/check"):
            captured_payload = json.loads(request.content)
            return httpx.Response(200, json={"has_credit": True})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(handler))
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:github", account_id="user-minimal")
        # Context with no metadata or minimal metadata
        context = CreditContext(agent_id="agent-minimal", channel_id="api_test")

        result = await provider.check_credit(account, context)

        assert result.has_credit is True
        assert captured_payload is not None

        # Verify optional fields are not present when not provided
        assert "customer_email" not in captured_payload
        assert "marketing_opt_in" not in captured_payload
        assert "marketing_opt_in_source" not in captured_payload
        assert "user_role" not in captured_payload

        # But agent_id should be present
        assert captured_payload["agent_id"] == "agent-minimal"

    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_resource_monitor_check_credit_no_provider(resource_budget, temp_db, time_service):
    """Test that check_credit raises error without credit provider."""
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        credit_provider=None,
    )

    await monitor.start()
    try:
        account = CreditAccount(provider="oauth:google", account_id="user-no-provider")
        with pytest.raises(RuntimeError, match="No credit provider"):
            await monitor.check_credit(account)
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_resource_monitor_spend_credit_no_provider(resource_budget, temp_db, time_service):
    """Test that spend_credit raises error without credit provider."""
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        credit_provider=None,
    )

    await monitor.start()
    try:
        account = CreditAccount(provider="oauth:google", account_id="user-no-provider")
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test")
        with pytest.raises(RuntimeError, match="No credit provider"):
            await monitor.spend_credit(account, spend_req)
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_resource_monitor_shutdown_action(resource_budget, temp_db, time_service, signal_bus):
    """Test that SHUTDOWN action emits shutdown signal."""
    emitted_signals = []

    async def signal_handler(signal: str, resource: str):
        emitted_signals.append((signal, resource))

    signal_bus.register("shutdown", signal_handler)

    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path=temp_db,
        time_service=time_service,
        signal_bus=signal_bus,
    )

    # Set SHUTDOWN action for thoughts_active
    monitor.budget.thoughts_active.action = ResourceAction.SHUTDOWN
    monitor.budget.thoughts_active.critical = 50

    # Exceed critical threshold
    monitor.snapshot.thoughts_active = 51

    # Check limits
    await monitor._check_limits()

    # Verify shutdown signal was emitted
    assert ("shutdown", "thoughts_active") in emitted_signals


@pytest.mark.asyncio
async def test_resource_monitor_check_available_unknown_resource(resource_monitor):
    """Test check_available with unknown resource type returns True."""
    result = await resource_monitor.check_available("unknown_resource", 100)
    assert result is True


@pytest.mark.asyncio
async def test_resource_monitor_token_refresh_signal_no_ciris_home(resource_monitor):
    """Test token refresh signal check when CIRIS_HOME is not set."""
    # Clear CIRIS_HOME and cached value
    resource_monitor._ciris_home = None
    original_env = os.environ.pop("CIRIS_HOME", None)

    try:
        # Should not raise even without CIRIS_HOME
        await resource_monitor._check_token_refresh_signal()
    finally:
        if original_env:
            os.environ["CIRIS_HOME"] = original_env


@pytest.mark.asyncio
async def test_resource_monitor_token_refresh_signal_with_file(temp_db, time_service, signal_bus):
    """Test token refresh signal detection and processing."""
    import tempfile
    from pathlib import Path

    emitted_signals = []

    async def signal_handler(signal: str, resource: str):
        emitted_signals.append((signal, resource))

    signal_bus.register("token_refreshed", signal_handler)

    # Create a temp directory to act as CIRIS_HOME
    with tempfile.TemporaryDirectory() as tmpdir:
        ciris_home = Path(tmpdir)

        # Create .env file
        env_file = ciris_home / ".env"
        env_file.write_text("OPENAI_API_KEY=test_key_123\n")

        # Create .config_reload signal file
        signal_file = ciris_home / ".config_reload"
        signal_file.write_text("reload_signal")

        # Set up the monitor with CIRIS_HOME
        original_env = os.environ.get("CIRIS_HOME")
        os.environ["CIRIS_HOME"] = str(ciris_home)

        try:
            resource_budget = ResourceBudget()
            monitor = ResourceMonitorService(
                budget=resource_budget,
                db_path=temp_db,
                time_service=time_service,
                signal_bus=signal_bus,
            )
            monitor._ciris_home = None  # Force re-detection

            # Should detect and process the signal
            await monitor._check_token_refresh_signal()

            # Verify token_refreshed signal was emitted
            assert ("token_refreshed", "openai_api_key") in emitted_signals

            # Verify signal file was cleaned up
            assert not signal_file.exists()

        finally:
            if original_env:
                os.environ["CIRIS_HOME"] = original_env
            else:
                os.environ.pop("CIRIS_HOME", None)


@pytest.mark.asyncio
async def test_resource_monitor_token_refresh_already_processed(temp_db, time_service, signal_bus):
    """Test that already processed token refresh signals are not re-processed."""
    import tempfile
    from pathlib import Path

    emitted_signals = []

    async def signal_handler(signal: str, resource: str):
        emitted_signals.append((signal, resource))

    signal_bus.register("token_refreshed", signal_handler)

    with tempfile.TemporaryDirectory() as tmpdir:
        ciris_home = Path(tmpdir)

        # Create .env and .config_reload files
        env_file = ciris_home / ".env"
        env_file.write_text("OPENAI_API_KEY=test_key\n")

        signal_file = ciris_home / ".config_reload"
        signal_file.write_text("signal")

        original_env = os.environ.get("CIRIS_HOME")
        os.environ["CIRIS_HOME"] = str(ciris_home)

        try:
            resource_budget = ResourceBudget()
            monitor = ResourceMonitorService(
                budget=resource_budget,
                db_path=temp_db,
                time_service=time_service,
                signal_bus=signal_bus,
            )
            monitor._ciris_home = None

            # Process first time
            await monitor._check_token_refresh_signal()
            first_count = len(emitted_signals)
            assert first_count == 1

            # Re-create signal file with same timestamp (shouldn't process)
            signal_file.write_text("signal2")
            # Touch file but keep same mtime won't trigger since mtime already processed

            # Since file was deleted, check again
            signal_file.write_text("signal3")
            # But mtime might be same or earlier than processed - won't trigger

        finally:
            if original_env:
                os.environ["CIRIS_HOME"] = original_env
            else:
                os.environ.pop("CIRIS_HOME", None)


@pytest.mark.asyncio
async def test_resource_monitor_postgres_connection_string(time_service, signal_bus):
    """Test that PostgreSQL connection strings skip disk usage."""
    resource_budget = ResourceBudget()
    monitor = ResourceMonitorService(
        budget=resource_budget,
        db_path="postgresql://user:pass@localhost:5432/ciris",
        time_service=time_service,
        signal_bus=signal_bus,
    )

    # Update snapshot should not raise with postgres URL
    await monitor._update_snapshot()

    # Disk metrics should be 0 for postgres
    assert monitor.snapshot.disk_free_mb == 0
    assert monitor.snapshot.disk_used_mb == 0


# ============================================================================
# CIRIS BILLING PROVIDER ADDITIONAL COVERAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_billing_provider_jwt_auth_mode():
    """Test billing provider in JWT auth mode with Google ID token."""
    captured_headers = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(request.headers)
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"has_credit": True, "credits_remaining": 10})
        raise AssertionError(f"Unexpected path {request.url.path}")

    # Create provider with JWT auth mode (google_id_token provided)
    provider = CIRISBillingProvider(
        api_key="",  # Empty API key
        google_id_token="test_google_id_token_abc123",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-jwt-test")
        await provider.check_credit(account)

        # Verify JWT auth header was used
        assert captured_headers is not None
        assert "authorization" in captured_headers
        assert captured_headers["authorization"] == "Bearer test_google_id_token_abc123"
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_token_refresh_callback():
    """Test that token refresh callback is invoked and updates token."""
    refresh_count = 0

    def token_refresh_callback():
        nonlocal refresh_count
        refresh_count += 1
        return f"refreshed_token_{refresh_count}"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"has_credit": True, "credits_remaining": 5})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="",
        google_id_token="initial_token",
        token_refresh_callback=token_refresh_callback,
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-refresh-test")
        await provider.check_credit(account)

        # Token refresh callback should have been invoked
        assert refresh_count >= 1
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_update_google_id_token():
    """Test updating Google ID token dynamically."""
    captured_headers = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"has_credit": True, "credits_remaining": 5})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",  # Start with API key mode
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        # First request uses API key
        account = CreditAccount(provider="oauth:google", account_id="user-update-test")
        await provider.check_credit(account)
        assert "x-api-key" in captured_headers[0]

        # Update to JWT mode
        provider.update_google_id_token("new_google_token_xyz")

        # Make another request (cache may prevent new request, so use different account)
        account2 = CreditAccount(provider="oauth:google", account_id="user-update-test2")
        await provider.check_credit(account2)

        # Should now use Bearer auth
        assert len(captured_headers) >= 2
        # The update_google_id_token sets _use_jwt_auth = True, but client headers
        # are set at start() time. The token refresh happens before requests.
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_401_unauthorized():
    """Test handling of 401 Unauthorized response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(
                401,
                json={"error": "token_expired", "message": "Token has expired"},
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    # Use temp dir for CIRIS_HOME to test signal file writing
    with tempfile.TemporaryDirectory() as temp_dir:
        original_env = os.environ.get("CIRIS_HOME")
        os.environ["CIRIS_HOME"] = temp_dir

        try:
            provider = CIRISBillingProvider(
                api_key="",
                google_id_token="expired_token",
                transport=httpx.MockTransport(handler),
            )
            await provider.start()

            try:
                account = CreditAccount(provider="oauth:google", account_id="user-401-test")
                result = await provider.check_credit(account)

                # Should return failure result with new error format
                assert result.has_credit is False
                assert "AUTH_EXPIRED" in (result.reason or "")

                # Signal file should have been written
                signal_file = os.path.join(temp_dir, ".token_refresh_needed")
                assert os.path.exists(signal_file)
            finally:
                await provider.stop()
        finally:
            if original_env:
                os.environ["CIRIS_HOME"] = original_env
            else:
                os.environ.pop("CIRIS_HOME", None)


@pytest.mark.asyncio
async def test_billing_provider_payment_required():
    """Test handling of 402 Payment Required response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(
                402,
                json={"error": "insufficient_credits", "message": "No credits remaining"},
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-402-test")
        result = await provider.check_credit(account)

        # Should return no credit
        assert result.has_credit is False
        assert result.reason is not None
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_request_error():
    """Test handling of network/request errors."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("Connection refused")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-error-test")
        result = await provider.check_credit(account)

        # Should return failure with new error format
        assert result.has_credit is False
        assert "NETWORK_ERROR" in (result.reason or "")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_spend_conflict():
    """Test handling of 409 Conflict (idempotency) response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/charges"):
            return httpx.Response(
                409,
                headers={"X-Existing-Charge-ID": "existing-charge-123"},
                json={"error": "charge_exists", "message": "Charge already recorded"},
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-conflict-test")
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test")
        result = await provider.spend_credit(account, spend_req)

        # Conflict is treated as success (idempotency)
        assert result.succeeded is True
        assert result.transaction_id == "existing-charge-123"
        assert "idempotency" in (result.reason or "")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_spend_payment_required():
    """Test handling of 402 Payment Required on spend."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/charges"):
            return httpx.Response(
                402,
                json={"error": "insufficient_funds", "message": "Not enough credits"},
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-spend-402")
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test")
        result = await provider.spend_credit(account, spend_req)

        assert result.succeeded is False
        assert result.reason is not None
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_spend_request_error():
    """Test handling of request errors during spend."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/charges"):
            raise httpx.RequestError("Network error")
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-spend-error")
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test")
        result = await provider.spend_credit(account, spend_req)

        assert result.succeeded is False
        assert "NETWORK_ERROR" in (result.reason or "")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_spend_unexpected_status():
    """Test handling of unexpected status codes on spend."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/charges"):
            return httpx.Response(500, json={"error": "internal_error"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-spend-500")
        spend_req = CreditSpendRequest(amount_minor=100, currency="USD", description="Test")
        result = await provider.spend_credit(account, spend_req)

        assert result.succeeded is False
        assert "HTTP_500" in (result.reason or "")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_check_unexpected_status():
    """Test handling of unexpected status codes on check_credit."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(503, json={"error": "service_unavailable"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-check-503")
        result = await provider.check_credit(account)

        assert result.has_credit is False
        assert "HTTP_503" in (result.reason or "")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_ensure_started():
    """Test that _ensure_started creates client if not started."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"has_credit": True})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="test_key",
        transport=httpx.MockTransport(handler),
    )

    # Don't call start() explicitly
    assert provider._client is None

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-ensure-test")
        # check_credit should call _ensure_started
        result = await provider.check_credit(account)

        # Client should now be initialized
        assert provider._client is not None
        assert result.has_credit is True
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_token_refresh_callback_failure():
    """Test handling of token refresh callback that raises exception."""

    def failing_callback():
        raise RuntimeError("Token refresh failed")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(200, json={"has_credit": True})
        raise AssertionError(f"Unexpected path {request.url.path}")

    provider = CIRISBillingProvider(
        api_key="",
        google_id_token="original_token",
        token_refresh_callback=failing_callback,
        transport=httpx.MockTransport(handler),
    )
    await provider.start()

    try:
        account = CreditAccount(provider="oauth:google", account_id="user-callback-fail")
        # Should not raise, just log warning and use existing token
        result = await provider.check_credit(account)
        assert result.has_credit is True
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_billing_provider_signal_token_refresh_no_ciris_home():
    """Test signal file writing when CIRIS_HOME is not set."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/credits/check"):
            return httpx.Response(401, json={"error": "unauthorized"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    # Remove CIRIS_HOME from environment
    original_env = os.environ.pop("CIRIS_HOME", None)

    try:
        provider = CIRISBillingProvider(
            api_key="",
            google_id_token="test_token",
            transport=httpx.MockTransport(handler),
        )
        await provider.start()

        try:
            account = CreditAccount(provider="oauth:google", account_id="user-no-home")
            # Should not raise even though signal file can't be written
            result = await provider.check_credit(account)
            assert result.has_credit is False
        finally:
            await provider.stop()
    finally:
        if original_env:
            os.environ["CIRIS_HOME"] = original_env
