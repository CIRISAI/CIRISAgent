"""Unlimit billing service implementation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from .protocol import UnlimitBillingProtocol
from .schemas import (
    BillingChargeRequest,
    BillingChargeResult,
    BillingCheckResult,
    BillingContext,
    BillingIdentity,
)

logger = logging.getLogger(__name__)


class UnlimitBillingService(UnlimitBillingProtocol):
    """Async billing service that checks credit balances via Unlimit."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.unlimit.com",
        api_key: Optional[str] = None,
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: int = 15,
        fail_open: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._cache_ttl = max(cache_ttl_seconds, 0)
        self._fail_open = fail_open
        self._transport = transport

        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._cache: Dict[str, tuple[BillingCheckResult, datetime]] = {}

    async def start(self) -> None:
        """Initialise the HTTP client lazily."""
        async with self._client_lock:
            if self._client is not None:
                return

            headers = {"User-Agent": "CIRIS-Unlimit-Billing/0.1"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers=headers,
                transport=self._transport,
            )
            logger.info("UnlimitBillingService started with base_url=%s", self._base_url)

    async def stop(self) -> None:
        """Dispose of the HTTP client and clear caches."""
        async with self._client_lock:
            client, self._client = self._client, None
        if client:
            await client.aclose()
        self._cache.clear()
        logger.info("UnlimitBillingService stopped")

    async def check_credits(
        self,
        identity: BillingIdentity,
        context: Optional[BillingContext] = None,
    ) -> BillingCheckResult:
        """Check if the supplied identity has available credits."""
        if not identity.oauth_provider or not identity.external_id:
            raise ValueError("Billing identity must include oauth_provider and external_id")

        await self._ensure_started()

        cache_key = identity.cache_key()
        cached = self._cache.get(cache_key)
        if cached and not self._is_expired(cached[1]):
            logger.debug("Billing cache hit for %s", cache_key)
            return cached[0].model_copy()

        payload = self._build_payload(identity, context)
        logger.debug("Billing request payload for %s: %s", cache_key, payload)

        try:
            assert self._client is not None  # nosec - ensured by _ensure_started
            response = await self._client.post("/v1/billing/credits/check", json=payload)
            logger.debug("Billing response status=%s", response.status_code)
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.warning("Billing request failed for %s: %s", cache_key, exc)
            return self._handle_failure("request_error", str(exc))

        if response.status_code == httpx.codes.OK:
            result = self._parse_success(response.json())
            self._store_cache(cache_key, result)
            return result

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            result = BillingCheckResult(has_balance=False, reason=reason)
            self._store_cache(cache_key, result)
            return result

        reason = self._extract_reason(response)
        logger.warning(
            "Unexpected billing response for %s: status=%s reason=%s",
            cache_key,
            response.status_code,
            reason,
        )
        return self._handle_failure(f"unexpected_status_{response.status_code}", reason)

    async def spend_credits(
        self,
        identity: BillingIdentity,
        charge: BillingChargeRequest,
        context: BillingContext | None = None,
    ) -> BillingChargeResult:
        """Execute a spend against the billing account."""

        if charge.amount_minor <= 0:
            raise ValueError("Charge amount must be positive")

        await self._ensure_started()

        payload = self._build_charge_payload(identity, charge, context)
        cache_key = identity.cache_key()
        logger.debug("Billing charge payload for %s: %s", cache_key, payload)

        try:
            assert self._client is not None
            response = await self._client.post("/v1/billing/charges", json=payload)
            logger.debug(
                "Billing charge response for %s: status=%s", cache_key, response.status_code
            )
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.warning("Billing charge request failed for %s: %s", cache_key, exc)
            return BillingChargeResult(succeeded=False, reason=f"charge_failure:request_error:{exc}")

        if response.status_code in {httpx.codes.OK, httpx.codes.CREATED}:
            result = self._parse_charge_success(response.json())
            self._invalidate_cache(cache_key)
            return result

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            self._invalidate_cache(cache_key)
            return BillingChargeResult(succeeded=False, reason=reason)

        reason = self._extract_reason(response)
        logger.warning(
            "Unexpected billing charge response for %s: status=%s reason=%s",
            cache_key,
            response.status_code,
            reason,
        )
        return BillingChargeResult(
            succeeded=False,
            reason=f"charge_failure:unexpected_status_{response.status_code}:{reason}",
        )

    async def _ensure_started(self) -> None:
        if self._client is not None:
            return
        await self.start()

    def _store_cache(self, cache_key: str, result: BillingCheckResult) -> None:
        if self._cache_ttl <= 0:
            return
        expiry = datetime.now(timezone.utc) + timedelta(seconds=self._cache_ttl)
        self._cache[cache_key] = (result, expiry)

    def _invalidate_cache(self, cache_key: str) -> None:
        self._cache.pop(cache_key, None)

    @staticmethod
    def _is_expired(expiry: datetime) -> bool:
        return datetime.now(timezone.utc) >= expiry

    @staticmethod
    def _build_payload(identity: BillingIdentity, context: Optional[BillingContext]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "oauth_provider": identity.oauth_provider,
            "external_id": identity.external_id,
        }
        if identity.wa_id:
            payload["wa_id"] = identity.wa_id
        if identity.tenant_id:
            payload["tenant_id"] = identity.tenant_id
        if context:
            context_data = context.model_dump(exclude_unset=True, exclude_none=True)
            if context_data:
                payload["context"] = context_data
        return payload

    @staticmethod
    def _parse_success(data: Dict[str, Any]) -> BillingCheckResult:
        try:
            return BillingCheckResult(**data)
        except Exception as exc:
            raise ValueError(f"Invalid billing payload: {data}") from exc

    @staticmethod
    def _build_charge_payload(
        identity: BillingIdentity,
        charge: BillingChargeRequest,
        context: Optional[BillingContext],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "oauth_provider": identity.oauth_provider,
            "external_id": identity.external_id,
            "amount_minor": charge.amount_minor,
            "currency": charge.currency,
        }
        if identity.wa_id:
            payload["wa_id"] = identity.wa_id
        if identity.tenant_id:
            payload["tenant_id"] = identity.tenant_id
        if charge.description:
            payload["description"] = charge.description
        if charge.metadata:
            payload["metadata"] = charge.metadata
        if context:
            context_data = context.model_dump(exclude_unset=True, exclude_none=True)
            if context_data:
                payload["context"] = context_data
        return payload

    @staticmethod
    def _parse_charge_success(data: Dict[str, Any]) -> BillingChargeResult:
        try:
            return BillingChargeResult(**data)
        except Exception as exc:
            raise ValueError(f"Invalid billing charge payload: {data}") from exc

    @staticmethod
    def _extract_reason(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body.get("reason") or body.get("detail") or body.get("message") or response.text
        except ValueError:
            return response.text

    def _handle_failure(self, code: str, detail: str) -> BillingCheckResult:
        reason = f"billing_failure:{code}:{detail}"
        if self._fail_open:
            logger.info("Fail-open billing fallback engaged: %s", reason)
            return BillingCheckResult(has_balance=True, reason=reason)
        return BillingCheckResult(has_balance=False, reason=reason)


__all__ = ["UnlimitBillingService"]
