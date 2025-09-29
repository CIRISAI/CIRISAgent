"""Unlimit commerce service for pay-ins, invoices, refunds, payouts, and reporting."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

import httpx

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.runtime.enums import ServiceType

from .schemas import (
    InvoiceRequest,
    InvoiceResult,
    PaymentCustomer,
    PaymentRequest,
    PaymentResult,
    PayoutRequest,
    PayoutResult,
    RefundRequest,
    RefundResult,
    ReportEntry,
    ReportQuery,
)

logger = logging.getLogger(__name__)


class UnlimitCommerceService(BaseService):
    """Higher-level Unlimit integration for fiat economic activity."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.unlimit.com",
        api_key: Optional[str] = None,
        timeout_seconds: float = 10.0,
        restricted_countries: Optional[set[str]] = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(service_name="UnlimitCommerceService")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._restricted_countries = {c.upper() for c in restricted_countries or set()}
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    def get_service_type(self) -> ServiceType:
        return ServiceType.TOOL

    def _get_actions(self) -> list[str]:
        return [
            "create_payment",
            "create_invoice",
            "refund_payment",
            "create_payout",
            "get_payment",
            "get_reports",
        ]

    def _check_dependencies(self) -> bool:
        return True

    async def _on_start(self) -> None:
        async with self._client_lock:
            if self._client is not None:
                return
            headers = {"User-Agent": "CIRIS-Unlimit-Commerce/0.1"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers=headers,
                transport=self._transport,
            )
            logger.info("UnlimitCommerceService HTTP client initialised")

    async def _on_stop(self) -> None:
        async with self._client_lock:
            client, self._client = self._client, None
        if client:
            await client.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            await self._on_start()
        assert self._client is not None
        return self._client

    def _is_restricted(self, customer: PaymentCustomer) -> bool:
        if not self._restricted_countries:
            return False
        if customer and customer.country:
            return customer.country.upper() in self._restricted_countries
        return False

    async def create_payment(self, request: PaymentRequest) -> PaymentResult:
        if self._is_restricted(request.customer):
            reason = "payer_country_restricted"
            return PaymentResult(succeeded=False, status="blocked", reason=reason)

        payload = self._build_payment_payload(request)
        response_json, status_code = await self._post("/api/payments", payload)
        if not status_code or status_code >= 400:
            return PaymentResult(
                succeeded=False,
                status=response_json.get("status") if response_json else None,
                reason=self._extract_reason(response_json, status_code),
                provider_metadata=response_json or {},
            )

        return PaymentResult(
            succeeded=True,
            payment_id=response_json.get("payment_data", {}).get("id") if response_json else None,
            status=response_json.get("payment_data", {}).get("status") if response_json else None,
            redirect_url=response_json.get("redirect_url"),
            provider_metadata=response_json or {},
        )

    async def create_invoice(self, request: InvoiceRequest) -> InvoiceResult:
        if self._is_restricted(request.customer):
            return InvoiceResult(succeeded=False, status="blocked", reason="payer_country_restricted")

        payload = self._build_invoice_payload(request)
        response_json, status_code = await self._post("/api/invoices", payload)
        if not status_code or status_code >= 400:
            return InvoiceResult(
                succeeded=False,
                status=response_json.get("status") if response_json else None,
                reason=self._extract_reason(response_json, status_code),
                provider_metadata=response_json or {},
            )

        return InvoiceResult(
            succeeded=True,
            invoice_id=response_json.get("invoice", {}).get("id") if response_json else None,
            status=response_json.get("invoice", {}).get("status") if response_json else None,
            payment_url=response_json.get("invoice", {}).get("payment_url") if response_json else None,
            provider_metadata=response_json or {},
        )

    async def refund_payment(self, request: RefundRequest) -> RefundResult:
        path = f"/api/payments/{request.payment_id}/refunds"
        response_json, status_code = await self._post(path, self._build_refund_payload(request))
        if not status_code or status_code >= 400:
            return RefundResult(
                succeeded=False,
                status=response_json.get("status") if response_json else None,
                reason=self._extract_reason(response_json, status_code),
                provider_metadata=response_json or {},
            )

        return RefundResult(
            succeeded=True,
            refund_id=response_json.get("refund_data", {}).get("id") if response_json else None,
            status=response_json.get("refund_data", {}).get("status") if response_json else None,
            provider_metadata=response_json or {},
        )

    async def create_payout(self, request: PayoutRequest) -> PayoutResult:
        if request.beneficiary.country.upper() in self._restricted_countries:
            return PayoutResult(succeeded=False, status="blocked", reason="beneficiary_country_restricted")

        payload = self._build_payout_payload(request)
        response_json, status_code = await self._post("/api/payouts", payload)
        if not status_code or status_code >= 400:
            return PayoutResult(
                succeeded=False,
                status=response_json.get("status") if response_json else None,
                reason=self._extract_reason(response_json, status_code),
                provider_metadata=response_json or {},
            )

        return PayoutResult(
            succeeded=True,
            payout_id=response_json.get("payout_data", {}).get("id") if response_json else None,
            status=response_json.get("payout_data", {}).get("status") if response_json else None,
            provider_metadata=response_json or {},
        )

    async def get_payment(self, payment_id: str) -> PaymentResult:
        response_json, status_code = await self._get(f"/api/payments/{payment_id}")
        if not status_code or status_code >= 400:
            return PaymentResult(
                succeeded=False,
                status=response_json.get("status") if response_json else None,
                reason=self._extract_reason(response_json, status_code),
                provider_metadata=response_json or {},
            )

        return PaymentResult(
            succeeded=True,
            payment_id=payment_id,
            status=response_json.get("payment_data", {}).get("status") if response_json else None,
            redirect_url=response_json.get("redirect_url"),
            provider_metadata=response_json or {},
        )

    async def get_reports(self, query: ReportQuery) -> list[ReportEntry]:
        params = {
            "date_from": query.date_from.isoformat(),
            "date_to": query.date_to.isoformat(),
            "limit": query.limit,
        }
        if query.kind:
            params["kind"] = query.kind
        response_json, status_code = await self._get("/api/reports", params=params)
        if not status_code or status_code >= 400:
            reason = self._extract_reason(response_json, status_code)
            logger.warning("Failed to fetch reports from Unlimit: %s", reason)
            return []

        entries: list[ReportEntry] = []
        for item in response_json.get("items", []) if response_json else []:
            try:
                entries.append(
                    ReportEntry(
                        reference_id=item.get("reference_id", ""),
                        kind=item.get("kind", "unknown"),
                        amount=float(item.get("amount", 0.0)),
                        currency=item.get("currency", ""),
                        created_at=datetime.fromisoformat(item.get("created_at")),
                        status=item.get("status", "unknown"),
                        metadata={k: str(v) for k, v in item.get("metadata", {}).items()},
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Skipping malformed report entry: %s", exc)
        return entries

    async def _post(self, path: str, payload: Dict[str, object]) -> tuple[Dict[str, object], Optional[int]]:
        client = await self._ensure_client()
        try:
            response = await client.post(path, json=payload)
            json_payload = response.json() if response.content else {}
            return json_payload, response.status_code
        except httpx.RequestError as exc:
            logger.warning("Unlimit POST %s request error: %s", path, exc)
            return {"error": str(exc)}, None

    async def _get(self, path: str, params: Optional[Dict[str, object]] = None) -> tuple[Dict[str, object], Optional[int]]:
        client = await self._ensure_client()
        try:
            response = await client.get(path, params=params)
            json_payload = response.json() if response.content else {}
            return json_payload, response.status_code
        except httpx.RequestError as exc:
            logger.warning("Unlimit GET %s request error: %s", path, exc)
            return {"error": str(exc)}, None

    @staticmethod
    def _extract_reason(response_json: Optional[Dict[str, object]], status_code: Optional[int]) -> str:
        if response_json:
            for key in ("message", "detail", "reason", "error"):
                value = response_json.get(key)
                if isinstance(value, str) and value:
                    return value
        return f"http_{status_code}" if status_code else "request_error"

    @staticmethod
    def _build_payment_payload(request: PaymentRequest) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "request": {
                "id": request.request_id,
            },
            "merchant_order": {
                "description": request.description,
            },
            "payment_method": request.payment_method.value,
            "payment_data": {
                "amount": f"{request.amount:.2f}",
                "currency": request.currency,
            },
        }
        if request.metadata:
            payload["merchant_data"] = request.metadata
        if request.customer:
            payload["customer"] = {
                "email": request.customer.email,
                "phone": request.customer.phone,
                "full_name": request.customer.full_name,
                "country": request.customer.country,
            }
        return payload

    @staticmethod
    def _build_invoice_payload(request: InvoiceRequest) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "request": {
                "id": request.request_id,
            },
            "invoice_data": {
                "description": request.description,
                "amount": f"{request.amount:.2f}",
                "currency": request.currency,
            },
        }
        if request.items:
            payload["invoice_data"]["items"] = [
                {
                    "name": item.name,
                    "price": f"{item.unit_price:.2f}",
                    "quantity": item.quantity,
                }
                for item in request.items
            ]
        if request.customer:
            payload["customer"] = {
                "email": request.customer.email,
                "phone": request.customer.phone,
                "full_name": request.customer.full_name,
                "country": request.customer.country,
            }
        if request.metadata:
            payload["merchant_data"] = request.metadata
        return payload

    @staticmethod
    def _build_refund_payload(request: RefundRequest) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "request": {"id": request.request_id},
        }
        if request.amount is not None:
            payload.setdefault("refund_data", {})["amount"] = f"{request.amount:.2f}"
        if request.currency:
            payload.setdefault("refund_data", {})["currency"] = request.currency
        if request.reason:
            payload.setdefault("refund_data", {})["reason"] = request.reason
        return payload

    @staticmethod
    def _build_payout_payload(request: PayoutRequest) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "request": {"id": request.request_id},
            "payout_data": {
                "amount": f"{request.amount:.2f}",
                "currency": request.currency,
                "description": request.description,
            },
            "beneficiary": {
                "name": request.beneficiary.name,
                "account_number": request.beneficiary.account_number,
                "bank_code": request.beneficiary.bank_code,
                "country": request.beneficiary.country,
            },
        }
        if request.metadata:
            payload["merchant_data"] = request.metadata
        return payload


__all__ = ["UnlimitCommerceService"]
