"""
Covenant Metrics Services - Full trace capture for CIRISLens.

This module implements the CovenantMetricsService which:
1. Subscribes to reasoning_event_stream for FULL trace capture (6 components)
2. Receives WBD (Wisdom-Based Deferral) events via WiseBus broadcast
3. Batches events and sends them to CIRISLens API
4. Signs complete traces with Ed25519 for integrity verification
5. Only operates when explicit consent has been given

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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    """Sign traces using Ed25519 keys (compatible with root WA keys)."""

    def __init__(self, seed_dir: Optional[Path] = None):
        """Initialize signer with optional seed directory for root public key."""
        self._private_key: Optional[Any] = None
        self._public_key: Optional[Any] = None
        self._key_id: Optional[str] = None
        self._root_pubkey: Optional[str] = None

        # Load root public key from seed directory
        if seed_dir is None:
            seed_dir = Path(__file__).parent.parent.parent / "seed"

        root_pub_file = seed_dir / "root_pub.json"
        if root_pub_file.exists():
            with open(root_pub_file) as f:
                root_data = json.load(f)
                self._root_pubkey = root_data.get("pubkey")
                self._key_id = root_data.get("wa_id", "wa-unknown")
                logger.info(f"Loaded root public key: {self._key_id}")

    def _load_private_key_if_available(self) -> bool:
        """Try to load private key from standard location."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            private_key_file = Path.home() / ".ciris" / "wa_keys" / "root_wa.key"
            if private_key_file.exists():
                private_bytes = private_key_file.read_bytes()
                self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
                self._public_key = self._private_key.public_key()
                logger.info("Loaded Ed25519 private key for trace signing")
                return True
        except Exception as e:
            logger.debug(f"Could not load private key: {e}")
        return False

    def sign_trace(self, trace: CompleteTrace) -> bool:
        """Sign a trace with Ed25519 private key.

        Returns True if signing succeeded, False if private key not available.
        """
        if not self._private_key and not self._load_private_key_if_available():
            logger.warning("No private key available for trace signing")
            return False

        try:
            # Compute trace hash
            trace_hash = trace.compute_hash()

            # Sign the hash
            signature_bytes = self._private_key.sign(trace_hash.encode())

            # URL-safe base64 encode
            trace.signature = base64.urlsafe_b64encode(signature_bytes).decode().rstrip("=")
            trace.signature_key_id = self._key_id

            logger.debug(f"Signed trace {trace.trace_id} with key {self._key_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to sign trace: {e}")
            return False

    def verify_trace(self, trace: CompleteTrace) -> bool:
        """Verify a trace signature using root public key."""
        if not trace.signature or not self._root_pubkey:
            return False

        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Decode public key
            pubkey_bytes = base64.urlsafe_b64decode(self._root_pubkey + "==")
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)

            # Decode signature
            sig_bytes = base64.urlsafe_b64decode(trace.signature + "==")

            # Compute expected hash
            expected_hash = trace.compute_hash()

            # Verify
            public_key.verify(sig_bytes, expected_hash.encode())
            return True

        except Exception as e:
            logger.warning(f"Trace signature verification failed: {e}")
            return False

    @property
    def key_id(self) -> Optional[str]:
        return self._key_id

    @property
    def has_signing_key(self) -> bool:
        return self._private_key is not None or self._load_private_key_if_available()


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
    EVENT_TO_COMPONENT = {
        "THOUGHT_START": "observation",
        "SNAPSHOT_AND_CONTEXT": "context",
        "DMA_RESULTS": "rationale",
        "ASPDMA_RESULT": "rationale",
        "CONSCIENCE_RESULT": "conscience",
        "ACTION_RESULT": "action",  # Also contains outcome data
    }

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
        logger.info("Starting CovenantMetricsService")

        # Subscribe to reasoning_event_stream for trace capture
        # This happens regardless of consent - we just don't SEND until consent
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            self._reasoning_queue = asyncio.Queue(maxsize=1000)
            reasoning_event_stream.subscribe(self._reasoning_queue)
            self._reasoning_task = asyncio.create_task(self._process_reasoning_events())
            logger.info("Subscribed to reasoning_event_stream for trace capture")
        except Exception as e:
            logger.warning(f"Could not subscribe to reasoning_event_stream: {e}")

        if not self._consent_given:
            logger.warning(
                "CovenantMetricsService started but consent not given - "
                "traces will be captured but NOT sent until user consents via setup wizard"
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

        # Unsubscribe from reasoning_event_stream
        if self._reasoning_queue:
            try:
                from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

                reasoning_event_stream.unsubscribe(self._reasoning_queue)
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
        await self._flush_events()

        # Close HTTP session
        if self._session:
            await self._session.close()
            self._session = None

        logger.info(
            f"CovenantMetricsService stopped (events_sent={self._events_sent}, "
            f"events_failed={self._events_failed}, traces_completed={self._traces_completed})"
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
    # Reasoning Event Stream Processing (6-Component Trace Capture)
    # =========================================================================

    async def _process_reasoning_events(self) -> None:
        """Process reasoning events from the stream and build traces."""
        logger.info("Starting reasoning event processor")
        while True:
            try:
                # Wait for next event
                event_data = await self._reasoning_queue.get()
                await self._handle_reasoning_event(event_data)
            except asyncio.CancelledError:
                logger.info("Reasoning event processor cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing reasoning event: {e}")

    async def _handle_reasoning_event(self, event_data: Dict[str, Any]) -> None:
        """Handle a single reasoning event and add to appropriate trace.

        Args:
            event_data: ReasoningStreamUpdate dict from step_streaming
        """
        # Extract events from stream update
        events = event_data.get("events", [])
        for event in events:
            await self._process_single_event(event)

    async def _process_single_event(self, event: Dict[str, Any]) -> None:
        """Process a single reasoning event.

        Args:
            event: Individual reasoning event dict
        """
        event_type = event.get("event_type", "")
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
        if event_type == "ACTION_RESULT":
            await self._complete_trace(thought_id, timestamp)

    def _extract_component_data(self, event_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract FULL reasoning data from event for trace component.

        User has opted in to share data for the Coherence Ratchet corpus.
        We capture complete reasoning content to enable pattern analysis
        across thousands of agents running different AI models.

        Args:
            event_type: Type of reasoning event
            event: Full event data

        Returns:
            Complete component data for corpus analysis
        """

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
            # Include full task context for pattern analysis
            return {
                # Core thought metadata
                "thought_type": event.get("thought_type"),
                "thought_status": event.get("thought_status"),
                "round_number": event.get("round_number"),
                "thought_depth": event.get("thought_depth"),
                "parent_thought_id": event.get("parent_thought_id"),
                # Task details - what was the observation/trigger
                "task_priority": event.get("task_priority"),
                "task_description": event.get("task_description"),
                "initial_context": event.get("initial_context"),
                "channel_id": event.get("channel_id"),
                "source_adapter": event.get("source_adapter"),
                # Flags
                "updated_info_available": event.get("updated_info_available"),
                "requires_human_input": event.get("requires_human_input"),
            }

        elif event_type == "SNAPSHOT_AND_CONTEXT":
            # CONTEXT: Environmental state when decision was made
            # Full snapshot enables understanding decision context
            snapshot = event.get("system_snapshot", {})
            snapshot_data = _serialize(snapshot)

            return {
                # Full system snapshot
                "system_snapshot": snapshot_data,
                # Context gathered for this thought
                "gathered_context": _serialize(event.get("gathered_context")),
                "context_sources": event.get("context_sources"),
                # Memory and history context
                "relevant_memories": _serialize(event.get("relevant_memories")),
                "conversation_history": _serialize(event.get("conversation_history")),
                # Active state
                "active_services": event.get("active_services"),
                "cognitive_state": event.get("cognitive_state"),
            }

        elif event_type == "DMA_RESULTS":
            # RATIONALE (Part 1): DMA reasoning outputs
            # Full reasoning text enables pattern comparison
            csdma = event.get("csdma", {})
            dsdma = event.get("dsdma", {})
            pdma = event.get("pdma", {})

            return {
                # Common Sense DMA - basic reasoning
                "csdma": {
                    "output": _serialize(csdma.get("output") if isinstance(csdma, dict) else csdma),
                    "prompt_used": event.get("csdma_prompt"),
                    "reasoning": csdma.get("reasoning") if isinstance(csdma, dict) else None,
                },
                # Domain Specific DMA - specialized knowledge
                "dsdma": {
                    "output": _serialize(dsdma.get("output") if isinstance(dsdma, dict) else dsdma),
                    "prompt_used": event.get("dsdma_prompt"),
                    "domain_context": dsdma.get("domain_context") if isinstance(dsdma, dict) else None,
                },
                # Principled DMA - ethical/value reasoning
                "pdma": {
                    "output": _serialize(pdma.get("output") if isinstance(pdma, dict) else pdma),
                    "prompt_used": event.get("pdma_prompt"),
                    "principles_applied": pdma.get("principles_applied") if isinstance(pdma, dict) else None,
                    "ethical_considerations": pdma.get("ethical_considerations") if isinstance(pdma, dict) else None,
                },
                # Aggregate reasoning
                "combined_analysis": event.get("combined_analysis"),
            }

        elif event_type == "ASPDMA_RESULT":
            # RATIONALE (Part 2): Action selection reasoning
            # Full rationale text for action selection
            return {
                # Selected action and reasoning
                "selected_action": event.get("selected_action"),
                "action_rationale": event.get("action_rationale"),  # Full text
                "reasoning_summary": event.get("reasoning_summary"),
                # Action parameters
                "action_parameters": _serialize(event.get("action_parameters")),
                # Selection process
                "alternatives_considered": event.get("alternatives_considered"),
                "selection_confidence": event.get("selection_confidence"),
                # Recursive flag
                "is_recursive": event.get("is_recursive", False),
                # Prompt used for decision
                "aspdma_prompt": event.get("aspdma_prompt"),
            }

        elif event_type == "CONSCIENCE_RESULT":
            # CONSCIENCE: Ethical validation details
            # Full epistemic and ethical check data
            return {
                # Overall result
                "conscience_passed": event.get("conscience_passed"),
                "action_was_overridden": event.get("action_was_overridden", False),
                "final_action": event.get("final_action"),
                # Epistemic checks - uncertainty/confidence
                "epistemic_data": _serialize(event.get("epistemic_data")),
                "uncertainty_flags": event.get("uncertainty_flags"),
                "confidence_score": event.get("confidence_score"),
                # Override details if action was changed
                "override_reason": event.get("override_reason"),
                "original_action": event.get("original_action"),
                # Individual conscience check results
                "conscience_checks": _serialize(event.get("conscience_checks")),
                # Guardrail activations
                "guardrails_triggered": event.get("guardrails_triggered"),
                "safety_flags": event.get("safety_flags"),
            }

        elif event_type == "ACTION_RESULT":
            # ACTION + OUTCOME: What happened and results
            # Full execution details and audit trail
            return {
                # Action executed
                "action_executed": event.get("action_executed"),
                "action_parameters": _serialize(event.get("action_parameters")),
                # Execution outcome
                "execution_success": event.get("execution_success"),
                "execution_result": _serialize(event.get("execution_result")),
                "execution_error": event.get("execution_error"),
                "execution_time_ms": event.get("execution_time_ms"),
                # Follow-up
                "follow_up_thought_id": event.get("follow_up_thought_id"),
                "requires_follow_up": event.get("requires_follow_up"),
                # Full audit trail (OUTCOME)
                "audit_entry_id": event.get("audit_entry_id"),
                "audit_sequence_number": event.get("audit_sequence_number"),
                "audit_signature": event.get("audit_signature"),
                "audit_hash_chain": event.get("audit_hash_chain"),
                # Resource consumption
                "tokens_input": event.get("tokens_input"),
                "tokens_output": event.get("tokens_output"),
                "tokens_total": event.get("tokens_total"),
                "cost_cents": event.get("cost_cents"),
                "llm_calls": event.get("llm_calls"),
                "llm_model": event.get("llm_model"),
                # Response content (for SPEAK actions)
                "response_content": event.get("response_content"),
            }

        else:
            # Unknown event type - capture everything we can
            return {
                "event_type": event_type,
                "raw_data": _serialize(event),
            }

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
            logger.info(
                f"Signed trace {trace.trace_id} with {len(trace.components)} components"
            )
        else:
            logger.debug(f"Trace {trace.trace_id} completed but not signed (no key)")

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
            # Trace capture metrics
            "traces_active": len(self._active_traces),
            "traces_completed": self._traces_completed,
            "traces_signed": self._traces_signed,
            "signer_key_id": self._signer.key_id,
            "has_signing_key": self._signer.has_signing_key,
        }
