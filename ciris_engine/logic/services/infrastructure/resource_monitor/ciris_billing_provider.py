"""CIRIS Billing-backed credit gate provider for the resource monitor."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

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


class CIRISBillingProvider(CreditGateProtocol):
    """Async credit provider that gates interactions via self-hosted CIRIS Billing API.

    Supports two auth modes:
    1. API Key auth (server-to-server): Uses X-API-Key header
    2. JWT auth (Android/mobile): Uses Authorization: Bearer {google_id_token}
       - Token is refreshed automatically via token_refresh_callback
       - Format matches CIRIS LLM proxy: Bearer google:{user_id} or raw ID token
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        google_id_token: str = "",
        token_refresh_callback: Optional[Callable[[], str]] = None,
        base_url: str = "https://billing.ciris.ai",
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: int = 15,
        fail_open: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize CIRIS Billing Provider.

        Args:
            api_key: API key for server-to-server auth (uses X-API-Key header)
            google_id_token: Google ID token for JWT auth (uses Authorization: Bearer)
            token_refresh_callback: Optional callback to refresh google_id_token when expired
            base_url: CIRIS Billing API base URL
            timeout_seconds: HTTP request timeout
            cache_ttl_seconds: Credit check cache TTL
            fail_open: If True, allow requests when billing backend is unavailable
            transport: Optional custom HTTP transport for testing
        """
        self._api_key = api_key
        self._google_id_token = google_id_token
        self._token_refresh_callback = token_refresh_callback
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._cache_ttl = max(cache_ttl_seconds, 0)
        self._fail_open = fail_open
        self._transport = transport

        # Determine auth mode
        self._use_jwt_auth = bool(google_id_token)

        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._cache: dict[str, tuple[CreditCheckResult, datetime]] = {}

    def _get_current_token(self) -> str:
        """Get the current Google ID token, checking environment for updates.

        Token refresh flow:
        1. Billing request fails with 401 → writes .token_refresh_needed
        2. Android detects signal, refreshes Google token silently
        3. Android updates .env with new GOOGLE_ID_TOKEN
        4. Android writes .config_reload signal
        5. ResourceMonitor reloads .env (via load_dotenv override=True)
        6. This method reads the updated GOOGLE_ID_TOKEN from environment
        """
        # First, try the callback if available
        if self._token_refresh_callback:
            try:
                new_token = self._token_refresh_callback()
                if new_token and new_token != self._google_id_token:
                    old_preview = self._google_id_token[:20] + "..." if self._google_id_token else "None"
                    new_preview = new_token[:20] + "..."
                    logger.info("[BILLING_TOKEN] Token refreshed via callback: %s -> %s", old_preview, new_preview)
                    self._google_id_token = new_token
                    return self._google_id_token
            except Exception as exc:
                logger.warning("[BILLING_TOKEN] Token refresh callback failed: %s", exc)

        # Check environment for updated token (set by ResourceMonitor after .env reload)
        env_token = os.environ.get("GOOGLE_ID_TOKEN", "")
        if env_token and env_token != self._google_id_token:
            old_preview = self._google_id_token[:20] + "..." if self._google_id_token else "None"
            new_preview = env_token[:20] + "..."
            logger.info("[BILLING_TOKEN] Token updated from environment: %s -> %s", old_preview, new_preview)
            self._google_id_token = env_token

        return self._google_id_token

    def _build_auth_headers(self) -> dict[str, str]:
        """Build authentication headers based on auth mode."""
        headers = {"User-Agent": "CIRIS-Agent-CreditGate/1.0"}

        if self._use_jwt_auth:
            # JWT auth mode (Android/mobile) - use Authorization: Bearer
            token = self._get_current_token()
            headers["Authorization"] = f"Bearer {token}"
            logger.debug("Using JWT auth mode with Google ID token")
        else:
            # API key auth mode (server-to-server)
            headers["X-API-Key"] = self._api_key
            logger.debug("Using API key auth mode")

        return headers

    def update_google_id_token(self, token: str) -> None:
        """Update the Google ID token (for token refresh).

        This is called when the Android app refreshes its Google ID token.
        The next request will use the new token.
        """
        self._google_id_token = token
        self._use_jwt_auth = True
        logger.info("Updated Google ID token for billing auth")

    async def start(self) -> None:
        async with self._client_lock:
            if self._client is not None:
                return
            headers = self._build_auth_headers()
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers=headers,
                transport=self._transport,
            )
            auth_mode = "JWT (Google ID token)" if self._use_jwt_auth else "API Key"
            token_preview = self._google_id_token[:20] + "..." if self._google_id_token else "None"
            logger.info(
                "[BILLING_PROVIDER] Started:\n"
                "  base_url: %s\n"
                "  auth_mode: %s\n"
                "  token_preview: %s\n"
                "  token_length: %d\n"
                "  has_refresh_callback: %s\n"
                "  cache_ttl: %ds\n"
                "  fail_open: %s",
                self._base_url,
                auth_mode,
                token_preview,
                len(self._google_id_token) if self._google_id_token else 0,
                self._token_refresh_callback is not None,
                self._cache_ttl,
                self._fail_open,
            )

    async def stop(self) -> None:
        async with self._client_lock:
            client, self._client = self._client, None
        if client:
            await client.aclose()
        self._cache.clear()
        logger.info("CIRISBillingProvider stopped")

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
            logger.info(
                "[CREDIT_CHECK] CACHE HIT for %s: free_uses=%s, credits=%s, has_credit=%s (expires in %ss)",
                cache_key,
                cached[0].free_uses_remaining,
                cached[0].credits_remaining,
                cached[0].has_credit,
                int((cached[1] - datetime.now(timezone.utc)).total_seconds()),
            )
            return cached[0].model_copy()

        if cached:
            logger.debug("[CREDIT_CHECK] Cache expired for %s - querying backend", cache_key)
        else:
            logger.debug("[CREDIT_CHECK] No cache for %s - querying backend", cache_key)

        payload = self._build_check_payload(account, context)
        logger.debug("Credit check payload for %s: %s", cache_key, payload)

        try:
            assert self._client is not None  # nosec - ensured by _ensure_started
            # Refresh auth header before request (for JWT mode token refresh)
            self._refresh_auth_header()

            # Both JWT and API key modes need oauth_provider and external_id in body
            # JWT provides authentication, but account identity still comes from payload
            logger.info(
                "Sending credit check to %s/v1/billing/credits/check (auth=%s, payload=%s)",
                self._base_url,
                "JWT" if self._use_jwt_auth else "API_KEY",
                payload,
            )
            response = await self._client.post("/v1/billing/credits/check", json=payload)

            logger.info("Credit response status=%s", response.status_code)
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.error("Credit request failed for %s: %s (%s)", cache_key, type(exc).__name__, exc, exc_info=True)
            return self._handle_failure("request_error", str(exc))

        if response.status_code == httpx.codes.OK:
            response_data = response.json()
            # Both JWT and API key modes return same response format now
            logger.info(
                "[CREDIT_CHECK] Backend response for %s: free_uses=%s, credits=%s, has_credit=%s, daily_free=%s",
                cache_key,
                response_data.get("free_uses_remaining"),
                response_data.get("credits_remaining"),
                response_data.get("has_credit"),
                response_data.get("daily_free_uses_remaining"),
            )
            result = self._parse_check_success(response_data)
            self._store_cache(cache_key, result)
            return result

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            logger.info("[CREDIT_CHECK] No credit available for %s: %s", cache_key, reason)
            result = CreditCheckResult(has_credit=False, reason=reason)
            self._store_cache(cache_key, result)
            return result

        # Handle 401 Unauthorized - likely token expired
        if response.status_code == httpx.codes.UNAUTHORIZED:
            reason = self._extract_reason(response)
            token_preview = self._google_id_token[:20] + "..." if self._google_id_token else "None"
            logger.error(
                "[CREDIT_CHECK] 401 Unauthorized for %s - TOKEN LIKELY EXPIRED\n"
                "  Reason: %s\n"
                "  Token preview: %s\n"
                "  Token length: %d\n"
                "  Has refresh callback: %s\n"
                "  Writing .token_refresh_needed signal for Android...",
                cache_key,
                reason,
                token_preview,
                len(self._google_id_token) if self._google_id_token else 0,
                self._token_refresh_callback is not None,
            )
            # Write signal file for Android to trigger token refresh
            self._signal_token_refresh_needed()
            return self._handle_failure("token_expired", reason)

        reason = self._extract_reason(response)
        logger.warning(
            "[CREDIT_CHECK] Unexpected response for %s: status=%s reason=%s",
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
            # Refresh auth header before request (for JWT mode token refresh)
            self._refresh_auth_header()
            response = await self._client.post("/v1/billing/charges", json=payload)
            logger.debug("Credit spend response for %s: status=%s", cache_key, response.status_code)
        except (httpx.RequestError, asyncio.TimeoutError) as exc:
            logger.warning("Credit spend request failed for %s: %s", cache_key, exc)
            return CreditSpendResult(succeeded=False, reason=f"charge_failure:request_error:{exc}")

        if response.status_code in {httpx.codes.OK, httpx.codes.CREATED}:
            response_data = response.json()
            logger.info(
                "[CREDIT_SPEND] Charge successful for %s: charge_id=%s, balance_after=%s",
                cache_key,
                response_data.get("charge_id"),
                response_data.get("balance_after"),
            )
            result = self._parse_spend_success(response_data)
            logger.debug("[CREDIT_SPEND] Cache invalidated for %s - next check will hit backend", cache_key)
            self._invalidate_cache(cache_key)
            return result

        if response.status_code == httpx.codes.CONFLICT:
            # Idempotency conflict - charge already exists
            logger.info("Idempotency conflict for %s - charge already recorded", cache_key)
            # Extract existing charge info from response if available
            existing_charge_id = response.headers.get("X-Existing-Charge-ID")
            return CreditSpendResult(
                succeeded=True,
                transaction_id=existing_charge_id,
                reason="charge_already_exists:idempotency",
            )

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

    def _refresh_auth_header(self) -> None:
        """Refresh the Authorization header if in JWT mode.

        This is called before each request to ensure the token is fresh.
        For API key mode, this is a no-op since API keys don't expire.
        """
        if not self._use_jwt_auth or self._client is None:
            return

        # Get fresh token (may call refresh callback)
        token = self._get_current_token()
        if token:
            self._client.headers["Authorization"] = f"Bearer {token}"

    def _signal_token_refresh_needed(self) -> None:
        """Write a signal file to indicate token refresh is needed.

        This is picked up by Android's TokenRefreshManager which will:
        1. Call Google silentSignIn() to get a fresh ID token
        2. Update .env with the new token
        3. Write .config_reload signal
        4. Python ResourceMonitor detects .config_reload and emits token_refreshed
        """
        import time
        from pathlib import Path

        # Get CIRIS_HOME
        ciris_home = os.environ.get("CIRIS_HOME")
        if not ciris_home:
            try:
                from ciris_engine.logic.utils.path_resolution import get_ciris_home

                ciris_home = str(get_ciris_home())
            except Exception:
                logger.warning("[BILLING_TOKEN] Cannot write refresh signal - CIRIS_HOME not found")
                return

        try:
            signal_file = Path(ciris_home) / ".token_refresh_needed"
            signal_file.write_text(str(time.time()))
            logger.info("[BILLING_TOKEN] Token refresh signal written to: %s", signal_file)
        except Exception as exc:
            logger.warning("[BILLING_TOKEN] Failed to write token refresh signal: %s", exc)

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
    def _extract_context_fields(context: CreditContext, payload: dict[str, object]) -> None:
        """Extract billing-specific fields from context into payload.

        Args:
            context: Credit context containing agent_id
            payload: Payload dict to update with extracted fields
        """
        # Note: context.metadata has been removed to match billing backend schema
        # customer_email, user_role, and marketing_opt_in are now passed directly
        # in the identity dict from the calling code (billing.py)

        # Add agent_id as top-level field (billing expects this)
        if context.agent_id:
            payload["agent_id"] = context.agent_id

    @staticmethod
    def _build_check_payload(
        account: CreditAccount,
        context: CreditContext | None,
    ) -> dict[str, object]:
        # Add oauth: prefix if not already present
        provider = account.provider if account.provider.startswith("oauth:") else f"oauth:{account.provider}"

        payload: dict[str, object] = {
            "oauth_provider": provider,
            "external_id": account.account_id,
            # Note: amount_minor removed - /credits/check doesn't accept it
        }
        if account.authority_id:
            payload["wa_id"] = account.authority_id
        if account.tenant_id:
            payload["tenant_id"] = account.tenant_id

        # Add customer_email and marketing_opt_in from CreditAccount
        if account.customer_email:
            payload["customer_email"] = account.customer_email
        if account.marketing_opt_in is not None:
            payload["marketing_opt_in"] = account.marketing_opt_in

        if context:
            # Extract billing-specific fields from metadata
            CIRISBillingProvider._extract_context_fields(context, payload)

            # Add user_role from context
            if context.user_role:
                payload["user_role"] = context.user_role

            # Only include remaining context fields
            context_dict = {}
            if context.channel_id:
                context_dict["channel_id"] = context.channel_id
            if context.request_id:
                context_dict["request_id"] = context.request_id
            if context_dict:
                payload["context"] = context_dict
        return payload

    @staticmethod
    def _build_spend_payload(
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None,
    ) -> dict[str, object]:
        # Add oauth: prefix if not already present
        provider = account.provider if account.provider.startswith("oauth:") else f"oauth:{account.provider}"

        # Generate idempotency key from request metadata or create one
        idempotency_key = request.metadata.get("idempotency_key") if request.metadata else None
        if not idempotency_key:
            # Create idempotency key from account + timestamp + amount
            import hashlib
            import time

            key_data = f"{account.provider}:{account.account_id}:{int(time.time())}:{request.amount_minor}"
            idempotency_key = f"charge_{hashlib.sha256(key_data.encode()).hexdigest()[:16]}"

        payload: dict[str, object] = {
            "oauth_provider": provider,
            "external_id": account.account_id,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "idempotency_key": idempotency_key,
        }
        if account.authority_id:
            payload["wa_id"] = account.authority_id
        if account.tenant_id:
            payload["tenant_id"] = account.tenant_id
        if request.description:
            payload["description"] = request.description

        # Add customer_email and marketing_opt_in from CreditAccount
        if account.customer_email:
            payload["customer_email"] = account.customer_email
        if account.marketing_opt_in is not None:
            payload["marketing_opt_in"] = account.marketing_opt_in

        # Extract billing-specific fields from context metadata (same as check_credit)
        if context:
            CIRISBillingProvider._extract_context_fields(context, payload)

            # Add user_role from context
            if context.user_role:
                payload["user_role"] = context.user_role

        # Include request metadata (excluding billing fields that are now top-level)
        if request.metadata:
            # Remove idempotency_key from metadata since it's in the top level
            metadata = {k: v for k, v in request.metadata.items() if k != "idempotency_key"}
            if metadata:
                payload["metadata"] = metadata
        return payload

    @staticmethod
    def _parse_check_success(data: dict[str, object]) -> CreditCheckResult:
        try:
            # CIRIS Billing returns additional fields:
            # - free_uses_remaining
            # - total_uses
            # - purchase_required
            # - purchase_price_minor
            # - purchase_uses
            return CreditCheckResult(**data)
        except Exception as exc:
            raise ValueError(f"Invalid credit payload: {data}") from exc

    @staticmethod
    def _parse_spend_success(data: dict[str, object]) -> CreditSpendResult:
        try:
            # Map CIRIS Billing response to CreditSpendResult
            # charge_id → transaction_id
            # balance_after → balance_remaining
            result_data = {
                "succeeded": True,
                "transaction_id": data.get("charge_id"),
                "balance_remaining": data.get("balance_after"),
                "reason": None,
                "provider_metadata": {
                    k: str(v) for k, v in data.items() if k not in {"succeeded", "transaction_id", "balance_remaining"}
                },
            }
            return CreditSpendResult(**result_data)
        except Exception as exc:
            raise ValueError(f"Invalid credit spend payload: {data}") from exc

    @staticmethod
    def _extract_reason(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                value = body.get("detail") or body.get("reason") or body.get("message") or body.get("error")
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


__all__ = ["CIRISBillingProvider"]
