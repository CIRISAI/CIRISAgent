"""
CIRISNode HTTP client for deferral routing and trace forwarding.

Handles HTTP communication with the CIRISNode API including
authentication, retry logic, and error handling.
"""

import logging
import os
from typing import Any, Dict, List, Optional, cast

import httpx

logger = logging.getLogger(__name__)


class CIRISNodeClient:
    """Async HTTP client for CIRISNode API.

    Provides WBD deferral submission/polling, agent event posting,
    and accord trace batch forwarding.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        agent_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.base_url: str = (
            base_url
            or os.getenv("CIRISNODE_BASE_URL", "https://node.ciris-services-1.ai")
            or "https://node.ciris-services-1.ai"
        )
        self.auth_token = auth_token or os.getenv("CIRISNODE_AUTH_TOKEN")
        self.agent_token = agent_token or os.getenv("CIRISNODE_AGENT_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._closed = False

    async def start(self) -> None:
        """Start the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        self._closed = False
        logger.info(f"CIRISNodeClient started, base_url={self.base_url}")

    async def stop(self) -> None:
        """Stop the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._closed = True
        logger.info("CIRISNodeClient stopped")

    def is_closed(self) -> bool:
        return self._closed

    def _get_headers(self, use_agent_token: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if use_agent_token and self.agent_token:
            headers["X-Agent-Token"] = self.agent_token
        elif self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        use_agent_token: bool = False,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        if not self._client:
            raise RuntimeError("Client not started. Call start() first.")

        headers = self._get_headers(use_agent_token)
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    json=json_data,
                    params=params,
                    headers=headers,
                )
                if 400 <= response.status_code < 500:
                    response.raise_for_status()
                response.raise_for_status()
                return cast(Dict[str, Any], response.json())

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise

            except httpx.HTTPStatusError as e:
                if 400 <= e.response.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Request failed with no error")

    # =========================================================================
    # Health
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check CIRISNode health status."""
        return await self._request("GET", "/api/v1/health")

    # =========================================================================
    # WBD (Wisdom-Based Deferral)
    # =========================================================================

    async def wbd_submit(
        self,
        agent_task_id: str,
        payload: str,
        domain_hint: Optional[str] = None,
        signature: Optional[str] = None,
        signature_key_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a signed WBD deferral task for review.

        The deferral must be signed with the agent's Ed25519 key
        (registered via CIRISPortal/CIRISRegistry).
        """
        data: Dict[str, Any] = {"agent_task_id": agent_task_id, "payload": payload}
        if domain_hint:
            data["domain_hint"] = domain_hint
        if signature:
            data["signature"] = signature
        if signature_key_id:
            data["signature_key_id"] = signature_key_id
        return await self._request("POST", "/api/v1/wbd/submit", json_data=data)

    async def wbd_get_task(self, task_id: str) -> Dict[str, Any]:
        """Get a specific WBD task by ID (poll resolution status)."""
        return await self._request("GET", f"/api/v1/wbd/tasks/{task_id}")

    # =========================================================================
    # Agent Events
    # =========================================================================

    async def post_agent_event(self, agent_uid: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Post an agent event for observability."""
        return await self._request(
            "POST",
            "/api/v1/agent/events",
            json_data={"agent_uid": agent_uid, "event": event},
            use_agent_token=True,
        )

    # =========================================================================
    # Accord Trace Events (Lens format)
    # =========================================================================

    async def post_accord_events(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post a batch of Ed25519-signed accord trace events in Lens format.

        Auth: Traces carry inline Ed25519 signatures verified by CIRISNode
        against public keys registered via CIRISPortal/CIRISRegistry.
        No header-based auth required.
        """
        return await self._request(
            "POST",
            "/api/v1/accord/events",
            json_data=payload,
        )

    async def register_public_key(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Register agent's Ed25519 public key with CIRISNode.

        The key is cross-validated against CIRISRegistry if org_id is provided.
        Agent token used if available (optional).
        """
        return await self._request(
            "POST",
            "/api/v1/accord/public-keys",
            json_data=payload,
            use_agent_token=True,
        )

    async def close(self) -> None:
        """Alias for stop()."""
        await self.stop()
