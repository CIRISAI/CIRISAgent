"""
Covenant Metrics Services - Trace capture for CIRISLens scoring.

This module implements the CovenantMetricsService which:
1. Subscribes to reasoning_event_stream for trace capture (6 components)
2. Receives WBD (Wisdom-Based Deferral) events via WiseBus broadcast
3. Batches events and sends them to CIRISLens API
4. Signs complete traces with Ed25519 for integrity verification
5. Only operates when explicit consent has been given

Trace Detail Levels:
- generic (default): Numeric scores only - powers ciris.ai/ciris-scoring
- detailed: Adds actionable lists (sources, stakeholders, flags)
- full_traces: Complete reasoning text for research corpus

Trace Components (from coherence-ratchet):
1. Observation - What triggered processing (THOUGHT_START)
2. Context - System snapshot and environment (SNAPSHOT_AND_CONTEXT)
3. Rationale - DMA reasoning analysis (DMA_RESULTS + ASPDMA_RESULT)
4. Conscience - Ethical validation (CONSCIENCE_RESULT)
5. Action - Final action taken (ACTION_RESULT)
6. Outcome - Execution results and audit (ACTION_RESULT audit data)
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from ciris_engine.schemas.services.authority_core import DeferralRequest
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class TraceDetailLevel(str, Enum):
    """Trace detail levels for privacy/bandwidth control.

    generic: Numeric scores only - minimum data for CIRIS scoring formula.
             No text strings, no reasoning, no prompts. Default level.
             Powers: ciris.ai/ciris-scoring

    detailed: Adds actionable lists and key identifiers.
              Includes: sources_identified, stakeholders, flags arrays.
              Good for debugging without full reasoning exposure.

    full_traces: Complete reasoning text for Coherence Ratchet corpus.
                 Includes all prompts, reasoning text, and full context.
                 Use only with full research consent.
    """

    GENERIC = "generic"
    DETAILED = "detailed"
    FULL_TRACES = "full_traces"


@dataclass
class SimpleCapabilities:
    """Simple capabilities container for duck-typing with WiseBus."""

    actions: List[str]
    scopes: List[str]


@dataclass
class TraceComponent:
    """A single component of a reasoning trace."""

    component_type: str  # observation, context, rationale, conscience, action, outcome
    event_type: str  # THOUGHT_START, SNAPSHOT_AND_CONTEXT, etc.
    timestamp: str
    data: Dict[str, Any]


@dataclass
class CompleteTrace:
    """A complete 6-component reasoning trace."""

    trace_id: str
    thought_id: str
    task_id: Optional[str]
    agent_id_hash: str
    started_at: str
    completed_at: Optional[str] = None
    components: List[TraceComponent] = field(default_factory=list)
    signature: Optional[str] = None
    signature_key_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "agent_id_hash": self.agent_id_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "components": [
                {
                    "component_type": c.component_type,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                    "data": c.data,
                }
                for c in self.components
            ],
            "signature": self.signature,
            "signature_key_id": self.signature_key_id,
        }

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of trace content (excluding signature)."""
        # Build deterministic representation
        content = {
            "trace_id": self.trace_id,
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "agent_id_hash": self.agent_id_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "components": [
                {
                    "component_type": c.component_type,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                    "data": c.data,
                }
                for c in self.components
            ],
        }
        json_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()


class Ed25519TraceSigner:
    """Sign traces using the unified Ed25519 signing key.

    This class wraps the unified signing key from ciris_engine.logic.audit.signing_protocol,
    ensuring the same key is used for both audit trail signing and covenant metrics traces.

    The unified key is stored at data/agent_signing.key and is shared with the audit service.
    """

    def __init__(self, seed_dir: Optional[Path] = None):
        """Initialize signer with optional seed directory for root public key."""
        self._unified_key: Optional[Any] = None
        self._root_pubkey: Optional[str] = None
        self._key_id: Optional[str] = None

        # Load root public key from seed directory (for verification only)
        if seed_dir is None:
            seed_dir = Path(__file__).parent.parent.parent / "seed"

        root_pub_file = seed_dir / "root_pub.json"
        if root_pub_file.exists():
            with open(root_pub_file) as f:
                root_data = json.load(f)
                self._root_pubkey = root_data.get("pubkey")
                logger.info(f"Loaded root public key: {root_data.get('wa_id', 'wa-unknown')}")

    def _ensure_unified_key(self) -> bool:
        """Ensure the unified signing key is loaded."""
        if self._unified_key is not None:
            return True

        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            self._unified_key = get_unified_signing_key()
            self._key_id = self._unified_key.key_id
            logger.info(f"Using unified signing key: {self._key_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not load unified signing key: {e}")
            return False

    def sign_trace(self, trace: CompleteTrace) -> bool:
        """Sign a trace with Ed25519 unified signing key.

        Signs the JSON array of components (not the full trace object).
        This matches CIRISLens verification which expects:
            message = json.dumps([c.model_dump() for c in trace.components], sort_keys=True).encode('utf-8')

        Returns True if signing succeeded, False if key not available.
        """
        if not self._ensure_unified_key() or self._unified_key is None:
            logger.warning("No unified signing key available for trace signing")
            return False

        try:
            # Build the canonical message that CIRISLens will verify against:
            # JSON array of components, alphabetically sorted keys, no extra whitespace
            components_list = [
                {
                    "component_type": c.component_type,
                    "data": c.data,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                }
                for c in trace.components
            ]
            # Must match CIRISLens exactly: sort_keys=True, UTF-8 encoded
            message = json.dumps(components_list, sort_keys=True).encode("utf-8")

            # Sign the raw message bytes (not a hash)
            trace.signature = self._unified_key.sign_base64(message)
            trace.signature_key_id = self._key_id

            logger.debug(f"Signed trace {trace.trace_id} with unified key {self._key_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to sign trace: {e}")
            return False

    def verify_trace(self, trace: CompleteTrace) -> bool:
        """Verify a trace signature using root public key.

        Verifies against the canonical JSON components message.
        """
        if not trace.signature or not self._root_pubkey:
            return False

        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Decode public key
            pubkey_bytes = base64.urlsafe_b64decode(self._root_pubkey + "==")
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)

            # Decode signature
            sig_bytes = base64.urlsafe_b64decode(trace.signature + "==")

            # Build the canonical message (same as sign_trace)
            components_list = [
                {
                    "component_type": c.component_type,
                    "data": c.data,
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
                }
                for c in trace.components
            ]
            message = json.dumps(components_list, sort_keys=True).encode("utf-8")

            # Verify
            public_key.verify(sig_bytes, message)
            return True

        except Exception as e:
            logger.warning(f"Trace signature verification failed: {e}")
            return False

    @property
    def key_id(self) -> Optional[str]:
        """Get the key ID, loading unified key if needed."""
        if self._key_id is None:
            self._ensure_unified_key()
        return self._key_id

    @property
    def has_signing_key(self) -> bool:
        """Check if a signing key is available."""
        return self._ensure_unified_key()


class CovenantMetricsService:
    """
    Covenant compliance metrics service for CIRISLens.

    This service:
    1. Subscribes to reasoning_event_stream for FULL 6-component trace capture
    2. Receives WBD (Wisdom-Based Deferral) events from WiseBus
    3. Batches and sends traces to CIRISLens API
    4. Signs complete traces with Ed25519 for integrity verification

    CRITICAL: This service ONLY sends data when:
    1. User has explicitly consented via the setup wizard
    2. The consent_given config flag is True
    3. A valid consent_timestamp exists

    Data sent is anonymized:
    - Agent IDs are hashed
    - No user message content is included
    - Only structural decision metadata
    """

    # Map reasoning events to trace components
    # Handle both formats: "THOUGHT_START" and "ReasoningEvent.THOUGHT_START"
    EVENT_TO_COMPONENT = {
        "THOUGHT_START": "observation",
        "SNAPSHOT_AND_CONTEXT": "context",
        "DMA_RESULTS": "rationale",
        "ASPDMA_RESULT": "rationale",
        "CONSCIENCE_RESULT": "conscience",
        "ACTION_RESULT": "action",  # Also contains outcome data
        # Also handle full enum names from streaming
        "ReasoningEvent.THOUGHT_START": "observation",
        "ReasoningEvent.SNAPSHOT_AND_CONTEXT": "context",
        "ReasoningEvent.DMA_RESULTS": "rationale",
        "ReasoningEvent.ASPDMA_RESULT": "rationale",
        "ReasoningEvent.CONSCIENCE_RESULT": "conscience",
        "ReasoningEvent.ACTION_RESULT": "action",
    }

    def __init__(
        self,
        config: Optional[JSONDict] = None,
        agent_id: Optional[str] = None,
        **kwargs: Any,  # Accept extra params from service_initializer (bus_manager, etc.)
    ) -> None:
        """Initialize CovenantMetricsService.

        Args:
            config: Configuration dict with consent settings
            agent_id: Agent identifier (will be hashed for privacy)
            **kwargs: Additional params from service_initializer (ignored)
        """
        self._config = config or {}

        # Set agent_id if provided during construction
        self._initial_agent_id = agent_id

        # Consent state - check env var first for QA testing
        env_consent = os.environ.get("CIRIS_COVENANT_METRICS_CONSENT", "").lower() == "true"
        env_timestamp = os.environ.get("CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP")

        config_consent = bool(self._config.get("consent_given", False))
        self._consent_given = config_consent or env_consent

        self._consent_timestamp: Optional[str] = None
        raw_timestamp = self._config.get("consent_timestamp") or env_timestamp
        if raw_timestamp is not None:
            self._consent_timestamp = str(raw_timestamp)

        if env_consent and not config_consent:
            logger.info("✅ CONSENT enabled via environment variable CIRIS_COVENANT_METRICS_CONSENT")

        # Endpoint configuration - check env var first for QA testing
        env_endpoint = os.environ.get("CIRIS_COVENANT_METRICS_ENDPOINT")
        raw_url = self._config.get("endpoint_url")
        if env_endpoint:
            self._endpoint_url: str = env_endpoint
        elif raw_url:
            self._endpoint_url = str(raw_url)
        else:
            self._endpoint_url = "https://lens.ciris-services-1.ai/lens-api/api/v1"

        raw_batch = self._config.get("batch_size")
        if raw_batch is not None and isinstance(raw_batch, (int, float, str)):
            self._batch_size: int = int(raw_batch)
        else:
            self._batch_size = 10

        # Flush interval - check env var first for QA testing
        env_interval = os.environ.get("CIRIS_COVENANT_METRICS_FLUSH_INTERVAL")
        raw_interval = self._config.get("flush_interval_seconds")
        if env_interval is not None:
            self._flush_interval: float = float(env_interval)
        elif raw_interval is not None and isinstance(raw_interval, (int, float, str)):
            self._flush_interval = float(raw_interval)
        else:
            self._flush_interval = 60.0

        # Trace detail level - check env var first for QA testing
        # Default is GENERIC (numeric scores only) for ciris.ai/ciris-scoring
        env_level = os.environ.get("CIRIS_COVENANT_METRICS_TRACE_LEVEL", "").lower()
        config_level = str(self._config.get("trace_level", "")).lower()
        level_str = env_level or config_level or "generic"
        try:
            self._trace_level = TraceDetailLevel(level_str)
        except ValueError:
            logger.warning(f"Invalid trace_level '{level_str}', defaulting to 'generic'")
            self._trace_level = TraceDetailLevel.GENERIC

        logger.info(f"📊 Trace detail level: {self._trace_level.value}")

        # Early warning correlation metadata (optional, anonymous)
        self._deployment_region: str = str(self._config.get("deployment_region", "") or "")
        self._deployment_type: str = str(self._config.get("deployment_type", "") or "")
        self._agent_role: str = str(self._config.get("agent_role", "") or "")
        self._agent_template: str = str(self._config.get("agent_template", "") or "")

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
        self._traces_completed = 0
        self._traces_signed = 0
        self._last_send_time: Optional[datetime] = None

        # Agent ID for anonymization (set during start)
        self._agent_id_hash: Optional[str] = None

        # Reasoning event stream subscription
        self._reasoning_queue: Optional[asyncio.Queue[Any]] = None
        self._reasoning_task: Optional[asyncio.Task[None]] = None

        # Active traces being built (keyed by thought_id)
        self._active_traces: Dict[str, CompleteTrace] = {}
        self._traces_lock = asyncio.Lock()

        # Completed traces ready for sending
        self._completed_traces: List[CompleteTrace] = []

        # Trace signer
        self._signer = Ed25519TraceSigner()

        logger.info(
            f"CovenantMetricsService initialized (consent_given={self._consent_given}, "
            f"endpoint={self._endpoint_url}, signer_key={self._signer.key_id})"
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
        logger.info("=" * 70)
        logger.info("🚀 COVENANT METRICS SERVICE STARTING")
        logger.info(f"   Consent given: {self._consent_given}")
        logger.info(f"   Endpoint: {self._endpoint_url}")

        # Set agent_id from constructor if provided and not already set
        if self._initial_agent_id and not self._agent_id_hash:
            self.set_agent_id(self._initial_agent_id)
            logger.info(f"   Agent ID set from constructor: {self._initial_agent_id}")

        logger.info("=" * 70)

        # Subscribe to reasoning_event_stream for trace capture
        # This happens regardless of consent - we just don't SEND until consent
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            self._reasoning_queue = asyncio.Queue(maxsize=1000)
            reasoning_event_stream.subscribe(self._reasoning_queue)
            self._reasoning_task = asyncio.create_task(self._process_reasoning_events())
            subscriber_count = len(reasoning_event_stream._subscribers)
            logger.info("=" * 70)
            logger.info(f"✅ SUBSCRIBED to reasoning_event_stream")
            logger.info(f"   Total subscribers: {subscriber_count}")
            logger.info(f"   Queue maxsize: 1000")
            logger.info("=" * 70)
        except Exception as e:
            logger.error("=" * 70)
            logger.error(f"❌ FAILED to subscribe to reasoning_event_stream: {e}")
            logger.error("   Traces will NOT be captured!")
            logger.error("=" * 70)

        if not self._consent_given:
            logger.warning("=" * 70)
            logger.warning("⚠️  CONSENT NOT GIVEN - traces captured but NOT sent")
            logger.warning("   Complete setup wizard to enable sending")
            logger.warning("=" * 70)
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

        logger.info("=" * 70)
        logger.info(f"✅ COVENANT METRICS SERVICE READY")
        logger.info(f"   Sending to: {self._endpoint_url}")
        logger.info(f"   Consent timestamp: {self._consent_timestamp}")
        logger.info(f"   Batch size: {self._batch_size}")
        logger.info(f"   Flush interval: {self._flush_interval}s")
        logger.info("=" * 70)

        # Register public key with CIRISLens (before connect event)
        await self._register_public_key()

        # Send connected event to server
        await self._send_connected_event("startup")

    async def stop(self) -> None:
        """Stop the service and flush remaining events."""
        logger.info("=" * 70)
        logger.info("🛑 COVENANT METRICS SERVICE STOPPING")
        logger.info(f"   Traces completed: {self._traces_completed}")
        logger.info(f"   Events in queue: {len(self._event_queue)}")
        logger.info("=" * 70)

        # Unsubscribe from reasoning_event_stream
        if self._reasoning_queue:
            try:
                from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

                reasoning_event_stream.unsubscribe(self._reasoning_queue)
                logger.info("   Unsubscribed from reasoning_event_stream")
            except Exception as e:
                logger.debug(f"Could not unsubscribe from reasoning_event_stream: {e}")

        # Cancel reasoning task
        if self._reasoning_task and not self._reasoning_task.done():
            self._reasoning_task.cancel()
            try:
                await self._reasoning_task
            except asyncio.CancelledError:
                pass

        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining events
        logger.info("   Performing final flush...")
        await self._flush_events()

        # Send disconnect event before closing session (only if consent still given)
        if self._session and self._consent_given:
            await self._send_connected_event("shutdown")

        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None

        logger.info("=" * 70)
        logger.info("📊 COVENANT METRICS FINAL STATS")
        logger.info(f"   Traces completed: {self._traces_completed}")
        logger.info(f"   Events sent: {self._events_sent}")
        logger.info(f"   Events failed: {self._events_failed}")
        logger.info(f"   Events received: {self._events_received}")
        logger.info("=" * 70)

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
        if not self._consent_given:
            logger.debug("⏭️  Flush skipped - no consent")
            return
        if not self._session:
            logger.debug("⏭️  Flush skipped - no HTTP session")
            return

        async with self._queue_lock:
            if not self._event_queue:
                return

            events_to_send = self._event_queue.copy()
            self._event_queue.clear()

        logger.info(f"📤 FLUSHING {len(events_to_send)} events to {self._endpoint_url}")

        try:
            await self._send_events_batch(events_to_send)
            self._events_sent += len(events_to_send)
            self._last_send_time = datetime.now(timezone.utc)
            logger.info(f"✅ FLUSH SUCCESS: {len(events_to_send)} events sent (total: {self._events_sent})")
        except Exception as e:
            self._events_failed += len(events_to_send)
            logger.error(f"❌ FLUSH FAILED: {len(events_to_send)} events: {e}")
            # Re-queue failed events (up to a limit)
            async with self._queue_lock:
                if len(self._event_queue) < self._batch_size * 10:
                    self._event_queue = events_to_send + self._event_queue
                    logger.info(f"   Re-queued {len(events_to_send)} events for retry")

    async def _send_events_batch(self, events: List[Dict[str, Any]]) -> None:
        """Send a batch of events to CIRISLens API.

        Args:
            events: List of event dictionaries to send
        """
        if not self._session:
            raise RuntimeError("HTTP session not initialized")

        # Build early warning correlation metadata (only include non-empty values)
        correlation_metadata: Dict[str, str] = {}
        if self._deployment_region:
            correlation_metadata["deployment_region"] = self._deployment_region
        if self._deployment_type:
            correlation_metadata["deployment_type"] = self._deployment_type
        if self._agent_role:
            correlation_metadata["agent_role"] = self._agent_role
        if self._agent_template:
            correlation_metadata["agent_template"] = self._agent_template

        payload: Dict[str, Any] = {
            "events": events,
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "consent_timestamp": self._consent_timestamp,
            "trace_level": self._trace_level.value,
        }
        # Only add correlation metadata if user opted in to any fields
        if correlation_metadata:
            payload["correlation_metadata"] = correlation_metadata

        url = f"{self._endpoint_url}/covenant/events"
        logger.info(f"📡 POST {url} ({len(events)} events)")

        async with self._session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"CIRISLens API error {response.status}: {error_text}")
            logger.info(f"✅ POST success: {response.status}")

    async def _register_public_key(self) -> None:
        """Register agent public key with CIRISLens for signature verification.

        This should be called during startup, before sending any signed traces.
        CIRISLens will use this key to verify all traces from this agent.
        """
        if not self._session:
            logger.warning("Cannot register public key - HTTP session not initialized")
            return

        # Ensure signing key is initialized
        if not self._signer.has_signing_key:
            logger.warning("Cannot register public key - no signing key available")
            return

        try:
            # Get registration payload from unified signing key
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            unified_key = get_unified_signing_key()
            description = f"Agent key for covenant metrics traces"
            if self._agent_template:
                description = f"Agent key ({self._agent_template})"

            payload = unified_key.get_registration_payload(description)

            # Store registered key ID for comparison during signing
            self._registered_key_id = payload['key_id']

            url = f"{self._endpoint_url}/covenant/public-keys"

            logger.info("=" * 70)
            logger.info(f"🔑 REGISTERING PUBLIC KEY with CIRISLens")
            logger.info(f"   URL: {url}")
            logger.info(f"   Key ID (REGISTRATION): {payload['key_id']}")
            logger.info(f"   Public key (first 20 chars): {payload['public_key_base64'][:20]}...")
            logger.info(f"   Algorithm: {payload['algorithm']}")
            logger.info(f"   Signer key_id: {self._signer.key_id}")

            async with self._session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info(f"✅ PUBLIC KEY REGISTERED SUCCESSFULLY")
                    logger.info("=" * 70)
                elif response.status == 409:
                    # Key already registered (conflict) - this is fine
                    logger.info(f"✅ PUBLIC KEY ALREADY REGISTERED (409 Conflict)")
                    logger.info("=" * 70)
                else:
                    error_text = await response.text()
                    logger.warning(f"⚠️ PUBLIC KEY REGISTRATION FAILED - Status {response.status}: {error_text}")
                    logger.warning("   Traces will still be signed, but verification may fail")
                    logger.warning("=" * 70)

        except aiohttp.ClientConnectorError as e:
            logger.warning("=" * 70)
            logger.warning(f"⚠️ PUBLIC KEY REGISTRATION FAILED - Cannot reach server: {e}")
            logger.warning("   Will retry on next startup")
            logger.warning("=" * 70)

        except Exception as e:
            logger.warning("=" * 70)
            logger.warning(f"⚠️ PUBLIC KEY REGISTRATION FAILED - Unexpected error: {e}")
            logger.warning("=" * 70)

    async def _send_connected_event(self, event_type: str = "connected") -> None:
        """Send a connected/heartbeat event to CIRISLens to signal agent is online.

        Args:
            event_type: Type of connection event (startup, heartbeat, reconnect)
        """
        if not self._session:
            logger.warning("Cannot send connected event - HTTP session not initialized")
            return

        # Build correlation metadata
        correlation_metadata: Dict[str, str] = {}
        if self._deployment_region:
            correlation_metadata["deployment_region"] = self._deployment_region
        if self._deployment_type:
            correlation_metadata["deployment_type"] = self._deployment_type
        if self._agent_role:
            correlation_metadata["agent_role"] = self._agent_role
        if self._agent_template:
            correlation_metadata["agent_template"] = self._agent_template

        timestamp = datetime.now(timezone.utc).isoformat()

        # Build a signed trace for connectivity events
        connectivity_trace = CompleteTrace(
            trace_id=f"connectivity-{event_type}-{timestamp}",
            thought_id=f"connectivity-{event_type}",
            task_id=None,
            agent_id_hash=self._agent_id_hash or "unknown",
            started_at=timestamp,
            completed_at=timestamp,
        )

        # Add connectivity component
        connectivity_trace.components.append(
            TraceComponent(
                component_type="connectivity",
                event_type=event_type,
                timestamp=timestamp,
                data={
                    "version": "1.8.5",
                    "trace_level": self._trace_level.value,
                    **({"correlation_metadata": correlation_metadata} if correlation_metadata else {}),
                },
            )
        )

        # Sign the trace (falls back to empty strings if no key available)
        if not self._signer.sign_trace(connectivity_trace):
            # No signing key available - use empty strings for unsigned trace
            connectivity_trace.signature = ""
            connectivity_trace.signature_key_id = ""

        payload: Dict[str, Any] = {
            "event_type": f"connectivity_{event_type}",
            "trace": connectivity_trace.to_dict(),
        }

        # Use the standard events endpoint
        url = f"{self._endpoint_url}/covenant/events"

        try:
            logger.info("=" * 70)
            logger.info(f"📡 SENDING CONNECTED EVENT to {url}")
            logger.info(f"   Event type: {event_type}")
            logger.info(f"   Agent hash: {self._agent_id_hash}")

            # Wrap as a standard event batch
            batch_payload: Dict[str, Any] = {
                "events": [payload],
                "batch_timestamp": timestamp,
                "consent_timestamp": self._consent_timestamp,
                "trace_level": self._trace_level.value,
            }
            if correlation_metadata:
                batch_payload["correlation_metadata"] = correlation_metadata

            async with self._session.post(url, json=batch_payload) as response:
                if response.status == 200:
                    logger.info(f"✅ CONNECTED EVENT SUCCESS - Server acknowledged agent online")
                    logger.info("=" * 70)
                else:
                    error_text = await response.text()
                    logger.error(f"❌ CONNECTED EVENT FAILED - Status {response.status}: {error_text}")
                    logger.error("=" * 70)

        except aiohttp.ClientConnectorError as e:
            logger.error("=" * 70)
            logger.error(f"❌ CONNECTED EVENT FAILED - Cannot reach server: {e}")
            logger.error(f"   Endpoint: {url}")
            logger.error("   Check network connectivity and endpoint URL")
            logger.error("=" * 70)

        except Exception as e:
            logger.error("=" * 70)
            logger.error(f"❌ CONNECTED EVENT FAILED - Unexpected error: {e}")
            logger.error("=" * 70)

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
    # Reasoning Event Stream Processing (6-Component Trace Capture)
    # =========================================================================

    async def _process_reasoning_events(self) -> None:
        """Process reasoning events from the stream and build traces."""
        logger.info("🎯 Starting reasoning event processor - listening for H3ERE pipeline events")
        events_processed = 0

        # Ensure queue is initialized (mypy hint)
        if self._reasoning_queue is None:
            logger.error("Reasoning queue not initialized")
            return

        while True:
            try:
                # Wait for next event with timeout to check for cancellation
                try:
                    event_data = await asyncio.wait_for(self._reasoning_queue.get(), timeout=1.0)
                    events_processed += 1
                    logger.info(f"📥 RECEIVED reasoning event #{events_processed}: {type(event_data).__name__}")
                    await self._handle_reasoning_event(event_data)
                except asyncio.TimeoutError:
                    # No event, just continue waiting
                    continue
            except asyncio.CancelledError:
                logger.info(f"Reasoning event processor cancelled (processed {events_processed} events)")
                break
            except Exception as e:
                # Check if event loop is gone (e.g., during shutdown/test teardown)
                err_str = str(e).lower()
                if "no running event loop" in err_str or "event loop is closed" in err_str:
                    logger.debug("Event loop closed, stopping reasoning event processor")
                    break
                logger.error(f"Error processing reasoning event: {e}")

    async def _handle_reasoning_event(self, event_data: Dict[str, Any]) -> None:
        """Handle a single reasoning event and add to appropriate trace.

        Args:
            event_data: ReasoningStreamUpdate dict from step_streaming
        """
        # Extract events from stream update
        events = event_data.get("events", [])
        logger.debug(f"Handling event_data with {len(events)} events")
        for event in events:
            await self._process_single_event(event)

    async def _process_single_event(self, event: Dict[str, Any]) -> None:
        """Process a single reasoning event.

        Args:
            event: Individual reasoning event dict
        """
        raw_event_type = event.get("event_type", "")
        # Handle both enum objects and strings
        # Enums show as <ReasoningEvent.THOUGHT_START: 'thought_start'>
        if hasattr(raw_event_type, "value"):
            event_type = raw_event_type.value.upper()  # 'thought_start' -> 'THOUGHT_START'
        else:
            # String like "ReasoningEvent.THOUGHT_START" - extract the last part
            event_type = str(raw_event_type).replace("ReasoningEvent.", "")

        thought_id = event.get("thought_id", "")
        task_id = event.get("task_id")
        timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

        if not thought_id:
            logger.debug(f"Ignoring event without thought_id: {event_type}")
            return

        self._events_received += 1

        # Get or create trace for this thought
        async with self._traces_lock:
            if thought_id not in self._active_traces:
                # Create new trace
                trace_id = f"trace-{thought_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                self._active_traces[thought_id] = CompleteTrace(
                    trace_id=trace_id,
                    thought_id=thought_id,
                    task_id=task_id,
                    agent_id_hash=self._agent_id_hash or "unknown",
                    started_at=timestamp,
                )
                logger.debug(f"Created new trace {trace_id} for thought {thought_id}")

            trace = self._active_traces[thought_id]

        # Map event type to trace component
        component_type = self.EVENT_TO_COMPONENT.get(event_type, "unknown")
        if component_type == "unknown":
            logger.debug(f"Unknown event type: {event_type}")

        # Extract relevant data based on event type
        component_data = self._extract_component_data(event_type, event)

        # Add component to trace
        component = TraceComponent(
            component_type=component_type,
            event_type=event_type,
            timestamp=timestamp,
            data=component_data,
        )

        async with self._traces_lock:
            trace.components.append(component)

        # Check if trace is complete (has ACTION_RESULT)
        # Handle both formats
        if event_type in ("ACTION_RESULT", "ReasoningEvent.ACTION_RESULT"):
            await self._complete_trace(thought_id, timestamp)

    def _extract_component_data(self, event_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract reasoning data from event based on configured trace detail level.

        Trace levels control what data is captured:
        - GENERIC: Numeric scores only (default) - powers ciris.ai/ciris-scoring
        - DETAILED: Adds actionable lists (sources, stakeholders, flags)
        - FULL_TRACES: Complete reasoning text for Coherence Ratchet corpus

        Args:
            event_type: Type of reasoning event
            event: Full event data

        Returns:
            Component data filtered by trace detail level
        """
        level = self._trace_level
        is_detailed = level in (TraceDetailLevel.DETAILED, TraceDetailLevel.FULL_TRACES)
        is_full = level == TraceDetailLevel.FULL_TRACES

        def _serialize(obj: Any) -> Any:
            """Recursively serialize objects to JSON-safe format."""
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, (list, tuple)):
                return [_serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "__dict__"):
                return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
            return str(obj)

        if event_type == "THOUGHT_START":
            # OBSERVATION: What triggered processing
            # GENERIC: Core numeric metadata only
            data: Dict[str, Any] = {
                "round_number": event.get("round_number"),
                "thought_depth": event.get("thought_depth"),
                "task_priority": event.get("task_priority"),
                "updated_info_available": event.get("updated_info_available"),
                "requires_human_input": event.get("requires_human_input"),
            }
            # DETAILED: Add type identifiers
            if is_detailed:
                data["thought_type"] = event.get("thought_type")
                data["thought_status"] = event.get("thought_status")
                data["parent_thought_id"] = event.get("parent_thought_id")
                data["channel_id"] = event.get("channel_id")
                data["source_adapter"] = event.get("source_adapter")
            # FULL: Add description text
            if is_full:
                data["task_description"] = event.get("task_description")
                data["initial_context"] = event.get("initial_context")
            return data

        elif event_type == "SNAPSHOT_AND_CONTEXT":
            # CONTEXT: Environmental state when decision was made
            # Extract system_snapshot which contains the context data
            snapshot = event.get("system_snapshot", {})
            if hasattr(snapshot, "model_dump"):
                snapshot = snapshot.model_dump()

            # GENERIC: Minimal - just cognitive state identifier
            # cognitive_state might be at top level or in snapshot
            cognitive_state = event.get("cognitive_state") or snapshot.get("cognitive_state")
            data = {
                "cognitive_state": cognitive_state,
            }
            # DETAILED: Add service list
            if is_detailed:
                data["active_services"] = event.get("active_services") or snapshot.get("active_services")
                data["context_sources"] = event.get("context_sources") or snapshot.get("context_sources")
            # FULL: Add complete snapshot and context
            if is_full:
                data["system_snapshot"] = _serialize(snapshot)
                data["gathered_context"] = _serialize(event.get("gathered_context"))
                data["relevant_memories"] = _serialize(event.get("relevant_memories"))
                data["conversation_history"] = _serialize(event.get("conversation_history"))
            return data

        elif event_type == "DMA_RESULTS":
            # RATIONALE (Part 1): DMA reasoning outputs
            csdma = event.get("csdma", {})
            dsdma = event.get("dsdma", {})
            pdma = event.get("pdma", {})
            idma = event.get("idma", {})

            # Handle both dict and Pydantic model objects
            if hasattr(csdma, "model_dump"):
                csdma = csdma.model_dump()
            if hasattr(dsdma, "model_dump"):
                dsdma = dsdma.model_dump()
            if hasattr(pdma, "model_dump"):
                pdma = pdma.model_dump()
            if hasattr(idma, "model_dump"):
                idma = idma.model_dump()

            # GENERIC: Numeric scores only - powers CIRIS scoring formula
            csdma_data: Dict[str, Any] = {
                "plausibility_score": csdma.get("plausibility_score") if isinstance(csdma, dict) else None,
            }
            dsdma_data: Dict[str, Any] = {
                "domain_alignment": dsdma.get("domain_alignment") if isinstance(dsdma, dict) else None,
            }
            # PDMA: has_conflicts is True if conflicts field is non-empty and not "none"
            conflicts_val = pdma.get("conflicts") if isinstance(pdma, dict) else None
            has_conflicts = bool(
                conflicts_val and isinstance(conflicts_val, str) and conflicts_val.lower().strip() != "none"
            )
            pdma_data: Dict[str, Any] = {"has_conflicts": has_conflicts}
            idma_data: Optional[Dict[str, Any]] = (
                {
                    "k_eff": idma.get("k_eff") if isinstance(idma, dict) else None,
                    "correlation_risk": idma.get("correlation_risk") if isinstance(idma, dict) else None,
                    "fragility_flag": idma.get("fragility_flag") if isinstance(idma, dict) else None,
                    # phase is a key scoring metric: chaos/healthy/rigidity
                    "phase": idma.get("phase") if isinstance(idma, dict) else None,
                }
                if idma
                else None
            )

            # DETAILED: Add flags, lists, identifiers
            if is_detailed:
                csdma_data["flags"] = csdma.get("flags", []) if isinstance(csdma, dict) else []
                dsdma_data["domain"] = dsdma.get("domain") if isinstance(dsdma, dict) else None
                dsdma_data["flags"] = dsdma.get("flags", []) if isinstance(dsdma, dict) else []
                pdma_data["stakeholders"] = pdma.get("stakeholders") if isinstance(pdma, dict) else None
                pdma_data["conflicts"] = pdma.get("conflicts") if isinstance(pdma, dict) else None
                pdma_data["alignment_check"] = pdma.get("alignment_check") if isinstance(pdma, dict) else None
                if idma_data:
                    idma_data["sources_identified"] = idma.get("sources_identified") if isinstance(idma, dict) else None
                    idma_data["correlation_factors"] = (
                        idma.get("correlation_factors") if isinstance(idma, dict) else None
                    )

            # FULL: Add reasoning text and prompts
            if is_full:
                csdma_data["reasoning"] = csdma.get("reasoning") if isinstance(csdma, dict) else None
                csdma_data["prompt_used"] = event.get("csdma_prompt")
                dsdma_data["reasoning"] = dsdma.get("reasoning") if isinstance(dsdma, dict) else None
                dsdma_data["prompt_used"] = event.get("dsdma_prompt")
                pdma_data["reasoning"] = pdma.get("reasoning") if isinstance(pdma, dict) else None
                pdma_data["prompt_used"] = event.get("pdma_prompt")
                if idma_data:
                    idma_data["reasoning"] = idma.get("reasoning") if isinstance(idma, dict) else None
                    idma_data["prompt_used"] = event.get("idma_prompt")

            data = {
                "csdma": csdma_data,
                "dsdma": dsdma_data,
                "pdma": pdma_data if pdma_data else None,
                "idma": idma_data,
            }
            if is_full:
                data["combined_analysis"] = event.get("combined_analysis")
            return data

        elif event_type == "ASPDMA_RESULT":
            # RATIONALE (Part 2): Action selection
            # GENERIC: Action type and confidence only
            data = {
                "selected_action": event.get("selected_action"),
                "selection_confidence": event.get("selection_confidence"),
                "is_recursive": event.get("is_recursive", False),
            }
            # DETAILED: Add alternatives
            if is_detailed:
                data["alternatives_considered"] = event.get("alternatives_considered")
            # FULL: Add reasoning text and parameters
            if is_full:
                data["action_rationale"] = event.get("action_rationale")
                data["reasoning_summary"] = event.get("reasoning_summary")
                data["action_parameters"] = _serialize(event.get("action_parameters"))
                data["aspdma_prompt"] = event.get("aspdma_prompt")
            return data

        elif event_type == "CONSCIENCE_RESULT":
            # CONSCIENCE: Ethical validation
            # GENERIC: All boolean flags and numeric scores (core for CIRIS scoring)
            data = {
                # Overall result
                "conscience_passed": event.get("conscience_passed"),
                "action_was_overridden": event.get("action_was_overridden", False),
                "ethical_faculties_skipped": event.get("ethical_faculties_skipped"),
                # Bypass guardrails (boolean)
                "updated_status_detected": event.get("updated_status_detected"),
                "thought_depth_triggered": event.get("thought_depth_triggered"),
                "thought_depth_current": event.get("thought_depth_current"),
                "thought_depth_max": event.get("thought_depth_max"),
                # Entropy conscience (numeric)
                "entropy_passed": event.get("entropy_passed"),
                "entropy_score": event.get("entropy_score"),
                "entropy_threshold": event.get("entropy_threshold"),
                # Coherence conscience (numeric)
                "coherence_passed": event.get("coherence_passed"),
                "coherence_score": event.get("coherence_score"),
                "coherence_threshold": event.get("coherence_threshold"),
                # Optimization veto (boolean + numeric)
                "optimization_veto_passed": event.get("optimization_veto_passed"),
                "optimization_veto_entropy_ratio": event.get("optimization_veto_entropy_ratio"),
                # Epistemic humility (boolean + numeric)
                "epistemic_humility_passed": event.get("epistemic_humility_passed"),
                "epistemic_humility_certainty": event.get("epistemic_humility_certainty"),
            }
            # DETAILED: Add identifiers and lists
            if is_detailed:
                data["final_action"] = event.get("final_action")
                data["optimization_veto_decision"] = event.get("optimization_veto_decision")
                data["optimization_veto_affected_values"] = event.get("optimization_veto_affected_values")
                data["epistemic_humility_uncertainties"] = event.get("epistemic_humility_uncertainties")
                data["epistemic_humility_recommendation"] = event.get("epistemic_humility_recommendation")
            # FULL: Add all text fields
            if is_full:
                data["conscience_override_reason"] = event.get("conscience_override_reason")
                data["epistemic_data"] = _serialize(event.get("epistemic_data"))
                data["updated_status_content"] = event.get("updated_status_content")
                data["entropy_reason"] = event.get("entropy_reason")
                data["coherence_reason"] = event.get("coherence_reason")
                data["optimization_veto_justification"] = event.get("optimization_veto_justification")
                data["epistemic_humility_justification"] = event.get("epistemic_humility_justification")
            return data

        elif event_type == "ACTION_RESULT":
            # ACTION + OUTCOME: What happened and results
            # Extract positive_moment from action_parameters (for TASK_COMPLETE actions)
            action_params = event.get("action_parameters", {})
            positive_moment_text = action_params.get("positive_moment") if isinstance(action_params, dict) else None

            # GENERIC: Execution metrics and audit chain (for integrity scoring)
            data = {
                "execution_success": event.get("execution_success"),
                "execution_time_ms": event.get("execution_time_ms"),
                # Resource consumption metrics
                "tokens_input": event.get("tokens_input", 0),
                "tokens_output": event.get("tokens_output", 0),
                "tokens_total": event.get("tokens_total", 0),
                "cost_cents": event.get("cost_cents", 0.0),
                "carbon_grams": event.get("carbon_grams", 0.0),
                "energy_mwh": event.get("energy_mwh", 0.0),
                "llm_calls": event.get("llm_calls", 0),
                # Audit chain for integrity verification
                "audit_sequence_number": event.get("audit_sequence_number"),
                "audit_entry_hash": event.get("audit_entry_hash"),
                # Positive moment indicator (privacy-preserving boolean)
                "has_positive_moment": positive_moment_text is not None and len(positive_moment_text) > 0,
            }
            # DETAILED: Add action type and follow-up
            if is_detailed:
                data["action_executed"] = event.get("action_executed")
                data["follow_up_thought_id"] = event.get("follow_up_thought_id")
                data["audit_entry_id"] = event.get("audit_entry_id")
                data["models_used"] = event.get("models_used", [])
                data["api_bases_used"] = event.get("api_bases_used", [])
            # FULL: Add parameters, error details, signature, and full positive moment text
            if is_full:
                data["action_parameters"] = _serialize(action_params) if action_params else {}
                data["execution_error"] = event.get("error")
                data["audit_signature"] = event.get("audit_signature")
                # Include full positive moment text at FULL detail level
                if positive_moment_text:
                    data["positive_moment"] = positive_moment_text[:500]  # Truncate for safety
            return data

        else:
            # Unknown event type - capture minimal info
            # GENERIC: Just event type
            data = {"event_type": event_type}
            # FULL: Include serialized data
            if is_full:
                data["raw_data"] = _serialize(event)
            return data

    async def _complete_trace(self, thought_id: str, completion_time: str) -> None:
        """Complete and sign a trace.

        Args:
            thought_id: ID of the thought whose trace is complete
            completion_time: Timestamp of completion
        """
        async with self._traces_lock:
            if thought_id not in self._active_traces:
                return

            trace = self._active_traces.pop(thought_id)
            trace.completed_at = completion_time

        # Sign the trace
        if self._signer.sign_trace(trace):
            self._traces_signed += 1
            component_types = [c.event_type for c in trace.components]
            logger.info(
                f"✅ TRACE COMPLETE #{self._traces_completed + 1}: {trace.trace_id} "
                f"with {len(trace.components)} components: {component_types}"
            )
        else:
            logger.warning(f"⚠️ Trace {trace.trace_id} completed but NOT signed (no key)")

        self._traces_completed += 1

        # Add to completed traces
        self._completed_traces.append(trace)

        # Queue trace as event for sending
        await self._queue_trace_event(trace)

    async def _queue_trace_event(self, trace: CompleteTrace) -> None:
        """Queue a completed trace for sending to CIRISLens.

        Args:
            trace: Completed trace to send
        """
        trace_event = {
            "event_type": "complete_trace",
            "trace": trace.to_dict(),
        }
        await self._queue_event(trace_event)

    def get_completed_traces(self) -> List[CompleteTrace]:
        """Get list of completed traces (for testing/export).

        Returns:
            List of completed traces
        """
        return self._completed_traces.copy()

    def get_latest_trace(self) -> Optional[CompleteTrace]:
        """Get the most recently completed trace.

        Returns:
            Most recent trace or None
        """
        if self._completed_traces:
            return self._completed_traces[-1]
        return None

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
        # Validate agent_id is a proper string (not a mock or other type)
        if not isinstance(agent_id, str) or not agent_id:
            logger.warning(f"Invalid agent_id type: {type(agent_id).__name__}, skipping")
            return
        self._agent_id_hash = self._anonymize_agent_id(agent_id)
        logger.debug(f"Agent ID hash set: {self._agent_id_hash}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics for telemetry.

        Returns:
            Dictionary of service metrics
        """
        return {
            "consent_given": self._consent_given,
            "trace_level": self._trace_level.value,
            "events_received": self._events_received,
            "events_sent": self._events_sent,
            "events_failed": self._events_failed,
            "events_queued": len(self._event_queue),
            "last_send_time": self._last_send_time.isoformat() if self._last_send_time else None,
            # Trace capture metrics
            "traces_active": len(self._active_traces),
            "traces_completed": self._traces_completed,
            "traces_signed": self._traces_signed,
            "signer_key_id": self._signer.key_id,
            "has_signing_key": self._signer.has_signing_key,
        }
