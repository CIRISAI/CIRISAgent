"""
Accord Metrics Services - Trace capture for CIRISLens scoring.

This module implements the AccordMetricsService which:
1. Subscribes to reasoning_event_stream for trace capture (8 event types)
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
3. Rationale - DMA reasoning analysis (DMA_RESULTS, IDMA_RESULT, ASPDMA_RESULT, TSASPDMA_RESULT)
4. Conscience - Ethical validation (CONSCIENCE_RESULT)
5. Action - Final action taken (ACTION_RESULT)
6. Outcome - Execution results and audit (ACTION_RESULT audit data)

Event Types (8 total - 7 core + 1 optional):
- THOUGHT_START: Thought begins processing
- SNAPSHOT_AND_CONTEXT: System snapshot + gathered context
- DMA_RESULTS: 3 DMA results (CSDMA, DSDMA, PDMA)
- IDMA_RESULT: Identity DMA fragility check (always emitted)
- ASPDMA_RESULT: Selected action + rationale
- TSASPDMA_RESULT: Tool-Specific ASPDMA (optional, when TOOL selected)
- CONSCIENCE_RESULT: Conscience evaluation + final action
- ACTION_RESULT: Action execution outcome + audit trail
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ciris_engine.schemas.services.authority_core import DeferralRequest
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)
TRACE_SCHEMA_VERSION = "2.7.0"


def _get_metrics_env(name: str, default: str = "") -> str:
    """Get env var with backward compatibility for old COVENANT naming.

    Checks CIRIS_ACCORD_METRICS_{name} first, falls back to CIRIS_COVENANT_METRICS_{name}.
    This allows existing .env files to continue working after the rename.
    """
    new_key = f"CIRIS_ACCORD_METRICS_{name}"
    old_key = f"CIRIS_COVENANT_METRICS_{name}"

    value = os.environ.get(new_key)
    if value is not None:
        return value

    value = os.environ.get(old_key)
    if value is not None:
        logger.info(f"Using legacy env var {old_key} - please migrate to {new_key}")
        return value

    return default


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


def _strip_empty(obj: Any) -> Any:
    """Recursively strip None, empty strings, empty lists, empty dicts to reduce payload size."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            stripped = _strip_empty(v)
            # Keep the value if it's not empty (0 and False are valid values)
            if stripped is not None and stripped != "" and stripped != [] and stripped != {}:
                result[k] = stripped
        return result
    elif isinstance(obj, list):
        return [_strip_empty(item) for item in obj if item is not None]
    return obj


@dataclass
class SimpleCapabilities:
    """Simple capabilities container for duck-typing with WiseBus.

    The supported_domains field declares which DomainCategory values this
    service can handle. WiseBus filters services by domain_hint when routing
    deferrals to ensure only qualified handlers receive domain-specific requests.
    """

    actions: List[str]
    scopes: List[str]
    supported_domains: List[str] = field(default_factory=list)  # DomainCategory values


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
    # Trace level determines what data is included - MUST be part of signature
    trace_level: Optional[str] = None
    trace_schema_version: str = TRACE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Uses _strip_empty on component data to match what was signed.
        """
        return {
            "trace_id": self.trace_id,
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "agent_id_hash": self.agent_id_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "trace_level": self.trace_level,
            "trace_schema_version": self.trace_schema_version,
            "components": [
                {
                    "component_type": c.component_type,
                    "data": _strip_empty(c.data),
                    "event_type": c.event_type,
                    "timestamp": c.timestamp,
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
            "trace_level": self.trace_level,
            "trace_schema_version": self.trace_schema_version,
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
    ensuring the same key is used for both audit trail signing and accord metrics traces.

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

        The signed payload MUST byte-for-byte match what CIRISLens verifies
        against (api/accord_api.py::verify_trace_signature). Lens computes:

            components_data = [strip_empty(c.model_dump()) for c in trace.components]
            signed_payload = {"components": components_data, "trace_level": trace_level}
            message = json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))

        trace_schema_version ships in the trace envelope (to_dict) for lens
        dashboards but is NOT in the signed bytes — lens doesn't include it
        in its canonical payload, so adding it on the agent side breaks
        signature verification for every trace.

        Returns True if signing succeeded, False if key not available.
        """
        if not self._ensure_unified_key() or self._unified_key is None:
            logger.warning("No unified signing key available for trace signing")
            return False

        try:
            # Build the canonical message. Match lens's strip_empty semantics:
            # dump the full component (component_type, event_type, timestamp,
            # data) then recursively drop None / ""  / [] / {}.
            components_list = [
                _strip_empty(
                    {
                        "component_type": c.component_type,
                        "data": c.data,
                        "event_type": c.event_type,
                        "timestamp": c.timestamp.isoformat()
                        if hasattr(c.timestamp, "isoformat")
                        else str(c.timestamp),
                    }
                )
                for c in trace.components
            ]

            signed_payload = {
                "components": components_list,
                "trace_level": trace.trace_level,
            }

            # Compact JSON: sort_keys=True, no extra whitespace, UTF-8 encoded
            message = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

            # Log hash for debugging signature verification mismatches (no content preview for privacy)
            message_hash = hashlib.sha256(message).hexdigest()
            logger.info(
                f"[SIGN_TRACE] trace={trace.trace_id} level={trace.trace_level} "
                f"len={len(message)} hash={message_hash[:16]}"
            )

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

        MUST match the canonical payload used in sign_trace — see that
        method's docstring. trace_schema_version is NOT included here.
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
                _strip_empty(
                    {
                        "component_type": c.component_type,
                        "data": c.data,
                        "event_type": c.event_type,
                        "timestamp": c.timestamp.isoformat()
                        if hasattr(c.timestamp, "isoformat")
                        else str(c.timestamp),
                    }
                )
                for c in trace.components
            ]

            signed_payload = {
                "components": components_list,
                "trace_level": trace.trace_level,
            }
            message = json.dumps(signed_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

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


class AccordMetricsService:
    """
    Accord compliance metrics service for CIRISLens.

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
        "IDMA_RESULT": "rationale",  # Identity DMA fragility check
        "ASPDMA_RESULT": "rationale",
        "TSASPDMA_RESULT": "rationale",  # DEPRECATED legacy; replaced by VERB_SECOND_PASS_RESULT
        "VERB_SECOND_PASS_RESULT": "verb_second_pass",  # Generic verb-specific second pass
        "CONSCIENCE_RESULT": "conscience",
        "ACTION_RESULT": "action",  # Also contains outcome data
        "LLM_CALL": "llm_call",  # Sub-pipeline: per-provider-call observation
        # Also handle full enum names from streaming
        "ReasoningEvent.THOUGHT_START": "observation",
        "ReasoningEvent.SNAPSHOT_AND_CONTEXT": "context",
        "ReasoningEvent.DMA_RESULTS": "rationale",
        "ReasoningEvent.IDMA_RESULT": "rationale",
        "ReasoningEvent.ASPDMA_RESULT": "rationale",
        "ReasoningEvent.TSASPDMA_RESULT": "rationale",
        "ReasoningEvent.VERB_SECOND_PASS_RESULT": "verb_second_pass",
        "ReasoningEvent.CONSCIENCE_RESULT": "conscience",
        "ReasoningEvent.ACTION_RESULT": "action",
        "ReasoningEvent.LLM_CALL": "llm_call",
        # Commons Credits trace events (bilateral verified interactions)
        "DEFERRAL_ROUTED": "deferral_routed",
        "DEFERRAL_RECEIVED": "deferral_received",
        "DEFERRAL_RESOLVED": "deferral_resolved",
        "GRATITUDE_SIGNALED": "gratitude_signaled",
        "CREDIT_GENERATED": "credit_generated",
    }

    def __init__(
        self,
        config: Optional[JSONDict] = None,
        agent_id: Optional[str] = None,
        **kwargs: Any,  # Accept extra params from service_initializer (bus_manager, etc.)
    ) -> None:
        """Initialize AccordMetricsService.

        Args:
            config: Configuration dict with consent settings
            agent_id: Agent identifier (will be hashed for privacy)
            **kwargs: Additional params from service_initializer (ignored)
        """
        self._config = config or {}

        # Adapter instance ID for logging (helps distinguish multiple instances)
        self._adapter_instance_id = str(self._config.get("adapter_id", "default"))

        # Set agent_id if provided during construction
        self._initial_agent_id = agent_id

        # Consent state - check env var first for QA testing
        # Uses backward-compatible helper that checks both ACCORD and legacy COVENANT env vars
        env_consent = _get_metrics_env("CONSENT", "").lower() == "true"
        env_timestamp = _get_metrics_env("CONSENT_TIMESTAMP") or None

        config_consent = bool(self._config.get("consent_given", False))
        self._consent_given = config_consent or env_consent

        # Consent timestamp - REQUIRED when consent is given, default to current time if not provided
        self._consent_timestamp: Optional[str] = None
        raw_timestamp = self._config.get("consent_timestamp") or env_timestamp
        if raw_timestamp is not None:
            self._consent_timestamp = str(raw_timestamp)
        elif self._consent_given:
            # CRITICAL: If consent is given but no timestamp provided, use current time
            # Without a timestamp, CIRISLens will reject all traces
            self._consent_timestamp = datetime.now(timezone.utc).isoformat()
            logger.warning(
                f"⚠️ Consent given but no timestamp provided. Using current time: {self._consent_timestamp}. "
                "Set CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP for consistent timestamps across restarts."
            )

        if env_consent and not config_consent:
            logger.info("✅ CONSENT enabled via environment variable CIRIS_ACCORD_METRICS_CONSENT")

        # Endpoint configuration - check env var first for QA testing
        env_endpoint = _get_metrics_env("ENDPOINT") or None
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
        env_interval = _get_metrics_env("FLUSH_INTERVAL") or None
        raw_interval = self._config.get("flush_interval_seconds")
        if env_interval is not None:
            self._flush_interval: float = float(env_interval)
        elif raw_interval is not None and isinstance(raw_interval, (int, float, str)):
            self._flush_interval = float(raw_interval)
        else:
            self._flush_interval = 60.0

        # Trace detail level - per-adapter config takes precedence over env var
        # This allows loading multiple adapters with different trace levels
        # Default is GENERIC (numeric scores only) for ciris.ai/ciris-scoring
        env_level = _get_metrics_env("TRACE_LEVEL", "").lower()
        config_level = str(self._config.get("trace_level", "")).lower()
        # Config takes precedence (allows per-adapter override), then env, then default
        level_str = config_level or env_level or "generic"
        level_source = "config" if config_level else ("env" if env_level else "default")
        try:
            self._trace_level = TraceDetailLevel(level_str)
        except ValueError:
            logger.warning(f"Invalid trace_level '{level_str}', defaulting to 'generic'")
            self._trace_level = TraceDetailLevel.GENERIC
            level_source = "default (invalid)"

        logger.info(
            f"📊 [{self._adapter_instance_id}] Trace detail level: {self._trace_level.value} "
            f"(source={level_source}, config='{config_level}', env='{env_level}')"
        )

        # Early warning correlation metadata (optional, anonymous)
        self._deployment_region: str = str(self._config.get("deployment_region", "") or "")
        self._deployment_type: str = str(self._config.get("deployment_type", "") or "")
        self._agent_role: str = str(self._config.get("agent_role", "") or "")
        self._agent_template: str = str(self._config.get("agent_template", "") or "")

        # User location (only included if user explicitly consented via PREFERENCES step)
        # Read from environment variables set during setup
        env_share_location = os.environ.get("CIRIS_SHARE_LOCATION_IN_TRACES", "").lower() == "true"
        self._share_location_in_traces: bool = env_share_location
        self._user_location: str = os.environ.get("CIRIS_USER_LOCATION", "") if env_share_location else ""
        self._user_timezone: str = os.environ.get("CIRIS_USER_TIMEZONE", "") if env_share_location else ""
        # Coordinates in ISO 6709 decimal degrees format
        lat_str = os.environ.get("CIRIS_USER_LATITUDE", "") if env_share_location else ""
        lon_str = os.environ.get("CIRIS_USER_LONGITUDE", "") if env_share_location else ""
        self._user_latitude: Optional[float] = None
        self._user_longitude: Optional[float] = None
        if lat_str:
            try:
                self._user_latitude = float(lat_str)
            except ValueError:
                logger.warning("Invalid CIRIS_USER_LATITUDE value: %s", lat_str)
        if lon_str:
            try:
                self._user_longitude = float(lon_str)
            except ValueError:
                logger.warning("Invalid CIRIS_USER_LONGITUDE value: %s", lon_str)
        if self._share_location_in_traces and self._user_location:
            coords = f" ({self._user_latitude}, {self._user_longitude})" if self._user_latitude else ""
            logger.info(f"   Location sharing enabled: {self._user_location}{coords}")

        # Event queue and batching
        self._event_queue: List[Dict[str, Any]] = []
        self._queue_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None

        # HTTP client session
        self._session: Optional[aiohttp.ClientSession] = None

        # Metrics (session counters)
        self._events_received = 0
        self._events_sent = 0
        self._events_failed = 0
        self._traces_completed = 0
        self._traces_signed = 0
        self._last_send_time: Optional[datetime] = None

        # Persisted cumulative total from prior sessions (loaded in start())
        self._persisted_events_sent = 0

        # Agent ID for anonymization (set during start)
        self._agent_id_hash: Optional[str] = None
        # Agent name (human-readable identifier for traces at all levels)
        self._agent_name: Optional[str] = str(self._config.get("agent_name", "") or "")

        # Reasoning event stream subscription
        self._reasoning_queue: Optional[asyncio.Queue[Any]] = None
        self._reasoning_task: Optional[asyncio.Task[None]] = None

        # Active traces being built (keyed by thought_id)
        self._active_traces: Dict[str, CompleteTrace] = {}
        self._traces_lock = asyncio.Lock()

        # Per-(thought_id, event_type) attempt index counter. Computed at
        # broadcast-receive time and injected into the event dict so the lens
        # has stable monotonic ordering for events that fire N times per
        # thought (LLM_CALL, RECURSIVE_ASPDMA, RECURSIVE_CONSCIENCE,
        # CONSCIENCE_RESULT, DMA_RESULTS bounce alternatives). For events that
        # fire once per thought the index is always 0. Single-subscriber FIFO
        # delivery from reasoning_event_stream guarantees broadcast-order
        # arrival, so the counter increments produce a stable index.
        # See FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.1 attempt_index semantics.
        self._attempt_counters: Dict[Tuple[str, str], int] = {}

        # Completed traces ready for sending
        self._completed_traces: List[CompleteTrace] = []

        # Trace signer
        self._signer = Ed25519TraceSigner()

        logger.info(
            f"AccordMetricsService initialized (consent_given={self._consent_given}, "
            f"endpoint={self._endpoint_url}, signer_key={self._signer.key_id})"
        )

    def _compute_instance_hash(self, fallback_id: Optional[str] = None) -> str:
        """Compute unique instance hash from signing key.

        Uses the signer's public key to generate a hash that is unique per agent instance,
        not just per template name. This ensures that multiple instances of the same
        template (e.g., 30 "Ally" agents) have distinct agent_id_hash values.

        Args:
            fallback_id: If signing key unavailable, hash this ID instead (for tests)

        Returns:
            SHA-256 hash of signing key's public key (first 16 chars),
            or hash of fallback_id if provided and no signing key,
            or "unknown" if neither available.
        """
        if self._signer and self._signer.has_signing_key:
            try:
                unified_key = self._signer._unified_key
                if unified_key is not None:
                    pubkey_bytes = unified_key.public_key_bytes
                    return hashlib.sha256(pubkey_bytes).hexdigest()[:16]
            except Exception as e:
                logger.warning(f"Could not compute instance hash from signing key: {e}")

        # Fallback for tests/environments without signing key
        if fallback_id:
            return hashlib.sha256(fallback_id.encode()).hexdigest()[:16]

        return "unknown"

    def _anonymize_agent_id(self, agent_id: str) -> str:
        """Hash agent ID for privacy - prefers signing key, falls back to agent_id.

        In production, uses the signing key's public key for uniqueness.
        In tests (no signing key), falls back to hashing the agent_id.

        Args:
            agent_id: Raw agent identifier (template name, used as fallback)

        Returns:
            SHA-256 hash (first 16 chars) - from signing key if available, else from agent_id
        """
        return self._compute_instance_hash(fallback_id=agent_id)

    def get_capabilities(self) -> SimpleCapabilities:
        """Return service capabilities.

        Returns:
            SimpleCapabilities with send_deferral to receive WBD events
        """
        return SimpleCapabilities(
            actions=["send_deferral", "accord_metrics"],
            scopes=["accord_compliance"],
        )

    def _load_persisted_events_total(self) -> int:
        """Load persisted cumulative events_sent from previous sessions."""
        try:
            from ciris_engine.logic.persistence.models.graph import get_graph_node
            from ciris_engine.schemas.services.graph_core import GraphScope

            node = get_graph_node("accord_metrics/events_total", GraphScope.LOCAL)
            if node and node.attributes:
                attrs = node.attributes
                # Handle both dict and object attribute access
                if isinstance(attrs, dict):
                    value = attrs.get("events_sent_total", 0)
                else:
                    value = getattr(attrs, "events_sent_total", 0)
                # Ensure we have a numeric type for int()
                if isinstance(value, (int, float)):
                    return int(value)
                elif isinstance(value, str) and value.isdigit():
                    return int(value)
        except Exception as e:
            logger.debug(f"Could not load persisted events total: {e}")
        return 0

    def _persist_events_total(self) -> None:
        """Persist cumulative events_sent to graph for survival across restarts."""
        try:
            from ciris_engine.logic.persistence.models.graph import add_graph_node
            from ciris_engine.logic.services.lifecycle.time.service import TimeService
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            total = self._persisted_events_sent + self._events_sent
            node = GraphNode(
                id="accord_metrics/events_total",
                type=NodeType.CONFIG,
                scope=GraphScope.LOCAL,
                attributes={
                    "events_sent_total": total,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
                updated_by="accord_metrics_service",
                updated_at=datetime.now(timezone.utc),
            )
            time_service = TimeService()
            add_graph_node(node, time_service, None)
        except Exception as e:
            logger.debug(f"Could not persist events total: {e}")

    async def start(self) -> None:
        """Start the service and initialize HTTP client."""
        # Load persisted event count from previous sessions
        self._persisted_events_sent = self._load_persisted_events_total()
        if self._persisted_events_sent:
            logger.info(f"   Loaded persisted events total: {self._persisted_events_sent}")

        logger.info("=" * 70)
        logger.info("🚀 ACCORD METRICS SERVICE STARTING")
        logger.info(f"   Consent given: {self._consent_given}")
        logger.info(f"   Consent timestamp: {self._consent_timestamp or 'NOT SET (traces will be rejected!)'}")
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

        # Initialize HTTP session and start flush task
        self._initialize_http_session()
        self._flush_task = asyncio.create_task(self._periodic_flush())

        logger.info("=" * 70)
        logger.info(f"✅ ACCORD METRICS SERVICE READY")
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
        logger.info("🛑 ACCORD METRICS SERVICE STOPPING")
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
                pass  # Expected - we initiated the cancellation

        # Cancel flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass  # Expected - we initiated the cancellation

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
        logger.info("📊 ACCORD METRICS FINAL STATS")
        logger.info(f"   Traces completed: {self._traces_completed}")
        logger.info(f"   Events sent: {self._events_sent}")
        logger.info(f"   Events failed: {self._events_failed}")
        logger.info(f"   Events received: {self._events_received}")
        logger.info("=" * 70)

    async def _periodic_flush(self) -> None:
        """Periodically flush events even if batch is not full."""
        try:
            while True:
                try:
                    await asyncio.sleep(self._flush_interval)
                    await self._flush_events()
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise  # Re-raise to exit cleanly
                    logger.error(
                        f"Error in periodic flush: {type(e).__name__}: {e!r}",
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            pass  # Clean exit on cancellation

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

        logger.info(
            f"📤 [{self._adapter_instance_id}] FLUSHING {len(events_to_send)} events to {self._endpoint_url} (level={self._trace_level.value})"
        )

        try:
            await self._send_events_batch(events_to_send)
            self._events_sent += len(events_to_send)
            self._last_send_time = datetime.now(timezone.utc)
            logger.info(
                f"✅ [{self._adapter_instance_id}] FLUSH SUCCESS: {len(events_to_send)} events sent "
                f"(session: {self._events_sent}, lifetime: {self._persisted_events_sent + self._events_sent}, level={self._trace_level.value})"
            )
            # Persist cumulative total to survive restarts
            self._persist_events_total()
        except asyncio.TimeoutError as e:
            # Empty str() on TimeoutError silently swallowed the cause for months.
            # Log type + endpoint so incident capture records an actionable message.
            self._events_failed += len(events_to_send)
            logger.error(
                f"❌ [{self._adapter_instance_id}] FLUSH FAILED - Timeout ({type(e).__name__}) "
                f"posting {len(events_to_send)} events to {self._endpoint_url}/accord/events "
                f"(connect=10s, read=20s, total=30s); level={self._trace_level.value}"
            )
            async with self._queue_lock:
                if len(self._event_queue) < self._batch_size * 10:
                    self._event_queue = events_to_send + self._event_queue
                    logger.info(f"   Re-queued {len(events_to_send)} events for retry")
        except Exception as e:
            self._events_failed += len(events_to_send)
            logger.error(
                f"❌ [{self._adapter_instance_id}] FLUSH FAILED: {len(events_to_send)} events: "
                f"{type(e).__name__}: {e!r}",
                exc_info=True,
            )
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

        # CRITICAL: Require explicit consent_timestamp - server returns 422 without it
        if not self._consent_timestamp:
            raise RuntimeError(
                "Cannot send events: consent_timestamp is not set. "
                "Set CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP env var or provide consent_timestamp in config."
            )

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
        # Include user location/timezone if explicitly consented via PREFERENCES step
        if self._share_location_in_traces:
            if self._user_location:
                correlation_metadata["user_location"] = self._user_location
            if self._user_timezone:
                correlation_metadata["user_timezone"] = self._user_timezone
            # Include coordinates in ISO 6709 decimal degrees format
            if self._user_latitude is not None:
                correlation_metadata["user_latitude"] = str(self._user_latitude)
            if self._user_longitude is not None:
                correlation_metadata["user_longitude"] = str(self._user_longitude)

        payload: Dict[str, Any] = {
            "events": events,
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "consent_timestamp": self._consent_timestamp,
            "trace_level": self._trace_level.value,
            "trace_schema_version": TRACE_SCHEMA_VERSION,
        }
        # Only add correlation metadata if user opted in to any fields
        if correlation_metadata:
            payload["correlation_metadata"] = correlation_metadata

        url = f"{self._endpoint_url}/accord/events"
        logger.info(
            f"📡 [{self._adapter_instance_id}] POST {url} ({len(events)} events, trace_level={self._trace_level.value})"
        )

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
            description = f"Agent key for accord metrics traces"
            if self._agent_template:
                description = f"Agent key ({self._agent_template})"

            payload = unified_key.get_registration_payload(description)

            # Store registered key ID for comparison during signing
            self._registered_key_id = payload["key_id"]

            url = f"{self._endpoint_url}/accord/public-keys"

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
        # Include user location/timezone if explicitly consented via PREFERENCES step
        if self._share_location_in_traces:
            if self._user_location:
                correlation_metadata["user_location"] = self._user_location
            if self._user_timezone:
                correlation_metadata["user_timezone"] = self._user_timezone
            # Include coordinates in ISO 6709 decimal degrees format
            if self._user_latitude is not None:
                correlation_metadata["user_latitude"] = str(self._user_latitude)
            if self._user_longitude is not None:
                correlation_metadata["user_longitude"] = str(self._user_longitude)

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

        # Add connectivity component. agent_name is included so lens can
        # self-identify the agent alongside the hashed agent_id (the bare hash
        # by itself makes triage in lens dashboards hard).
        connectivity_trace.components.append(
            TraceComponent(
                component_type="connectivity",
                event_type=event_type,
                timestamp=timestamp,
                data={
                    "version": "1.8.5",
                    "trace_level": self._trace_level.value,
                    "agent_name": self._agent_name or "",
                    "agent_template": self._agent_template or "",
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
        url = f"{self._endpoint_url}/accord/events"

        try:
            logger.info("=" * 70)
            logger.info(f"📡 SENDING CONNECTED EVENT to {url}")
            logger.info(f"   Event type: {event_type}")
            logger.info(f"   Agent hash: {self._agent_id_hash}")

            # CRITICAL: Require explicit consent_timestamp
            if not self._consent_timestamp:
                logger.error("❌ Cannot send connected event: consent_timestamp is not set")
                logger.error("   Set CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP env var")
                return

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
            logger.error(f"❌ CONNECTED EVENT FAILED - Cannot reach server: {type(e).__name__}: {e!r}")
            logger.error(f"   Endpoint: {url}")
            logger.error("   Check network connectivity and endpoint URL")
            logger.error("=" * 70)

        except asyncio.TimeoutError as e:
            # aiohttp raises asyncio.TimeoutError on ClientTimeout; these have no
            # str() representation, so surface the type + endpoint so the incident
            # log actually identifies what hung.
            logger.error("=" * 70)
            logger.error(
                f"❌ CONNECTED EVENT FAILED - Timeout ({type(e).__name__}) posting to {url}"
            )
            logger.error("   Server did not respond within client timeout (connect=10s, read=20s)")
            logger.error("=" * 70)

        except Exception as e:
            logger.error("=" * 70)
            logger.error(
                f"❌ CONNECTED EVENT FAILED - Unexpected error: {type(e).__name__}: {e!r}",
                exc_info=True,
            )
            logger.error(f"   Endpoint: {url}")
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
                logger.error(
                    f"Failed to send batch ({len(events_to_send)} events) to "
                    f"{self._endpoint_url}/accord/events: {type(e).__name__}: {e!r}",
                    exc_info=True,
                )

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

        try:
            while True:
                try:
                    # Wait for next event with timeout to check for cancellation
                    event_data = await asyncio.wait_for(self._reasoning_queue.get(), timeout=1.0)
                    events_processed += 1
                    logger.info(f"📥 RECEIVED reasoning event #{events_processed}: {type(event_data).__name__}")
                    await self._handle_reasoning_event(event_data)
                except asyncio.TimeoutError:
                    # No event, just continue waiting
                    continue
                except asyncio.CancelledError:
                    raise  # Re-raise to exit cleanly
                except Exception as e:
                    # Check if event loop is gone (e.g., during shutdown/test teardown)
                    err_str = str(e).lower()
                    if "no running event loop" in err_str or "event loop is closed" in err_str:
                        logger.debug("Event loop closed, stopping reasoning event processor")
                        break
                    logger.error(f"Error processing reasoning event: {e}")
        except asyncio.CancelledError:
            logger.info(f"Reasoning event processor cancelled (processed {events_processed} events)")

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

        # Compute attempt_index — monotonic per (thought_id, event_type).
        # Single-subscriber FIFO from reasoning_event_stream preserves
        # broadcast order; the counter increments produce a stable index
        # the lens can use to order rows for events that fire multiple
        # times per thought (LLM_CALL, RECURSIVE_*, CONSCIENCE_RESULT, DMA
        # bounce alternatives). Inject into the event dict so the
        # downstream _extract_component_data builders pick it up via
        # event.get("attempt_index", 0).
        attempt_key = (thought_id, event_type)
        attempt_index = self._attempt_counters.get(attempt_key, 0)
        self._attempt_counters[attempt_key] = attempt_index + 1
        event["attempt_index"] = attempt_index

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
        # Always carry attempt_index forward so the lens row writer sees it
        # uniformly across event types (single-emit events have 0 here, which
        # is informative — confirms the event is the first occurrence).
        component_data["attempt_index"] = attempt_index

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
        logger.debug(f"[TRACE_EXTRACT] {event_type}: level={level.value}, is_detailed={is_detailed}, is_full={is_full}")

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
            # FULL: Add description text and thought content
            if is_full:
                data["task_description"] = event.get("task_description")
                data["initial_context"] = event.get("initial_context")
                # Truncate thought_content to 500 chars for privacy/bandwidth
                thought_content = event.get("thought_content")
                if thought_content:
                    data["thought_content"] = thought_content[:500] if len(thought_content) > 500 else thought_content
            return data

        elif event_type == "SNAPSHOT_AND_CONTEXT":
            # CONTEXT: Environmental state when decision was made
            # Extract system_snapshot which contains the context data
            snapshot = event.get("system_snapshot", {})
            if hasattr(snapshot, "model_dump"):
                snapshot = snapshot.model_dump()

            # Extract verify_attestation context (REQUIRED at all levels per FSD-001)
            verify_attestation = snapshot.get("verify_attestation", {})
            if hasattr(verify_attestation, "model_dump"):
                verify_attestation = verify_attestation.model_dump()

            # Build attestation context string (same format everywhere)
            attestation_context = None
            if verify_attestation:
                attestation_level = verify_attestation.get("attestation_level", 0)
                attestation_summary = verify_attestation.get("attestation_summary", "")
                key_status = verify_attestation.get("key_status", "none")
                disclosure_text = verify_attestation.get("disclosure_text", "")
                disclosure_severity = verify_attestation.get("disclosure_severity", "info")
                ed25519_fingerprint = verify_attestation.get("ed25519_fingerprint")
                hardware_backed = verify_attestation.get("hardware_backed", False)
                key_storage_mode = verify_attestation.get("key_storage_mode")

                # Build the same context string used in LLM context
                context_lines = [f"CIRIS VERIFY ATTESTATION: {attestation_summary}"]
                if key_status != "none":
                    key_info = f"Key: {key_status}"
                    if ed25519_fingerprint:
                        key_info += f" (fingerprint: {ed25519_fingerprint[:16]}...)"
                    if hardware_backed:
                        key_info += f" [HARDWARE-BACKED]"
                    else:
                        key_info += f" [SOFTWARE: {key_storage_mode or 'default'}]"
                    context_lines.append(key_info)
                if disclosure_text:
                    severity_prefix = {"critical": "⚠️ CRITICAL", "warning": "⚠️ WARNING"}.get(
                        disclosure_severity.lower(), "ℹ️ NOTICE"
                    )
                    context_lines.append(f"{severity_prefix}: {disclosure_text}")
                attestation_context = "\n".join(context_lines)

            # GENERIC: Minimal - agent_name + cognitive state + attestation context
            # agent_name is REQUIRED at all 3 levels for CIRISLens correlation
            # attestation_context is REQUIRED at all 3 levels per FSD-001
            # cognitive_state might be at top level or in snapshot
            cognitive_state = event.get("cognitive_state") or snapshot.get("cognitive_state")
            data = {
                "agent_name": self._agent_name,
                "cognitive_state": cognitive_state,
                # CIRISVerify attestation - REQUIRED at all levels
                "attestation_context": attestation_context,
                "attestation_level": verify_attestation.get("attestation_level", 0) if verify_attestation else 0,
                "attestation_status": (
                    verify_attestation.get("attestation_status", "not_attempted")
                    if verify_attestation
                    else "not_attempted"
                ),
                "disclosure_severity": (
                    verify_attestation.get("disclosure_severity", "info") if verify_attestation else "info"
                ),
                # Per-check booleans from VerifyAttestationContext. These are
                # populated even in community mode (where max_level is 0 because
                # not every check passes) — each individual check still carries
                # independent signal, and each is near-zero-correlation with the
                # reasoning stack. Emit at GENERIC level so CIRISLens always has
                # the hardware-integrity dimensions available for k_eff.
                "binary_ok": verify_attestation.get("binary_ok") if verify_attestation else None,
                "env_ok": verify_attestation.get("env_ok") if verify_attestation else None,
                "registry_ok": verify_attestation.get("registry_ok") if verify_attestation else None,
                "file_integrity_ok": verify_attestation.get("file_integrity_ok") if verify_attestation else None,
                "audit_ok": verify_attestation.get("audit_ok") if verify_attestation else None,
                "play_integrity_ok": verify_attestation.get("play_integrity_ok") if verify_attestation else None,
                "hardware_backed": verify_attestation.get("hardware_backed") if verify_attestation else None,
            }
            # Counts are privacy-safe (no content, just cardinality) and carry
            # per-thought diversity signal — emit at GENERIC so they're always
            # available for k_eff analysis, don't gate behind DETAILED.
            relevant_memories = event.get("relevant_memories") or snapshot.get("relevant_memories")
            conversation_history = event.get("conversation_history") or snapshot.get("conversation_history")
            if isinstance(relevant_memories, list):
                data["memory_count"] = len(relevant_memories)
            elif isinstance(conversation_history, list):
                data["memory_count"] = len(conversation_history)
            else:
                data["memory_count"] = 0
            context_enrichment = snapshot.get("context_enrichment_results", {})
            data["context_tokens"] = len(context_enrichment) if isinstance(context_enrichment, dict) else 0

            # DETAILED: Add service list, system health info, and key details
            # (these can carry identifying info — service names, key ids,
            # hardware type — so gate behind DETAILED rather than GENERIC).
            if is_detailed:
                data["active_services"] = event.get("active_services") or snapshot.get("active_services")
                data["context_sources"] = event.get("context_sources") or snapshot.get("context_sources")
                data["service_health"] = event.get("service_health") or snapshot.get("service_health")
                data["agent_version"] = event.get("agent_version") or snapshot.get("agent_version")
                data["circuit_breaker_status"] = event.get("circuit_breaker_status") or snapshot.get(
                    "circuit_breaker_status"
                )
                # Key signature details (identifying, so DETAILED not GENERIC)
                if verify_attestation:
                    data["key_status"] = verify_attestation.get("key_status")
                    data["key_id"] = verify_attestation.get("key_id")
                    data["ed25519_fingerprint"] = verify_attestation.get("ed25519_fingerprint")
                    data["key_storage_mode"] = verify_attestation.get("key_storage_mode")
                    data["hardware_type"] = verify_attestation.get("hardware_type")
                    data["verify_version"] = verify_attestation.get("verify_version")
            # FULL: Add complete snapshot and context. This is for managed
            # agents where the operator already has full access. We intentionally
            # do NOT re-dump verify_attestation here — every one of its scalar
            # fields is already emitted flat at GENERIC/DETAILED above, and
            # repeating the nested object just doubles the byte cost.
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
            # Build idma_data only if idma is a non-empty dict. The earlier
            # version had a nested ternary on every key (`idma.get(k) if
            # isinstance(idma, dict) else None`) — redundant since a single
            # outer dict-check is sufficient.
            idma_data: Optional[Dict[str, Any]] = None
            if isinstance(idma, dict) and idma:
                idma_data = {
                    "k_eff": idma.get("k_eff"),
                    "effective_source_count": idma.get("effective_source_count"),
                    "correlation_risk": idma.get("correlation_risk"),
                    "source_overlap": idma.get("source_overlap"),
                    "fragility_flag": idma.get("fragility_flag"),
                    "reasoning_is_fragile": idma.get("reasoning_is_fragile"),
                    # phase is a key scoring metric: chaos/healthy/rigidity
                    "phase": idma.get("phase"),
                    "reasoning_state": idma.get("reasoning_state"),
                }

            # DETAILED: Add flags, lists, identifiers
            if is_detailed:
                csdma_data["flags"] = csdma.get("flags", []) if isinstance(csdma, dict) else []
                dsdma_data["domain"] = dsdma.get("domain") if isinstance(dsdma, dict) else None
                dsdma_data["flags"] = dsdma.get("flags", []) if isinstance(dsdma, dict) else []
                pdma_data["stakeholders"] = pdma.get("stakeholders") if isinstance(pdma, dict) else None
                pdma_data["conflicts"] = pdma.get("conflicts") if isinstance(pdma, dict) else None
                pdma_data["alignment_check"] = pdma.get("alignment_check") if isinstance(pdma, dict) else None
                if idma_data:
                    idma_data["k_raw"] = idma.get("k_raw") if isinstance(idma, dict) else None
                    idma_data["raw_source_count"] = idma.get("raw_source_count") if isinstance(idma, dict) else None
                    idma_data["rho_mean"] = idma.get("rho_mean") if isinstance(idma, dict) else None
                    idma_data["phase_confidence"] = idma.get("phase_confidence") if isinstance(idma, dict) else None
                    idma_data["collapse_margin"] = idma.get("collapse_margin") if isinstance(idma, dict) else None
                    idma_data["safety_margin"] = idma.get("safety_margin") if isinstance(idma, dict) else None
                    idma_data["sources_identified"] = idma.get("sources_identified") if isinstance(idma, dict) else None
                    idma_data["source_ids"] = idma.get("source_ids") if isinstance(idma, dict) else None
                    idma_data["source_types"] = idma.get("source_types") if isinstance(idma, dict) else None
                    idma_data["source_independence_scores"] = (
                        idma.get("source_independence_scores") if isinstance(idma, dict) else None
                    )
                    idma_data["source_type_counts"] = idma.get("source_type_counts") if isinstance(idma, dict) else None
                    idma_data["correlation_factors"] = (
                        idma.get("correlation_factors") if isinstance(idma, dict) else None
                    )
                    idma_data["top_correlation_factors"] = (
                        idma.get("top_correlation_factors") if isinstance(idma, dict) else None
                    )
                    idma_data["pairwise_correlation_summary"] = (
                        idma.get("pairwise_correlation_summary") if isinstance(idma, dict) else None
                    )
                    idma_data["rho_intra"] = idma.get("rho_intra") if isinstance(idma, dict) else None
                    idma_data["rho_inter"] = idma.get("rho_inter") if isinstance(idma, dict) else None
                    idma_data["module_count"] = idma.get("module_count") if isinstance(idma, dict) else None
                    idma_data["effective_module_count"] = (
                        idma.get("effective_module_count") if isinstance(idma, dict) else None
                    )
                    idma_data["source_clusters"] = idma.get("source_clusters") if isinstance(idma, dict) else None
                    idma_data["common_cause_flags"] = (
                        idma.get("common_cause_flags") if isinstance(idma, dict) else None
                    )
                    idma_data["intervention_recommendation"] = (
                        idma.get("intervention_recommendation") if isinstance(idma, dict) else None
                    )
                    idma_data["next_best_recovery_step"] = (
                        idma.get("next_best_recovery_step") if isinstance(idma, dict) else None
                    )
                    idma_data["delta_k_eff"] = idma.get("delta_k_eff") if isinstance(idma, dict) else None
                    idma_data["delta_rho_mean"] = idma.get("delta_rho_mean") if isinstance(idma, dict) else None
                    idma_data["phase_persistence_steps"] = (
                        idma.get("phase_persistence_steps") if isinstance(idma, dict) else None
                    )
                    idma_data["time_in_fragile_state_ms"] = (
                        idma.get("time_in_fragile_state_ms") if isinstance(idma, dict) else None
                    )
                    idma_data["moving_variance"] = idma.get("moving_variance") if isinstance(idma, dict) else None
                    idma_data["rho_critical"] = idma.get("rho_critical") if isinstance(idma, dict) else None
                    idma_data["k_required"] = idma.get("k_required") if isinstance(idma, dict) else None
                    idma_data["defense_function"] = (
                        idma.get("defense_function") if isinstance(idma, dict) else None
                    )
                    idma_data["collapse_rate"] = idma.get("collapse_rate") if isinstance(idma, dict) else None
                    idma_data["time_to_truth"] = idma.get("time_to_truth") if isinstance(idma, dict) else None
                    idma_data["time_to_entropy"] = idma.get("time_to_entropy") if isinstance(idma, dict) else None
                    idma_data["time_to_capture"] = idma.get("time_to_capture") if isinstance(idma, dict) else None

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

        elif event_type == "IDMA_RESULT":
            # RATIONALE (Part 1.5): Identity DMA fragility check
            # GENERIC: Numeric scores only - k_eff is the key metric
            data = {
                "k_eff": event.get("k_eff"),
                "effective_source_count": event.get("effective_source_count"),
                "correlation_risk": event.get("correlation_risk"),
                "source_overlap": event.get("source_overlap"),
                "phase": event.get("phase"),
                "reasoning_state": event.get("reasoning_state"),
                "fragility_flag": event.get("fragility_flag"),
                "reasoning_is_fragile": event.get("reasoning_is_fragile"),
            }
            # DETAILED: Add identified sources and correlation factors
            if is_detailed:
                data["k_raw"] = event.get("k_raw")
                data["raw_source_count"] = event.get("raw_source_count")
                data["rho_mean"] = event.get("rho_mean")
                data["phase_confidence"] = event.get("phase_confidence")
                data["collapse_margin"] = event.get("collapse_margin")
                data["safety_margin"] = event.get("safety_margin")
                data["sources_identified"] = event.get("sources_identified", [])
                data["source_ids"] = event.get("source_ids", [])
                data["source_types"] = event.get("source_types", [])
                data["source_independence_scores"] = event.get("source_independence_scores", [])
                data["source_type_counts"] = event.get("source_type_counts", [])
                data["correlation_factors"] = event.get("correlation_factors", [])
                data["top_correlation_factors"] = event.get("top_correlation_factors", [])
                data["pairwise_correlation_summary"] = event.get("pairwise_correlation_summary", [])
                data["rho_intra"] = event.get("rho_intra")
                data["rho_inter"] = event.get("rho_inter")
                data["module_count"] = event.get("module_count")
                data["effective_module_count"] = event.get("effective_module_count")
                data["source_clusters"] = event.get("source_clusters", [])
                data["common_cause_flags"] = event.get("common_cause_flags", [])
                data["intervention_recommendation"] = event.get("intervention_recommendation")
                data["next_best_recovery_step"] = event.get("next_best_recovery_step")
                data["delta_k_eff"] = event.get("delta_k_eff")
                data["delta_rho_mean"] = event.get("delta_rho_mean")
                data["phase_persistence_steps"] = event.get("phase_persistence_steps")
                data["time_in_fragile_state_ms"] = event.get("time_in_fragile_state_ms")
                data["moving_variance"] = event.get("moving_variance")
                data["rho_critical"] = event.get("rho_critical")
                data["k_required"] = event.get("k_required")
                data["defense_function"] = event.get("defense_function")
                data["collapse_rate"] = event.get("collapse_rate")
                data["time_to_truth"] = event.get("time_to_truth")
                data["time_to_entropy"] = event.get("time_to_entropy")
                data["time_to_capture"] = event.get("time_to_capture")
            # FULL: Add reasoning text and prompt
            if is_full:
                data["reasoning"] = event.get("reasoning")
                data["prompt_used"] = event.get("idma_prompt")
            return data

        elif event_type == "ASPDMA_RESULT":
            # RATIONALE (Part 2): Action selection
            # GENERIC: Action type and confidence only
            data = {
                "selected_action": event.get("selected_action"),
                "selection_confidence": event.get("selection_confidence"),
                "is_recursive": event.get("is_recursive", False),
            }
            # DETAILED: Add alternatives and timing
            if is_detailed:
                data["alternatives_considered"] = event.get("alternatives_considered")
                data["evaluation_time_ms"] = event.get("evaluation_time_ms")
            # FULL: Add reasoning text and parameters
            if is_full:
                data["action_rationale"] = event.get("action_rationale")
                data["reasoning_summary"] = event.get("reasoning_summary")
                data["action_parameters"] = _serialize(event.get("action_parameters"))
                data["aspdma_prompt"] = event.get("aspdma_prompt")
                # Truncate raw LLM response to 1000 chars for safety
                raw_response = event.get("raw_llm_response")
                if raw_response:
                    data["raw_llm_response"] = str(raw_response)[:1000]
            return data

        elif event_type == "TSASPDMA_RESULT":
            # RATIONALE (Part 2.5): Tool-Specific ASPDMA (optional, when TOOL selected)
            # DEPRECATED — replaced by VERB_SECOND_PASS_RESULT, kept during transition.
            # GENERIC: Final action and decision
            data = {
                "original_tool_name": event.get("original_tool_name"),
                "final_action": event.get("final_action"),
                "final_tool_name": event.get("final_tool_name"),
            }
            # DETAILED: Add parameter comparison and gotchas
            if is_detailed:
                data["original_parameters"] = _serialize(event.get("original_parameters", {}))
                data["final_parameters"] = _serialize(event.get("final_parameters", {}))
                data["gotchas_acknowledged"] = event.get("gotchas_acknowledged", [])
                data["tool_description"] = event.get("tool_description")
            # FULL: Add full reasoning and prompts
            if is_full:
                data["aspdma_rationale"] = event.get("aspdma_rationale")
                data["tsaspdma_rationale"] = event.get("tsaspdma_rationale")
                data["tsaspdma_prompt"] = event.get("tsaspdma_prompt")
            return data

        elif event_type == "VERB_SECOND_PASS_RESULT":
            # VERB_SECOND_PASS: Generic verb-specific second-pass result
            # (FSD/TRACE_EVENT_LOG_PERSISTENCE.md §4). One event with verb
            # discriminator replaces per-verb event types — TSASPDMA_RESULT
            # for TOOL, future per-verb second passes for MEMORIZE/etc.
            # GENERIC: verb + action transition + opaque verb-specific payload
            data = {
                "verb": event.get("verb"),
                "original_action": event.get("original_action"),
                "final_action": event.get("final_action"),
                # verb_specific_data is opaque at the lens row level —
                # serialized whole, ordered/decoded by `verb` discriminator
                # at query time. Lens may project verb-specific columns later.
                "verb_specific_data": _serialize(event.get("verb_specific_data", {})),
            }
            # DETAILED: Add reasoning text
            if is_detailed:
                data["original_reasoning"] = event.get("original_reasoning")
                data["final_reasoning"] = event.get("final_reasoning")
            # FULL: Add the second-pass prompt
            if is_full:
                data["second_pass_prompt"] = event.get("second_pass_prompt")
            return data

        elif event_type == "CONSCIENCE_RESULT":
            # CONSCIENCE: Ethical validation
            # GENERIC: All boolean flags and numeric scores (core for CIRIS scoring)
            # Extract entropy_level and coherence_level from epistemic_data - CRITICAL scoring metrics
            epistemic_data_obj = event.get("epistemic_data", {})
            if hasattr(epistemic_data_obj, "model_dump"):
                epistemic_data_obj = epistemic_data_obj.model_dump()
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
                # Core epistemic metrics from epistemic_data (CRITICAL for CIRIS scoring)
                "entropy_level": (
                    epistemic_data_obj.get("entropy_level") if isinstance(epistemic_data_obj, dict) else None
                ),
                "coherence_level": (
                    epistemic_data_obj.get("coherence_level") if isinstance(epistemic_data_obj, dict) else None
                ),
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
            # DETAILED: Add identifiers, lists, and key reason fields
            if is_detailed:
                data["final_action"] = event.get("final_action")
                data["conscience_override_reason"] = event.get("conscience_override_reason")
                data["entropy_reason"] = event.get("entropy_reason")
                data["coherence_reason"] = event.get("coherence_reason")
                data["optimization_veto_decision"] = event.get("optimization_veto_decision")
                data["optimization_veto_affected_values"] = event.get("optimization_veto_affected_values")
                data["epistemic_humility_uncertainties"] = event.get("epistemic_humility_uncertainties")
                data["epistemic_humility_recommendation"] = event.get("epistemic_humility_recommendation")
            # FULL: Add all text fields and complete epistemic_data
            if is_full:
                data["epistemic_data"] = _serialize(event.get("epistemic_data"))
                data["updated_status_content"] = event.get("updated_status_content")
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
                # Execution error indicator (privacy-preserving boolean)
                "has_execution_error": event.get("error") is not None,
            }
            # DETAILED: Add action type, follow-up, error details, and audit signature
            if is_detailed:
                data["action_executed"] = event.get("action_executed")
                data["follow_up_thought_id"] = event.get("follow_up_thought_id")
                data["audit_entry_id"] = event.get("audit_entry_id")
                data["models_used"] = event.get("models_used", [])
                data["api_bases_used"] = event.get("api_bases_used", [])
                data["execution_error"] = event.get("error")
                data["audit_signature"] = event.get("audit_signature")
            # FULL: Add parameters and full positive moment text
            if is_full:
                data["action_parameters"] = _serialize(action_params) if action_params else {}
                # Include full positive moment text at FULL detail level
                if positive_moment_text:
                    data["positive_moment"] = positive_moment_text[:500]  # Truncate for safety
            return data

        elif event_type == "LLM_CALL":
            # SUB-PIPELINE: per-provider-call observation (FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.2)
            # Multiple LLM_CALL events fire under each pipeline event — every DMA
            # / ASPDMA / conscience handler issues 1+ provider calls.
            # GENERIC: caller attribution + sizes + duration + outcome (no content)
            data = {
                "handler_name": event.get("handler_name"),
                "service_name": event.get("service_name"),
                "model": event.get("model"),
                "base_url": event.get("base_url"),
                "response_model": event.get("response_model"),
                "duration_ms": event.get("duration_ms"),
                "prompt_tokens": event.get("prompt_tokens"),
                "completion_tokens": event.get("completion_tokens"),
                "prompt_bytes": event.get("prompt_bytes"),
                "completion_bytes": event.get("completion_bytes"),
                "cost_usd": event.get("cost_usd"),
                "status": event.get("status"),
                "error_class": event.get("error_class"),
                "attempt_count": event.get("attempt_count", 1),
                "retry_count": event.get("retry_count", 0),
            }
            # DETAILED: add prompt hash for dedup analysis without leaking content
            if is_detailed:
                data["prompt_hash"] = event.get("prompt_hash")
            # FULL: full prompt + completion text
            if is_full:
                data["prompt"] = event.get("prompt")
                data["response_text"] = event.get("response_text")
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
            # Set trace_level BEFORE signing - critical for per-level signature verification
            trace.trace_level = self._trace_level.value

        # Drop attempt_index counters for this thought — they're only meaningful
        # while the thought is in-flight, and leaving them in the dict means
        # unbounded growth across long-running agents.
        self._attempt_counters = {
            key: count for key, count in self._attempt_counters.items() if key[0] != thought_id
        }

        # Sign the trace (signature includes trace_level for uniqueness)
        if self._signer.sign_trace(trace):
            self._traces_signed += 1
            component_types = [c.event_type for c in trace.components]
            logger.info(
                f"✅ TRACE COMPLETE #{self._traces_completed + 1}: {trace.trace_id} "
                f"(level={trace.trace_level}) with {len(trace.components)} components: {component_types}"
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
        # trace.trace_level is already set in _complete_trace before signing
        trace_dict = trace.to_dict()
        trace_event = {
            "event_type": "complete_trace",
            "trace": trace_dict,
            "trace_level": trace.trace_level,  # Also at event level for routing
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

        Called by WiseBus.send_deferral() which broadcasts to all WiseAuthority
        services with the send_deferral capability. WBD events are a distinct
        accord primitive from traces — they POST to the dedicated endpoint
        /accord/wbd/deferrals per the CIRISLens accord contract, NOT to
        /accord/events which is reserved for complete_trace envelopes.

        Args:
            request: DeferralRequest containing deferral details

        Returns:
            String confirming receipt
        """
        logger.debug(f"Received WBD event for thought {request.thought_id}")

        # Build payload matching CIRISLens WBDDeferralCreate schema.
        # See CIRISLens/api/accord_api.py::WBDDeferralCreate and POST /accord/wbd/deferrals.
        reason = (request.reason or "").strip()
        deferral_payload: Dict[str, Any] = {
            "agent_id": self._agent_id_hash or "unknown",
            # Default to UNCERTAINTY — the reason text is free-form and we can't
            # reliably classify it client-side. Lens is free to re-classify.
            "trigger_type": "UNCERTAINTY",
            "trigger_description": reason[:500] if reason else "Wisdom-based deferral",
            "context_summary": (
                f"thought_id={request.thought_id} task_id={request.task_id} "
                f"defer_until={request.defer_until.isoformat() if request.defer_until else 'n/a'}"
            ),
            "dilemma_description": reason[:2000] if reason else "(no reason provided)",
            "rationale": reason[:2000] if reason else None,
            # Thread the thought/task identifiers through as trace_id/span_id so
            # lens can join WBD events back to the owning trace.
            "trace_id": request.task_id or None,
            "span_id": request.thought_id or None,
        }

        await self._send_wbd_deferral(deferral_payload, request.thought_id)

        return f"WBD event recorded for accord metrics: {request.thought_id}"

    async def _send_wbd_deferral(self, payload: Dict[str, Any], thought_id: str) -> None:
        """POST a WBD deferral directly to the dedicated lens endpoint.

        Unlike trace events this is NOT batched through _event_queue — WBD is a
        separate accord primitive with its own endpoint. Failures are logged but
        don't raise, to keep the WiseBus broadcast non-blocking.
        """
        if not self._session:
            logger.warning("Cannot send WBD deferral — HTTP session not initialized")
            return

        url = f"{self._endpoint_url}/accord/wbd/deferrals"
        logger.info(f"📡 [{self._adapter_instance_id}] POST {url} (thought={thought_id})")

        try:
            async with self._session.post(url, json=payload) as response:
                if response.status in (200, 201):
                    logger.info(f"✅ WBD deferral accepted by lens (thought={thought_id})")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"❌ WBD deferral rejected: Status {response.status} "
                        f"{error_text[:500]} (url={url}, thought={thought_id})"
                    )
        except asyncio.TimeoutError as e:
            logger.error(
                f"❌ WBD deferral timed out ({type(e).__name__}) posting to {url} "
                f"(thought={thought_id})"
            )
        except Exception as e:
            logger.error(
                f"❌ WBD deferral failed: {type(e).__name__}: {e!r} "
                f"(url={url}, thought={thought_id})",
                exc_info=True,
            )

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
            "source": "accord_metrics",
            "message": "AccordMetricsService does not provide guidance",
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

        When consent is granted and the HTTP session/flush task are not yet
        initialized (adapter was started without consent), this method will
        start them so collection begins immediately without requiring a
        full adapter reload.

        Args:
            consent_given: Whether consent is given
            timestamp: ISO timestamp when consent was given/revoked
        """
        self._consent_given = consent_given
        self._consent_timestamp = timestamp or datetime.now(timezone.utc).isoformat()

        if consent_given:
            logger.info(f"Consent granted for accord metrics at {self._consent_timestamp}")
            # If the service was started without consent, the HTTP session and
            # flush task were never created.  Initialize them now so collection
            # begins immediately.  Only do this if there's a running event loop.
            try:
                loop = asyncio.get_running_loop()
                if self._session is None or (hasattr(self._session, "closed") and self._session.closed):
                    self._initialize_http_session()
                if self._flush_task is None or self._flush_task.done():
                    self._flush_task = asyncio.create_task(self._periodic_flush())
                    logger.info("Started periodic flush task after late consent grant")
            except RuntimeError:
                # No running event loop — session/task will be created on first async call
                pass
        else:
            logger.info(f"Consent revoked for accord metrics at {self._consent_timestamp}")

    def _initialize_http_session(self) -> None:
        """Create the aiohttp session used to send events to CIRISLens.

        Safe to call multiple times — will only create a session if one
        does not already exist (or the existing one is closed).

        On iOS, Python's default SSL context cannot find system CA certificates,
        so we explicitly create an SSL context using certifi's bundled CA bundle.
        """
        if self._session is not None and not getattr(self._session, "closed", True):
            return

        # Create SSL context with certifi CA bundle for iOS compatibility.
        # On iOS, Python's ssl module cannot locate system CA certs, causing
        # SSLCertVerificationError for all HTTPS connections.
        ssl_context = self._create_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        self._session = aiohttp.ClientSession(
            connector=connector,
            # Split timeout: distinguishes unreachable host (connect) from slow/stuck
            # server response (sock_read) when the POST never returns. A total cap
            # still protects against pathological cases.
            timeout=aiohttp.ClientTimeout(total=30, connect=10, sock_read=20),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CIRIS-AccordMetrics/1.0",
            },
        )
        logger.info(f"HTTP session initialized for {self._endpoint_url}")

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """Create an SSL context with proper CA certificates.

        Tries certifi first (bundled in iOS Resources), then falls back
        to the default context (works on desktop/server platforms).
        """
        try:
            import certifi

            ca_bundle = certifi.where()
            ctx = ssl.create_default_context(cafile=ca_bundle)
            logger.info(f"SSL context created with certifi CA bundle: {ca_bundle}")
            return ctx
        except ImportError:
            logger.debug("certifi not available, using default SSL context")
        except Exception as e:
            logger.warning(f"Failed to load certifi CA bundle: {e}, falling back to default")

        return ssl.create_default_context()

    def set_agent_id(self, agent_id: str) -> None:
        """Set agent identity for traces.

        The agent_id (template name like "Ally") is stored in _agent_name for display
        in traces. The _agent_id_hash is derived from the signing key's public key
        to ensure uniqueness across multiple instances of the same template.

        Args:
            agent_id: Agent identifier (template name like "Ally", "Echo", etc.)
        """
        # Validate agent_id is a proper string (not a mock or other type)
        if not isinstance(agent_id, str) or not agent_id:
            logger.warning(f"Invalid agent_id type: {type(agent_id).__name__}, skipping")
            return

        # Store template name for display in traces (agent_name field)
        if not self._agent_name:
            self._agent_name = agent_id

        # Compute unique hash from signing key (not template name)
        # This ensures each instance has a unique agent_id_hash even if
        # multiple instances share the same template (e.g., 30 "Ally" agents)
        # Falls back to agent_id hash in tests where signing key is mocked
        self._agent_id_hash = self._anonymize_agent_id(agent_id)

        logger.info(
            f"Agent identity set: template={agent_id}, "
            f"agent_name={self._agent_name}, "
            f"agent_id_hash={self._agent_id_hash}"
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics for telemetry.

        Returns:
            Dictionary of service metrics
        """
        return {
            "consent_given": self._consent_given,
            "trace_level": self._trace_level.value,
            "events_received": self._events_received,
            "events_sent": self._persisted_events_sent + self._events_sent,
            "events_sent_session": self._events_sent,
            "events_failed": self._events_failed,
            "events_queued": len(self._event_queue),
            "last_send_time": self._last_send_time.isoformat() if self._last_send_time else None,
            # Trace capture metrics
            "traces_active": len(self._active_traces),
            "traces_completed": self._traces_completed,
            "traces_signed": self._traces_signed,
            "signer_key_id": self._signer.key_id,
            "has_signing_key": self._signer.has_signing_key,
            "agent_id_hash": self._agent_id_hash,
        }

    def queue_lens_deletion_on_revoke(self) -> None:
        """Queue a deletion event to be sent to CIRISLens.

        Called when consent is revoked to request removal of all traces
        for this agent from the lens repository. Sends a disconnect event
        with deletion_requested=True so the lens API knows to purge data.
        """
        if not self._agent_id_hash:
            logger.warning("Cannot queue lens deletion: no agent_id_hash set")
            return

        deletion_event: Dict[str, Any] = {
            "event_type": "consent_revoked_deletion_requested",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id_hash": self._agent_id_hash,
            "deletion_requested": True,
            "reason": "User revoked accord metrics consent via DSAR self-service",
        }

        self._event_queue.append(deletion_event)
        logger.info(
            f"Queued lens deletion request for agent {self._agent_id_hash} " f"(queue size: {len(self._event_queue)})"
        )
