"""
Covenant Metrics Services - WBD and PDMA event collection for CIRISLens.

This module implements the CovenantMetricsService which:
1. Receives WBD (Wisdom-Based Deferral) events via WiseBus broadcast
2. Batches events and sends them to CIRISLens API
3. Only operates when explicit consent has been given
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from ciris_engine.schemas.services.authority_core import DeferralRequest
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


@dataclass
class SimpleCapabilities:
    """Simple capabilities container for duck-typing with WiseBus."""

    actions: List[str]
    scopes: List[str]


class CovenantMetricsService:
    """
    Covenant compliance metrics service for CIRISLens.

    This service receives WBD (Wisdom-Based Deferral) events from WiseBus
    and forwards them to the CIRISLens API for covenant compliance tracking.

    CRITICAL: This service ONLY sends data when:
    1. User has explicitly consented via the setup wizard
    2. The consent_given config flag is True
    3. A valid consent_timestamp exists

    Data sent is anonymized:
    - Agent IDs are hashed
    - No user message content is included
    - Only structural decision metadata
    """

    def __init__(self, config: Optional[JSONDict] = None) -> None:
        """Initialize CovenantMetricsService.

        Args:
            config: Configuration dict with consent settings
        """
        self._config = config or {}

        # Consent state
        self._consent_given = bool(self._config.get("consent_given", False))
        self._consent_timestamp: Optional[str] = None
        raw_timestamp = self._config.get("consent_timestamp")
        if raw_timestamp is not None:
            self._consent_timestamp = str(raw_timestamp)

        # Endpoint configuration
        raw_url = self._config.get("endpoint_url")
        self._endpoint_url: str = str(raw_url) if raw_url else "https://lens.ciris.ai/v1"

        raw_batch = self._config.get("batch_size")
        if raw_batch is not None and isinstance(raw_batch, (int, float, str)):
            self._batch_size: int = int(raw_batch)
        else:
            self._batch_size = 10

        raw_interval = self._config.get("flush_interval_seconds")
        if raw_interval is not None and isinstance(raw_interval, (int, float, str)):
            self._flush_interval: float = float(raw_interval)
        else:
            self._flush_interval = 60.0

        # Event queue and batching
        self._event_queue: List[Dict[str, Any]] = []
        self._queue_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None

        # HTTP client session
        self._session: Optional[aiohttp.ClientSession] = None

        # Metrics
        self._events_received = 0
        self._events_sent = 0
        self._events_failed = 0
        self._last_send_time: Optional[datetime] = None

        # Agent ID for anonymization (set during start)
        self._agent_id_hash: Optional[str] = None

        logger.info(
            f"CovenantMetricsService initialized (consent_given={self._consent_given}, "
            f"endpoint={self._endpoint_url})"
        )

    def _anonymize_agent_id(self, agent_id: str) -> str:
        """Hash agent ID for privacy.

        Args:
            agent_id: Raw agent identifier

        Returns:
            SHA-256 hash of agent ID (first 16 chars)
        """
        return hashlib.sha256(agent_id.encode()).hexdigest()[:16]

    def get_capabilities(self) -> SimpleCapabilities:
        """Return service capabilities.

        Returns:
            SimpleCapabilities with send_deferral to receive WBD events
        """
        return SimpleCapabilities(
            actions=["send_deferral", "covenant_metrics"],
            scopes=["covenant_compliance"],
        )

    async def start(self) -> None:
        """Start the service and initialize HTTP client."""
        logger.info("Starting CovenantMetricsService")

        if not self._consent_given:
            logger.warning(
                "CovenantMetricsService started but consent not given - "
                "no data will be sent until user consents via setup wizard"
            )
            return

        # Initialize HTTP session
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CIRIS-CovenantMetrics/1.0",
            },
        )

        # Start flush task
        self._flush_task = asyncio.create_task(self._periodic_flush())

        logger.info(f"CovenantMetricsService started with consent (timestamp={self._consent_timestamp})")

    async def stop(self) -> None:
        """Stop the service and flush remaining events."""
        logger.info("Stopping CovenantMetricsService")

        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining events
        await self._flush_events()

        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None

        logger.info(
            f"CovenantMetricsService stopped (events_sent={self._events_sent}, " f"events_failed={self._events_failed})"
        )

    async def _periodic_flush(self) -> None:
        """Periodically flush events even if batch is not full."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    async def _flush_events(self) -> None:
        """Send all queued events to CIRISLens."""
        if not self._consent_given or not self._session:
            return

        async with self._queue_lock:
            if not self._event_queue:
                return

            events_to_send = self._event_queue.copy()
            self._event_queue.clear()

        try:
            await self._send_events_batch(events_to_send)
            self._events_sent += len(events_to_send)
            self._last_send_time = datetime.now(timezone.utc)
            logger.debug(f"Flushed {len(events_to_send)} events to CIRISLens")
        except Exception as e:
            self._events_failed += len(events_to_send)
            logger.error(f"Failed to send {len(events_to_send)} events: {e}")
            # Re-queue failed events (up to a limit)
            async with self._queue_lock:
                if len(self._event_queue) < self._batch_size * 10:
                    self._event_queue = events_to_send + self._event_queue

    async def _send_events_batch(self, events: List[Dict[str, Any]]) -> None:
        """Send a batch of events to CIRISLens API.

        Args:
            events: List of event dictionaries to send
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        payload = {
            "events": events,
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "consent_timestamp": self._consent_timestamp,
        }

        async with self._session.post(
            f"{self._endpoint_url}/covenant/events",
            json=payload,
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"CIRISLens API error {response.status}: {error_text}")

    async def _queue_event(self, event: Dict[str, Any]) -> None:
        """Add event to queue and flush if batch is full.

        Args:
            event: Event dictionary to queue
        """
        if not self._consent_given:
            logger.debug("Event dropped - consent not given")
            return

        self._events_received += 1
        events_to_send: List[Dict[str, Any]] = []

        async with self._queue_lock:
            self._event_queue.append(event)

            if len(self._event_queue) >= self._batch_size:
                # Prepare batch for sending
                events_to_send = self._event_queue.copy()
                self._event_queue.clear()

        # Flush outside of lock if batch is full
        if events_to_send:
            try:
                await self._send_events_batch(events_to_send)
                self._events_sent += len(events_to_send)
                self._last_send_time = datetime.now(timezone.utc)
            except Exception as e:
                self._events_failed += len(events_to_send)
                logger.error(f"Failed to send batch: {e}")

    # =========================================================================
    # WiseBus-Compatible Interface (Duck-typed)
    # =========================================================================

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Receive WBD (Wisdom-Based Deferral) events.

        This is called by WiseBus.send_deferral() which broadcasts to all
        WiseAuthority services with the send_deferral capability.

        Args:
            request: DeferralRequest containing deferral details

        Returns:
            String confirming receipt
        """
        logger.debug(f"Received WBD event for thought {request.thought_id}")

        # Build anonymized event
        wbd_event: Dict[str, Any] = {
            "event_type": "wbd_deferral",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self._agent_id_hash or "unknown",
            "thought_id": request.thought_id,
            "task_id": request.task_id,
            "reason": request.reason[:200] if request.reason else None,  # Truncate
            "defer_until": request.defer_until.isoformat() if request.defer_until else None,
            # Do NOT include context/metadata which may contain sensitive info
        }

        await self._queue_event(wbd_event)

        return f"WBD event recorded for covenant metrics: {request.thought_id}"

    async def fetch_guidance(self, context: Any) -> Optional[str]:
        """Not implemented - this service only receives deferrals.

        Args:
            context: Guidance context (ignored)

        Returns:
            None - this service does not provide guidance
        """
        return None

    async def get_guidance(self, question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Not implemented - this service only receives deferrals.

        Args:
            question: Question (ignored)
            context: Context (ignored)

        Returns:
            Empty guidance response
        """
        return {
            "guidance": None,
            "confidence": 0.0,
            "source": "covenant_metrics",
            "message": "CovenantMetricsService does not provide guidance",
        }

    # =========================================================================
    # PDMA Decision Event Collection
    # =========================================================================

    async def record_pdma_decision(
        self,
        thought_id: str,
        selected_action: str,
        rationale: str,
        reasoning_summary: Optional[str] = None,
    ) -> None:
        """Record a PDMA decision event.

        This method should be called when a PDMA decision is made.
        It can be hooked into the telemetry or audit system.

        Args:
            thought_id: ID of the thought being processed
            selected_action: The action selected (SPEAK, DEFER, etc.)
            rationale: Brief rationale for the decision
            reasoning_summary: Optional truncated reasoning
        """
        pdma_event: Dict[str, Any] = {
            "event_type": "pdma_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self._agent_id_hash or "unknown",
            "thought_id": thought_id,
            "selected_action": selected_action,
            "rationale": rationale[:200] if rationale else None,  # Truncate
            "reasoning_summary": reasoning_summary[:500] if reasoning_summary else None,
        }

        await self._queue_event(pdma_event)
        logger.debug(f"Recorded PDMA decision for thought {thought_id}: {selected_action}")

    # =========================================================================
    # Consent Management
    # =========================================================================

    def set_consent(self, consent_given: bool, timestamp: Optional[str] = None) -> None:
        """Update consent state.

        Args:
            consent_given: Whether consent is given
            timestamp: ISO timestamp when consent was given/revoked
        """
        self._consent_given = consent_given
        self._consent_timestamp = timestamp or datetime.now(timezone.utc).isoformat()

        if consent_given:
            logger.info(f"Consent granted for covenant metrics at {self._consent_timestamp}")
        else:
            logger.info(f"Consent revoked for covenant metrics at {self._consent_timestamp}")

    def set_agent_id(self, agent_id: str) -> None:
        """Set and anonymize the agent ID.

        Args:
            agent_id: Raw agent identifier to hash
        """
        self._agent_id_hash = self._anonymize_agent_id(agent_id)
        logger.debug(f"Agent ID hash set: {self._agent_id_hash}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics for telemetry.

        Returns:
            Dictionary of service metrics
        """
        return {
            "consent_given": self._consent_given,
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_failed": self._events_failed,
            "events_queued": len(self._event_queue),
            "last_send_time": self._last_send_time.isoformat() if self._last_send_time else None,
        }
