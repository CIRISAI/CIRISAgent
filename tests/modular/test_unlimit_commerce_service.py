import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ciris_modular_services.unlimit_billing.commerce_service import UnlimitCommerceService
from ciris_modular_services.unlimit_billing.schemas import (
    InvoiceItem,
    InvoiceRequest,
    PaymentCustomer,
    PaymentMethod,
    PaymentRequest,
    PayoutBeneficiary,
    PayoutRequest,
    RefundRequest,
    ReportQuery,
)


@pytest.mark.asyncio
async def test_create_payment_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/payments"
        body = json.loads(request.content)
        assert body["payment_method"] == PaymentMethod.CARD.value
        return httpx.Response(
            201,
            json={
                "payment_data": {"id": "pay-1", "status": "pending"},
                "redirect_url": "https://checkout.example/redirect",
            },
        )

    service = UnlimitCommerceService(transport=httpx.MockTransport(handler))
    await service.start()

    result = await service.create_payment(
        PaymentRequest(
            request_id="req-1",
            description="Order",
            amount=12.34,
            currency="USD",
            payment_method=PaymentMethod.CARD,
            customer=PaymentCustomer(email="buyer@example.com"),
        )
    )

    assert result.succeeded is True
    assert result.payment_id == "pay-1"
    await service.stop()


@pytest.mark.asyncio
async def test_create_invoice_restricted_country() -> None:
    service = UnlimitCommerceService(restricted_countries={"RU"})
    await service.start()

    result = await service.create_invoice(
        InvoiceRequest(
            request_id="req-1",
            description="Invoice",
            amount=50.0,
            currency="USD",
            customer=PaymentCustomer(country="RU"),
        )
    )

    assert result.succeeded is False
    assert result.reason == "payer_country_restricted"
    await service.stop()


@pytest.mark.asyncio
async def test_refund_payment_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "invalid payment"})

    service = UnlimitCommerceService(transport=httpx.MockTransport(handler))
    await service.start()

    result = await service.refund_payment(
        RefundRequest(payment_id="pay-1", request_id="req-2", amount=5.0)
    )

    assert result.succeeded is False
    assert result.reason == "invalid payment"
    await service.stop()


@pytest.mark.asyncio
async def test_create_payout_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/payouts"
        return httpx.Response(201, json={"payout_data": {"id": "payout-1", "status": "processing"}})

    service = UnlimitCommerceService(transport=httpx.MockTransport(handler))
    await service.start()

    result = await service.create_payout(
        PayoutRequest(
            request_id="req-3",
            amount=20.0,
            currency="USD",
            description="Creator payout",
            beneficiary=PayoutBeneficiary(
                name="Alice", account_number="123456", bank_code="001", country="US"
            ),
        )
    )

    assert result.succeeded is True
    assert result.payout_id == "payout-1"
    await service.stop()


@pytest.mark.asyncio
async def test_get_payment_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    service = UnlimitCommerceService(transport=httpx.MockTransport(handler))
    await service.start()

    result = await service.get_payment("missing")
    assert result.succeeded is False
    assert result.reason == "not found"
    await service.stop()


@pytest.mark.asyncio
async def test_get_reports_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "reference_id": "pay-1",
                        "kind": "payment",
                        "amount": "12.34",
                        "currency": "USD",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "succeeded",
                        "metadata": {"note": "test"},
                    }
                ]
            },
        )

    service = UnlimitCommerceService(transport=httpx.MockTransport(handler))
    await service.start()

    query = ReportQuery(
        date_from=datetime.now(timezone.utc) - timedelta(days=1),
        date_to=datetime.now(timezone.utc),
        limit=10,
    )

    reports = await service.get_reports(query)
    assert len(reports) == 1
    assert reports[0].reference_id == "pay-1"
    await service.stop()
