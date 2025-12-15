"""CIRIS Billing-backed credit gate provider for the resource monitor."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import httpx

from ciris_engine.config.ciris_services import get_billing_url
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

    Includes automatic failover to EU fallback (ciris-services-2.ai) on connection errors.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        google_id_token: str = "",
        token_refresh_callback: Optional[Callable[[], str]] = None,
        base_url: Optional[str] = None,
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
            base_url: CIRIS Billing API base URL (defaults to central config)
            timeout_seconds: HTTP request timeout
            cache_ttl_seconds: Credit check cache TTL
            fail_open: If True, allow requests when billing backend is unavailable
            transport: Optional custom HTTP transport for testing
        """
        self._api_key = api_key
        self._google_id_token = google_id_token
        self._token_refresh_callback = token_refresh_callback
        # Use provided URL or get from central config
        self._base_url = (base_url or get_billing_url()).rstrip("/")
        self._fallback_url = get_billing_url(use_fallback=True).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._cache_ttl = max(cache_ttl_seconds, 0)
        self._fail_open = fail_open
        self._transport = transport
        self._using_fallback = False

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
        self._using_fallback = False
        logger.info("CIRISBillingProvider stopped")

    async def _post_with_fallback(
        self, path: str, payload: Dict[str, Any], cache_key: str
    ) -> tuple[httpx.Response | None, str | None]:
        """Make a POST request with automatic fallback to EU region.

        Args:
            path: API path (e.g., "/v1/billing/credits/check")
            payload: JSON payload to send
            cache_key: Cache key for logging

        Returns:
            Tuple of (response, error_type). error_type is a clear category string:
            - "TIMEOUT": Request timed out (tried both regions)
            - "CONNECTION_ERROR": Could not connect (tried both regions)
            - "NETWORK_ERROR": Other network issue
            - None: Success
        """
        assert self._client is not None
        self._refresh_auth_header()

        urls_to_try = self._get_urls_to_try()
        errors_encountered: list[tuple[str, str, str]] = []

        for base_url, region in urls_to_try:
            result = await self._try_single_request(base_url, region, path, payload, cache_key)
            if result[0] is not None:
                # Got a successful response
                return result[0], None
            if result[1] == "FATAL":
                # Fatal error - don't try other URLs
                return None, result[2]
            if result[1] == "RETRY":
                errors_encountered.append((region, result[2], result[3]))

        return self._summarize_errors(errors_encountered, cache_key)

    def _get_urls_to_try(self) -> list[tuple[str, str]]:
        """Get list of (url, region) tuples to try."""
        if self._using_fallback:
            return [(self._fallback_url, "EU-fallback")]
        return [(self._base_url, "US-primary"), (self._fallback_url, "EU-fallback")]

    async def _try_single_request(
        self, base_url: str, region: str, path: str, payload: Dict[str, Any], cache_key: str
    ) -> tuple[httpx.Response | None, str, str, str]:
        """Try a single request to one URL.

        Returns: (response, status, error_type, error_detail)
        - status: "SUCCESS", "RETRY" (try next URL), or "FATAL" (don't retry)
        """
        full_url = f"{base_url}{path}"
        try:
            logger.info("[BILLING] POST %s (%s) for %s", full_url, region, cache_key)
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers=self._client.headers,  # type: ignore[union-attr]
                transport=self._transport,
            ) as client:
                response = await client.post(full_url, json=payload)

            self._update_fallback_state(region)
            return response, "SUCCESS", "", ""

        except (httpx.ConnectTimeout, asyncio.TimeoutError):
            logger.warning("[BILLING] ✗ %s TIMEOUT: %s timed out after %.1fs", region, base_url, self._timeout_seconds)
            return None, "RETRY", "TIMEOUT", f"Timed out after {self._timeout_seconds}s"

        except httpx.ConnectError as exc:
            logger.warning("[BILLING] ✗ %s CONNECTION_ERROR: Cannot reach %s - %s", region, base_url, exc)
            return None, "RETRY", "CONNECTION_ERROR", str(exc)

        except httpx.RequestError as exc:
            error_detail = f"NETWORK_ERROR:{type(exc).__name__}: {exc}"
            logger.error("[BILLING] ✗ %s NETWORK_ERROR: %s - %s", region, base_url, error_detail)
            return None, "FATAL", error_detail, ""

    def _update_fallback_state(self, region: str) -> None:
        """Update fallback state based on which region succeeded."""
        if "fallback" in region and not self._using_fallback:
            logger.info("[BILLING] ✓ Switched to %s: %s", region, self._fallback_url)
            self._using_fallback = True
        elif "primary" in region and self._using_fallback:
            logger.info("[BILLING] ✓ Recovered to %s: %s", region, self._base_url)
            self._using_fallback = False
        else:
            logger.info("[BILLING] ✓ Request succeeded via %s", region)

    def _summarize_errors(self, errors: list[tuple[str, str, str]], cache_key: str) -> tuple[None, str]:
        """Summarize errors from all failed attempts."""
        if not errors:
            return None, "UNKNOWN_ERROR:No URLs configured"

        error_types = {e[1] for e in errors}
        regions_tried = [e[0] for e in errors]

        if error_types == {"TIMEOUT"}:
            error_summary = f"TIMEOUT:All regions timed out ({', '.join(regions_tried)})"
        elif error_types == {"CONNECTION_ERROR"}:
            error_summary = f"CONNECTION_ERROR:Cannot reach any region ({', '.join(regions_tried)})"
        else:
            error_summary = f"MULTI_ERROR:{'; '.join(f'{e[0]}={e[1]}' for e in errors)}"

        logger.error(
            "[BILLING] ✗ ALL REGIONS FAILED for %s:\n%s",
            cache_key,
            "\n".join(f"  - {e[0]}: {e[1]} - {e[2]}" for e in errors),
        )
        return None, error_summary

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        if not account.provider or not account.account_id:
            raise ValueError("Credit account must include provider and account_id")

        await self._ensure_started()

        cache_key = account.cache_key()
        cached_result = self._get_cached_check(cache_key)
        if cached_result:
            return cached_result

        payload = self._build_check_payload(account, context)
        logger.debug("Credit check payload for %s: %s", cache_key, payload)

        response, error_type = await self._post_with_fallback("/v1/billing/credits/check", payload, cache_key)

        if error_type:
            return self._handle_check_network_error(error_type, cache_key)

        assert response is not None
        return self._handle_check_response(response, cache_key)

    def _get_cached_check(self, cache_key: str) -> CreditCheckResult | None:
        """Return cached result if valid, None otherwise."""
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
        return None

    def _handle_check_network_error(self, error_type: str, cache_key: str) -> CreditCheckResult:
        """Handle network errors from check_credit."""
        error_category = error_type.split(":")[0] if ":" in error_type else error_type
        logger.error("[CREDIT_CHECK] ✗ %s for %s - %s", error_category, cache_key, error_type)
        return self._handle_failure(error_category, error_type)

    def _handle_check_response(self, response: httpx.Response, cache_key: str) -> CreditCheckResult:
        """Handle HTTP response from check_credit."""
        if response.status_code == httpx.codes.OK:
            return self._handle_check_success(response, cache_key)

        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            return self._handle_check_no_credits(response, cache_key)

        if response.status_code == httpx.codes.UNAUTHORIZED:
            return self._handle_check_unauthorized(response, cache_key)

        return self._handle_check_unexpected(response, cache_key)

    def _handle_check_success(self, response: httpx.Response, cache_key: str) -> CreditCheckResult:
        """Handle successful credit check response."""
        response_data = response.json()
        has_credit = response_data.get("has_credit", False)
        free_remaining = response_data.get("free_uses_remaining", 0)
        credits_remaining = response_data.get("credits_remaining", 0)

        if has_credit:
            logger.info(
                "[CREDIT_CHECK] ✓ HAS_CREDIT for %s: free=%s, paid=%s", cache_key, free_remaining, credits_remaining
            )
        else:
            logger.warning(
                "[CREDIT_CHECK] ✗ NO_CREDITS for %s: free=%s, paid=%s (exhausted)",
                cache_key,
                free_remaining,
                credits_remaining,
            )

        result = self._parse_check_success(response_data)
        self._store_cache(cache_key, result)
        return result

    def _handle_check_no_credits(self, response: httpx.Response, cache_key: str) -> CreditCheckResult:
        """Handle payment required or forbidden response."""
        reason = self._extract_reason(response)
        logger.warning("[CREDIT_CHECK] ✗ NO_CREDITS for %s (HTTP %d): %s", cache_key, response.status_code, reason)
        result = CreditCheckResult(has_credit=False, reason=f"NO_CREDITS:{reason}")
        self._store_cache(cache_key, result)
        return result

    def _handle_check_unauthorized(self, response: httpx.Response, cache_key: str) -> CreditCheckResult:
        """Handle 401 Unauthorized response."""
        reason = self._extract_reason(response)
        token_preview = self._google_id_token[:20] + "..." if self._google_id_token else "None"
        logger.error(
            "[CREDIT_CHECK] ✗ AUTH_EXPIRED for %s:\n"
            "  HTTP Status: 401 Unauthorized\n"
            "  Reason: %s\n"
            "  Token: %s (%d chars)\n"
            "  Action: Writing .token_refresh_needed signal",
            cache_key,
            reason,
            token_preview,
            len(self._google_id_token) if self._google_id_token else 0,
        )
        self._signal_token_refresh_needed()
        return self._handle_failure("AUTH_EXPIRED", reason)

    def _handle_check_unexpected(self, response: httpx.Response, cache_key: str) -> CreditCheckResult:
        """Handle unexpected HTTP status codes."""
        reason = self._extract_reason(response)
        logger.error("[CREDIT_CHECK] ✗ UNEXPECTED_ERROR for %s: HTTP %d - %s", cache_key, response.status_code, reason)
        return self._handle_failure(f"HTTP_{response.status_code}", reason)

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

        response, error_type = await self._post_with_fallback("/v1/billing/charges", payload, cache_key)

        if error_type:
            # Clear categorization of network errors
            if error_type.startswith("TIMEOUT"):
                logger.error(
                    "[CREDIT_SPEND] ✗ TIMEOUT for %s - billing service unreachable",
                    cache_key,
                )
                return CreditSpendResult(succeeded=False, reason=f"TIMEOUT:{error_type}")
            elif error_type.startswith("CONNECTION_ERROR"):
                logger.error(
                    "[CREDIT_SPEND] ✗ CONNECTION_ERROR for %s - cannot connect to billing",
                    cache_key,
                )
                return CreditSpendResult(succeeded=False, reason=f"CONNECTION_ERROR:{error_type}")
            else:
                logger.error(
                    "[CREDIT_SPEND] ✗ NETWORK_ERROR for %s - %s",
                    cache_key,
                    error_type,
                )
                return CreditSpendResult(succeeded=False, reason=f"NETWORK_ERROR:{error_type}")

        assert response is not None

        # Handle successful charge
        if response.status_code in {httpx.codes.OK, httpx.codes.CREATED}:
            response_data = response.json()
            charge_id = response_data.get("charge_id")
            balance_after = response_data.get("balance_after")
            logger.info(
                "[CREDIT_SPEND] ✓ CHARGE_SUCCESS for %s: charge_id=%s, balance_after=%s",
                cache_key,
                charge_id,
                balance_after,
            )
            result = self._parse_spend_success(response_data)
            self._invalidate_cache(cache_key)
            return result

        # Handle idempotency conflict - charge already recorded (this is success)
        if response.status_code == httpx.codes.CONFLICT:
            existing_charge_id = response.headers.get("X-Existing-Charge-ID")
            logger.info(
                "[CREDIT_SPEND] ✓ ALREADY_CHARGED for %s (idempotency): charge_id=%s",
                cache_key,
                existing_charge_id,
            )
            return CreditSpendResult(
                succeeded=True,
                transaction_id=existing_charge_id,
                reason="ALREADY_CHARGED:idempotency",
            )

        # Handle insufficient credits
        if response.status_code in {httpx.codes.PAYMENT_REQUIRED, httpx.codes.FORBIDDEN}:
            reason = self._extract_reason(response)
            logger.warning(
                "[CREDIT_SPEND] ✗ INSUFFICIENT_CREDITS for %s (HTTP %d): %s",
                cache_key,
                response.status_code,
                reason,
            )
            self._invalidate_cache(cache_key)
            return CreditSpendResult(succeeded=False, reason=f"INSUFFICIENT_CREDITS:{reason}")

        # Handle auth errors
        if response.status_code == httpx.codes.UNAUTHORIZED:
            reason = self._extract_reason(response)
            logger.error(
                "[CREDIT_SPEND] ✗ AUTH_EXPIRED for %s: %s",
                cache_key,
                reason,
            )
            self._signal_token_refresh_needed()
            return CreditSpendResult(succeeded=False, reason=f"AUTH_EXPIRED:{reason}")

        # Handle other unexpected responses
        reason = self._extract_reason(response)
        logger.error(
            "[CREDIT_SPEND] ✗ UNEXPECTED_ERROR for %s: HTTP %d - %s",
            cache_key,
            response.status_code,
            reason,
        )
        return CreditSpendResult(
            succeeded=False,
            reason=f"HTTP_{response.status_code}:{reason}",
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

    def _handle_failure(self, error_category: str, detail: str) -> CreditCheckResult:
        """Handle a billing failure and return appropriate CreditCheckResult.

        Error categories:
        - TIMEOUT: Billing service unreachable (tried all regions)
        - CONNECTION_ERROR: Cannot connect to billing service
        - NETWORK_ERROR: Other network issues
        - AUTH_EXPIRED: Token expired, needs refresh
        - NO_CREDITS: User has no credits available
        - HTTP_xxx: Unexpected HTTP status code
        """
        reason = f"{error_category}:{detail}"
        if self._fail_open:
            logger.warning(
                "[BILLING] FAIL_OPEN engaged - allowing request despite error: %s",
                reason,
            )
            return CreditCheckResult(has_credit=True, reason=f"FAIL_OPEN:{reason}")
        return CreditCheckResult(has_credit=False, reason=reason)


__all__ = ["CIRISBillingProvider"]
