import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from ciris_modular_services.unlimit_billing.protocol import UnlimitBillingProtocol
from ciris_modular_services.unlimit_billing.schemas import (
    BillingChargeRequest,
    BillingContext,
    BillingIdentity,
)
from ciris_modular_services.unlimit_billing.service import UnlimitBillingService


@pytest.mark.asyncio
async def test_successful_check_is_cached() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        data: dict[str, Any] = {
            "has_balance": True,
            "credits_remaining": 42,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "plan_name": "standard",
        }
        return httpx.Response(200, json=data)

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=60,
        transport=httpx.MockTransport(handler),
    )

    assert isinstance(service, UnlimitBillingProtocol)

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")

    result1 = await service.check_credits(identity)
    result2 = await service.check_credits(identity)

    assert result1.has_balance is True
    assert result2.has_balance is True
    assert call_count == 1, "second call should hit cache"

    await service.stop()


@pytest.mark.asyncio
async def test_payment_required_returns_denial() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"reason": "no credits"})

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")
    result = await service.check_credits(identity)

    assert result.has_balance is False
    assert result.reason == "no credits"

    await service.stop()


@pytest.mark.asyncio
async def test_request_error_fail_closed() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=0,
        fail_open=False,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")
    result = await service.check_credits(identity)

    assert result.has_balance is False
    assert "billing_failure" in (result.reason or "")

    await service.stop()


@pytest.mark.asyncio
async def test_request_error_fail_open() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=0,
        fail_open=True,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")
    context = BillingContext(agent_id="agent-1", channel_id="chan-1")
    result = await service.check_credits(identity, context=context)

    assert result.has_balance is True
    assert result.reason and result.reason.startswith("billing_failure")

    await service.stop()


@pytest.mark.asyncio
async def test_spend_success_clears_cache() -> None:
    charge_calls = 0
    check_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal charge_calls, check_calls
        if request.url.path.endswith("/credits/check"):
            data = {"has_balance": True, "credits_remaining": 100}
            check_calls += 1
            return httpx.Response(200, json=data)
        charge_calls += 1
        data = {
            "succeeded": True,
            "transaction_id": "txn-123",
            "balance_remaining": 50,
        }
        return httpx.Response(201, json=data)

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=60,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")

    # Prime the cache
    await service.check_credits(identity)
    # Spend credits
    charge = BillingChargeRequest(amount_minor=10, currency="EUR")
    result = await service.spend_credits(identity, charge)

    assert result.succeeded is True
    assert charge_calls == 1

    # Next balance check should fetch fresh data (handler returns 200 once)
    await service.check_credits(identity)
    assert check_calls == 2

    await service.stop()


@pytest.mark.asyncio
async def test_spend_denied_returns_reason() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/charges"):
            return httpx.Response(402, json={"reason": "insufficient_funds"})
        return httpx.Response(200, json={"has_balance": True})

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")
    charge = BillingChargeRequest(amount_minor=500, currency="USD", description="Purchase")

    result = await service.spend_credits(identity, charge)

    assert result.succeeded is False
    assert result.reason == "insufficient_funds"

    await service.stop()


@pytest.mark.asyncio
async def test_spend_request_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow network")

    service = UnlimitBillingService(
        api_key="token",
        cache_ttl_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    identity = BillingIdentity(oauth_provider="google", external_id="user-123")
    charge = BillingChargeRequest(amount_minor=100, currency="USD")

    result = await service.spend_credits(identity, charge)

    assert result.succeeded is False
    assert result.reason and "request_error" in result.reason

    await service.stop()
