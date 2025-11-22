from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .exceptions import CIRISConnectionError
from .resources.agent import AgentIdentity, AgentResource, AgentStatus, ConversationHistory, InteractResponse
from .resources.audit import AuditResource
from .resources.auth import AuthResource
from .resources.billing import BillingResource
from .resources.config import ConfigResource
from .resources.consent import ConsentResource
from .resources.emergency import EmergencyResource
from .resources.jobs import JobsResource
from .resources.memory import MemoryResource
from .resources.setup import SetupResource
from .resources.system import SystemResource
from .resources.telemetry import TelemetryResource
from .resources.wa import WiseAuthorityResource
from .transport import Transport
from .websocket import EventChannel, WebSocketClient


class CIRISClient:
    """
    Main client for interacting with CIRIS v1 API (Pre-Beta).

    **WARNING**: This SDK is for the v1 API which is in pre-beta stage.
    The API and SDK interfaces may change without notice.
    No backwards compatibility is guaranteed.

    The client provides access to all API resources through a clean, typed interface.
    It handles authentication, retries, and connection management automatically.

    Example:
        async with CIRISClient() as client:
            # Simple interaction
            response = await client.interact("Hello, CIRIS!")
            print(response.response)

            # Get agent status
            status = await client.status()
            print(f"Agent state: {status.cognitive_state}")

    Note: All endpoints are under /v1/ prefix except the emergency shutdown endpoint.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 50.0,  # Increased to support longer processing times
        max_retries: int = 3,
        use_auth_store: bool = True,
        rate_limit: bool = True,
    ):
        """Initialize CIRIS client.

        Args:
            base_url: Base URL of CIRIS API (default: http://localhost:8080)
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds (default: 50.0)
            max_retries: Number of retries for failed requests (default: 3)
            use_auth_store: Whether to use persistent auth storage (default: True)
            rate_limit: Whether to enable client-side rate limiting (default: True)
        """
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_auth_store = use_auth_store
        self.rate_limit = rate_limit
        self._transport = Transport(base_url, api_key, timeout, use_auth_store, rate_limit)

        # Core resources matching v1 API structure
        # Note: Many endpoints have been consolidated in the v1 API
        self.agent = AgentResource(self._transport)
        self.audit = AuditResource(self._transport)
        self.billing = BillingResource(self._transport)  # NEW: Credit and billing management
        self.memory = MemoryResource(self._transport)
        self.system = SystemResource(self._transport)  # NEW: Consolidated system ops
        self.telemetry = TelemetryResource(self._transport)
        self.auth = AuthResource(self._transport)
        self.setup = SetupResource(self._transport)  # NEW: First-run setup wizard
        self.wa = WiseAuthorityResource(self._transport)
        self.config = ConfigResource(self._transport)
        self.consent = ConsentResource(self._transport)  # NEW: Consent management
        self.emergency = EmergencyResource(self._transport)  # NEW: Emergency operations
        self.jobs = JobsResource(self._transport)  # NEW: Async job management

        # Legacy resource references for backwards compatibility
        # These will be removed in future versions
        self.runtime = self.system  # Deprecated: use client.system
        self.visibility = self.telemetry  # Deprecated: use client.telemetry

    async def __aenter__(self) -> "CIRISClient":
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._transport.__aexit__(exc_type, exc, tb)

    def set_api_key(self, api_key: Optional[str], persist: bool = True) -> None:
        """
        Set or update the API key.

        Args:
            api_key: The API key to use (None to clear)
            persist: Whether to store persistently (default: True)
        """
        self.api_key = api_key
        self._transport.set_api_key(api_key, persist)

    def clear_stored_auth(self) -> None:
        """Clear any stored authentication data for this server."""
        if self.use_auth_store and self._transport.auth_store:
            self._transport.auth_store.clear_auth(self.base_url)

    async def _request_with_retry(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(self.max_retries):
            try:
                return await self._transport.request(method, path, **kwargs)
            except CIRISConnectionError:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise

    # Convenience methods for primary agent interactions

    async def interact(self, message: str, context: Optional[Dict[str, Any]] = None) -> InteractResponse:
        """Send message and get response from agent.

        This is the primary method for interacting with the agent.
        It sends your message and waits for the agent's response.

        Args:
            message: Message to send to the agent
            context: Optional context for the interaction

        Returns:
            InteractResponse with the agent's response and metadata

        Example:
            response = await client.interact("What is the weather like?")
            print(response.response)  # Agent's response text
            print(f"Processing took {response.processing_time_ms}ms")
        """
        return await self.agent.interact(message, context)

    async def ask(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Ask a question and get just the response text.

        Convenience method that returns only the response content.

        Args:
            question: Question to ask the agent
            context: Optional context

        Returns:
            Agent's response as a string

        Example:
            answer = await client.ask("What is 2 + 2?")
            print(answer)  # "4"
        """
        return await self.agent.ask(question, context)

    async def history(self, limit: int = 50) -> ConversationHistory:
        """Get conversation history.

        Args:
            limit: Maximum messages to return (1-200)

        Returns:
            ConversationHistory with recent messages
        """
        return await self.agent.get_history(limit)

    async def status(self) -> AgentStatus:
        """Get agent status and cognitive state.

        Returns:
            AgentStatus with current state information
        """
        return await self.agent.get_status()

    def create_websocket(
        self, channels: Optional[List[EventChannel]] = None, reconnect: bool = True, heartbeat_interval: float = 30.0
    ) -> WebSocketClient:
        """
        Create a WebSocket client for real-time streaming.

        The WebSocket client provides real-time updates with:
        - Automatic reconnection on disconnect
        - Channel-based event filtering
        - Health monitoring with heartbeat

        Args:
            channels: List of channels to subscribe to (default: all)
            reconnect: Whether to auto-reconnect (default: True)
            heartbeat_interval: Heartbeat interval in seconds (default: 30)

        Returns:
            WebSocketClient instance

        Example:
            # Create WebSocket for specific channels
            ws = client.create_websocket(channels=[
                EventChannel.AGENT_STATE,
                EventChannel.SYSTEM_HEALTH
            ])

            # Register event handlers
            @ws.on("message")
            async def on_message(data):
                print(f"Received: {data}")

            @ws.on("channel:agent.state")
            async def on_state_change(data):
                print(f"State changed: {data}")

            # Connect and listen
            await ws.connect()

            # Later: close connection
            await ws.close()
        """
        return WebSocketClient(
            base_url=self.base_url,
            api_key=self.api_key,
            channels=channels,
            reconnect=reconnect,
            heartbeat_interval=heartbeat_interval,
            use_auth_store=self.use_auth_store,
        )

    async def identity(self) -> AgentIdentity:
        """Get agent identity and capabilities.

        Returns:
            AgentIdentity with comprehensive identity info
        """
        return await self.agent.get_identity()

    # Authentication helpers

    async def login(self, username: str, password: str) -> None:
        """Login to the API and store authentication token.

        Args:
            username: Username for authentication
            password: Password for authentication
        """
        response = await self.auth.login(username, password)
        self._transport.set_api_key(response.access_token)

    async def logout(self) -> None:
        """Logout and invalidate current token."""
        await self.auth.logout()
        self._transport.set_api_key(None)
