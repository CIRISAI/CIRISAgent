"""Unlimit-backed credit gate provider for the resource monitor."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ciris_engine.protocols.services.infrastructure.credit_gate import CreditGateProtocol
from ciris_engine.schemas.services.credit_gate import (
    CreditAccount,
    CreditCheckResult,
    CreditContext,
    CreditSpendRequest,
    CreditSpendResult,
)

logger = logging.getLogger(__name__)


class UnlimitCreditProvider(CreditGateProtocol):
    """Async credit provider that gates interactions via Unlimit."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.unlimit.com",
        api_key: str | None = None,
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

        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._cache: dict[str, tuple[CreditCheckResult, datetime]] = {}

    async def start(self) -> None:
        async with self._client_lock:
            if self._client is not None:
                return
            headers = {"User-Agent": "CIRIS-Unlimit-CreditGate/0.1"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers=headers,
                transport=self._transport,
            )
            logger.info("UnlimitCreditProvider started with base_url=%s", self._base_url)

    async def stop(self) -> None:
        async with self._client_lock:
            client, self._client = self._client, None
        if client:
            await client.aclose()
        self._cache.clear()
        logger.info("UnlimitCreditProvider stopped")

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        if not account.provider or not account.account_id:
            raise ValueError("Credit account must include provider and account_id")

        await self._ensure_started()

        cache_key = account.cache_key()
        cached = self._cache.get(cache_key)
        if cached and not self._is_expired(cached[1]):
            logger.debug("Credit cache hit for %s", cache_key)
            return cached[0].model_copy()

        payload = self._build_payload(account, context)
        logger.debug("Credit check payload for %s: %s", cache_key, payload)

        try:
            assert self._client is not None  # nosec - ensured by _ensure_started
            response = await self._client.post("/v1/billing/credits/check", json=payload)
            logger.debug("Credit response status=%s", response.status_code)
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.warning("Credit request failed for %s: %s", cache_key, exc)
            return self._handle_failure("request_error", str(exc))

        if response.status_code == httpx.codes.OK:
            result = self._parse_check_success(response.json())
            self._store_cache(cache_key, result)
            return result

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            result = CreditCheckResult(has_credit=False, reason=reason)
            self._store_cache(cache_key, result)
            return result

        reason = self._extract_reason(response)
        logger.warning(
            "Unexpected credit response for %s: status=%s reason=%s",
            cache_key,
            response.status_code,
            reason,
        )
        return self._handle_failure(f"unexpected_status_{response.status_code}", reason)

    async def spend_credit(
        self,
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None = None,
    ) -> CreditSpendResult:
        if request.amount_minor <= 0:
            raise ValueError("Spend amount must be positive")

        await self._ensure_started()

        payload = self._build_spend_payload(account, request, context)
        cache_key = account.cache_key()
        logger.debug("Credit spend payload for %s: %s", cache_key, payload)

        try:
            assert self._client is not None
            response = await self._client.post("/v1/billing/charges", json=payload)
            logger.debug("Credit spend response for %s: status=%s", cache_key, response.status_code)
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.warning("Credit spend request failed for %s: %s", cache_key, exc)
            return CreditSpendResult(succeeded=False, reason=f"charge_failure:request_error:{exc}")

        if response.status_code in {httpx.codes.OK, httpx.codes.CREATED}:
            result = self._parse_spend_success(response.json())
            self._invalidate_cache(cache_key)
            return result

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            self._invalidate_cache(cache_key)
            return CreditSpendResult(succeeded=False, reason=reason)

        reason = self._extract_reason(response)
        logger.warning(
            "Unexpected credit spend response for %s: status=%s reason=%s",
            cache_key,
            response.status_code,
            reason,
        )
        return CreditSpendResult(
            succeeded=False,
            reason=f"charge_failure:unexpected_status_{response.status_code}:{reason}",
        )

    async def _ensure_started(self) -> None:
        if self._client is not None:
            return
        await self.start()

    def _store_cache(self, cache_key: str, result: CreditCheckResult) -> None:
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
    def _build_payload(
        account: CreditAccount,
        context: CreditContext | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "oauth_provider": account.provider,
            "external_id": account.account_id,
        }
        if account.authority_id:
            payload["wa_id"] = account.authority_id
        if account.tenant_id:
            payload["tenant_id"] = account.tenant_id
        if context:
            context_data = context.model_dump(exclude_unset=True, exclude_none=True)
            if context_data:
                payload["context"] = context_data
        return payload

    @staticmethod
    def _build_spend_payload(
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "oauth_provider": account.provider,
            "external_id": account.account_id,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
        }
        if account.authority_id:
            payload["wa_id"] = account.authority_id
        if account.tenant_id:
            payload["tenant_id"] = account.tenant_id
        if request.description:
            payload["description"] = request.description
        if request.metadata:
            payload["metadata"] = request.metadata
        if context:
            context_data = context.model_dump(exclude_unset=True, exclude_none=True)
            if context_data:
                payload["context"] = context_data
        return payload

    @staticmethod
    def _parse_check_success(data: dict[str, object]) -> CreditCheckResult:
        try:
            # Accept legacy providers that return `has_balance`
            if "has_balance" in data and "has_credit" not in data:
                data = {**data, "has_credit": data.get("has_balance")}
            return CreditCheckResult(**data)
        except Exception as exc:
            raise ValueError(f"Invalid credit payload: {data}") from exc

    @staticmethod
    def _parse_spend_success(data: dict[str, object]) -> CreditSpendResult:
        try:
            return CreditSpendResult(**data)
        except Exception as exc:
            raise ValueError(f"Invalid credit spend payload: {data}") from exc

    @staticmethod
    def _extract_reason(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                value = body.get("reason") or body.get("detail") or body.get("message") or body.get("error")
                if isinstance(value, str) and value:
                    return value
            return response.text
        except ValueError:
            return response.text

    def _handle_failure(self, code: str, detail: str) -> CreditCheckResult:
        reason = f"credit_failure:{code}:{detail}"
        if self._fail_open:
            logger.info("Fail-open credit fallback engaged: %s", reason)
            return CreditCheckResult(has_credit=True, reason=reason)
        return CreditCheckResult(has_credit=False, reason=reason)


__all__ = ["UnlimitCreditProvider"]
