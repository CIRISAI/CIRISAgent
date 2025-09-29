import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ciris_modular_services.unlimit_billing.tool_service import (
    AP2_CHECKOUT_TOOL,
    UnlimitBillingToolService,
)


def build_ap2_payload(amount: int = 1000, currency: str = "USD") -> dict:
    now = datetime.now(timezone.utc)
    intent_id = "intent-123"
    cart_id = "cart-123"
    intent = {
        "mandate_id": intent_id,
        "mandate_type": "intent",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "instructions": {"note": "buy something"},
        "constraints": {"max_amount_minor": str(amount)},
        "credential_reference": "cred-1",
        "signature": "sig-intent",
    }
    cart = {
        "mandate_id": cart_id,
        "mandate_type": "cart",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "amount_minor": amount,
        "currency": currency,
        "instructions": {"item": "test"},
        "constraints": {},
        "credential_reference": "cred-2",
        "signature": "sig-cart",
    }
    return {
        "mandates": {
            "intent": intent,
            "cart": cart,
            "credentials": [
                {
                    "credential_id": "cred-1",
                    "issuer": "issuer",
                    "subject": "subject",
                    "issued_at": now.isoformat(),
                    "proof_type": "eddsa",
                    "proof_value": "proof",
                }
            ],
        },
        "payment_method": {
            "method_type": "card",
            "provider": "unlimit",
            "payment_token": "tok_123",
            "linked_mandate_id": cart_id,
        },
        "metadata": {"source": "test"},
    }


@pytest.mark.asyncio
async def test_ap2_tool_success() -> None:
    charge_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal charge_calls
        if request.url.path.endswith("/billing/charges"):
            charge_calls += 1
            return httpx.Response(
                201,
                json={
                    "succeeded": True,
                    "transaction_id": "txn-1",
                    "balance_remaining": 9000,
                },
            )
        raise AssertionError(f"Unexpected path {request.url.path}")

    service = UnlimitBillingToolService(api_key="token", transport=httpx.MockTransport(handler))
    await service.start()

    payload = {
        "identity": {"oauth_provider": "google", "external_id": "user-1"},
        "charge": {"amount_minor": 1000, "currency": "USD"},
        "ap2": build_ap2_payload(),
    }

    result = await service.execute_tool(AP2_CHECKOUT_TOOL, payload)

    assert result.success is True
    assert result.data is not None
    assert result.data["transaction"]["transaction_id"] == "txn-1"
    assert result.data["mandates"]["cart"] == "cart-123"
    assert charge_calls == 1

    await service.stop()


@pytest.mark.asyncio
async def test_ap2_tool_amount_mismatch() -> None:
    async def fail_handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called")

    service = UnlimitBillingToolService(api_key="token", transport=httpx.MockTransport(fail_handler))
    await service.start()

    payload = {
        "identity": {"oauth_provider": "google", "external_id": "user-1"},
        "charge": {"amount_minor": 500, "currency": "USD"},
        "ap2": build_ap2_payload(amount=1000),
    }

    result = await service.execute_tool(AP2_CHECKOUT_TOOL, payload)

    assert result.success is False
    assert result.error == "amount_mismatch"

    await service.stop()


@pytest.mark.asyncio
async def test_ap2_tool_cart_expired() -> None:
    now = datetime.now(timezone.utc)
    payload = build_ap2_payload()
    payload["mandates"]["cart"]["expires_at"] = (now - timedelta(minutes=1)).isoformat()

    async def fail_handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called")

    service = UnlimitBillingToolService(api_key="token", transport=httpx.MockTransport(fail_handler))
    await service.start()

    params = {
        "identity": {"oauth_provider": "google", "external_id": "user-1"},
        "charge": {"amount_minor": 1000, "currency": "USD"},
        "ap2": payload,
    }

    result = await service.execute_tool(AP2_CHECKOUT_TOOL, params)

    assert result.success is False
    assert result.error == "cart_mandate_expired"

    await service.stop()


@pytest.mark.asyncio
async def test_validate_parameters() -> None:
    async def fail_handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called")

    service = UnlimitBillingToolService(api_key="token", transport=httpx.MockTransport(fail_handler))
    await service.start()

    valid = await service.validate_parameters(
        AP2_CHECKOUT_TOOL,
        {
            "identity": {"oauth_provider": "google", "external_id": "user-1"},
            "charge": {"amount_minor": 1000, "currency": "USD"},
            "ap2": build_ap2_payload(),
        },
    )
    assert valid is True

    invalid = await service.validate_parameters(
        AP2_CHECKOUT_TOOL,
        {
            "identity": {"oauth_provider": "google", "external_id": "user-1"},
            "charge": {"amount_minor": 1000, "currency": "USD"},
            "ap2": build_ap2_payload(amount=500),
        },
    )
    assert invalid is False

    await service.stop()
