"""
Accord Metrics Services - Trace capture via the LensCore substrate.

2.9.6 LensCore fold (CIRISAgent#866 / #857): the trace-emit pipeline —
partial-trace assembly, attempt indexing, canonicalization, Ed25519 signing,
consent gating, local-copy tee, orphan sweep, and persistence — is OWNED BY
THE SUBSTRATE (`ciris-lens-core` `LensClient`, wire contract frozen in
CIRISLensCore/docs/PUBLIC_SCHEMA_CONTRACT.md). Sealed traces land in the
local persist store via `Engine::receive_and_persist`; federation fan-out
rides the substrate replication layer (CIRISLensCore#11 Cut 4), not agent
HTTP. LensCore is the observability ORCHESTRATOR the way the audit service
orchestrates the audit trail — and like persist/edge/verify it is a REQUIRED
substrate leg in 2.9.6+: `start()` raises if it cannot be constructed.

Per CIRISAgent#857 the legacy bespoke HTTP shipping path
(`POST <CIRIS_ACCORD_METRICS_ENDPOINT>/accord/*`) is RETIRED — "no second
shipping mechanism". That removed the aiohttp session, public-key
registration, connectivity heartbeats, WBD HTTP POSTs, the event queue /
batch / flush machinery, and the Python Ed25519 trace signer from this file
(~2200 lines of Python replaced by the Rust substrate).

What remains agent-side (the semantic mapping the substrate cannot own):
1. reasoning_event_stream subscription — each event is normalized and fed
   to `LensClient.capture_event`
2. `_extract_component_data` — per-event-type payload construction with
   trace-level field gating (generic / detailed / full_traces)
3. WBD deferrals — captured as DEFERRAL_ROUTED events in the closed
   15-variant ReasoningEventType taxonomy (no separate wire)
4. Consent config sourcing + correlation-metadata inputs (raw values; the
   PII lat/lng fuzz is a lens-core construction-time type invariant)

Consent is enforced at the substrate: lens-core's dynamic CEG consent gate
(`consent:community_trust:v1`, newest-wins; a withdraws/recants is a HARD
stop that config cannot override) decides at every seal. The agent-side
consent flag only selects the config-fallback timestamp handed to the
client (the 2.9.6 interim path per CIRISAgent#870).

Trace Detail Levels:
- generic (default): Numeric scores only - powers ciris.ai/ciris-scoring
- detailed: Adds actionable lists (sources, stakeholders, flags)
- full_traces: Complete reasoning text for research corpus

Event Types (closed 15-variant taxonomy, locked by lens-core at compile
time): THOUGHT_START, SNAPSHOT_AND_CONTEXT, DMA_RESULTS, IDMA_RESULT,
ASPDMA_RESULT, TSASPDMA_RESULT (deprecated), VERB_SECOND_PASS_RESULT,
CONSCIENCE_RESULT, ACTION_RESULT, LLM_CALL + the 5 Commons Credits events
(DEFERRAL_ROUTED / DEFERRAL_RECEIVED / DEFERRAL_RESOLVED /
GRATITUDE_SIGNALED / CREDIT_GENERATED).
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ciris_engine.schemas.services.authority_core import DeferralRequest
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)
# 2.9.6 crosses the JCS gate: the trace wire era the agent declares is
# "3.0.0" — persist's signed-epoch verifier gate (`canon_version_for_trace_
# schema`, src/verify/ed25519.rs) dispatches major >= 3 ⇒ JCS (RFC 8785),
# 2.x ⇒ legacy Python json.dumps. The signed stamp itself is produced by
# lens-core at seal time. NOTE: ciris-lens-core 1.0.0 still stamps "2.7.9"
# and signs V1Python (its capture path froze before the gate crossing);
# the upstream ask to align lens-core's stamp + canonicalizer to
# 3.0.0/JCS is filed on CIRISLensCore — the agent pin moves to that cut.
# Until then this constant documents the agent's DECLARED era; nothing
# signature-bearing reads it (the legacy HTTP wire that used to carry it
# is retired per #857).
TRACE_SCHEMA_VERSION = "3.0.0"


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


# PII fuzzing precision for ISO 6709 decimal degrees in correlation_metadata.
# Matches the city/region resolution that `user_location` string already
# carries (CIRISAgent#757 PII analysis). At 1 decimal place coordinates
# resolve to ~11 km × ~11 km cells — the right granularity for federation
# cohort routing (same city → same cohort) without leaking residence.
# 4 decimals = ~11 m = a specific house; 1 decimal = ~11 km = a city/region.
# Two emitted fields cannot disagree on privacy posture without leaking
# precision through the loose one — string field (`user_location` = city/
# state/country) and numeric fields must match resolution. Single source
# of truth so future call sites can't accidentally skip the rounding.
_PII_LOCATION_FUZZ_DECIMALS = 1

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
    """Simple capabilities container for duck-typing with WiseBus.

    The supported_domains field declares which DomainCategory values this
    service can handle. WiseBus filters services by domain_hint when routing
    deferrals to ensure only qualified handlers receive domain-specific requests.
    """

    actions: List[str]
    scopes: List[str]
    supported_domains: List[str] = field(default_factory=list)  # DomainCategory values

class AccordMetricsService:
    """Accord trace capture, orchestrated by the LensCore substrate.

    The service is the agent-side half of the CIRISLensCore client-emit
    contract: it subscribes to reasoning_event_stream, maps each event to
    the component-dict shape `LensClient.capture_event` expects (semantic
    extraction + trace-level gating), and lets the substrate own sealing,
    signing, consent gating, tee, and persistence.

    Also implements the WiseAuthority duck-type (send_deferral) so WBD
    events ride the same capture path as DEFERRAL_ROUTED components.
    """

    # Map reasoning events to trace components
    # Handle both formats: "THOUGHT_START" and "ReasoningEvent.THOUGHT_START"
    EVENT_TO_COMPONENT = {
        "THOUGHT_START": "observation",
        "SNAPSHOT_AND_CONTEXT": "context",
        "DMA_RESULTS": "rationale",
        "IDMA_RESULT": "rationale",  # Intuition DMA fragility check
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

        # Consent timestamp - REQUIRED when consent is given (it is the
        # config-fallback the lens-core consent gate uses when no CEG grant
        # is discoverable; without it every seal resolves NoConsent)
        self._consent_timestamp: Optional[str] = None
        raw_timestamp = self._config.get("consent_timestamp") or env_timestamp
        if raw_timestamp is not None:
            self._consent_timestamp = str(raw_timestamp)
        elif self._consent_given:
            self._consent_timestamp = datetime.now(timezone.utc).isoformat()
            logger.warning(
                f"⚠️ Consent given but no timestamp provided. Using current time: {self._consent_timestamp}. "
                "Set CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP for consistent timestamps across restarts."
            )

        if env_consent and not config_consent:
            logger.info("✅ CONSENT enabled via environment variable CIRIS_ACCORD_METRICS_CONSENT")

        # Local-tee: when CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR is set, the
        # substrate writes every sealed batch to <dir>/lens-batch-<seq>.json
        # (lens-core Gap 4 — best-effort, never fails persist). The QA
        # runner sets this automatically when --live-lens is active.
        env_local_copy_dir = _get_metrics_env("LOCAL_COPY_DIR") or None
        self._local_copy_dir: Optional[Path] = None
        if env_local_copy_dir:
            try:
                candidate = Path(env_local_copy_dir)
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / ".accord_local_copy_probe"
                probe.write_text("")
                probe.unlink()
                self._local_copy_dir = candidate
                logger.info(
                    f"📂 [{self._adapter_instance_id}] Local-copy enabled: {candidate} "
                    f"(every sealed batch will be teed here by lens-core)"
                )
            except OSError as e:  # PermissionError is a subclass of OSError
                logger.warning(
                    f"⚠️ [{self._adapter_instance_id}] CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR={env_local_copy_dir!r} "
                    f"is not writable ({e}); proceeding without local copies."
                )
                self._local_copy_dir = None

        # Sweep cadence — reuses the historical FLUSH_INTERVAL knob so QA
        # configs keep working; post-fold it paces orphan_sweep + the
        # events-total persistence, not an HTTP flush.
        env_interval = _get_metrics_env("FLUSH_INTERVAL") or None
        raw_interval = self._config.get("flush_interval_seconds")
        if env_interval is not None:
            self._sweep_interval: float = float(env_interval)
        elif raw_interval is not None and isinstance(raw_interval, (int, float, str)):
            self._sweep_interval = float(raw_interval)
        else:
            self._sweep_interval = 60.0

        # Orphan-trace max age — handed to LensClient.orphan_sweep. Traces
        # that never see ACTION_RESULT are purged by the substrate after
        # this age (they are ephemeral by design — no action, no trace).
        env_orphan = _get_metrics_env("ORPHAN_MAX_AGE") or None
        raw_orphan = self._config.get("orphan_trace_max_age_seconds")
        if env_orphan is not None:
            self._orphan_trace_max_age: float = float(env_orphan)
        elif raw_orphan is not None and isinstance(raw_orphan, (int, float, str)):
            self._orphan_trace_max_age = float(raw_orphan)
        else:
            self._orphan_trace_max_age = max(120.0, self._sweep_interval * 2.0)

        # Trace detail level - per-adapter config takes precedence over env var
        env_level = _get_metrics_env("TRACE_LEVEL", "").lower()
        config_level = str(self._config.get("trace_level", "")).lower()
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

        # Cohort taxonomy (deployment_profile block per FSD §3.2) —
        # operator-declared values; migration defaults filled by
        # _build_deployment_profile and stamped by lens-core onto every
        # sealed trace.
        self._deployment_region: str = str(self._config.get("deployment_region", "") or "")
        self._deployment_type: str = str(self._config.get("deployment_type", "") or "")
        self._deployment_domain: str = str(self._config.get("deployment_domain", "") or "")
        self._deployment_trust_mode: str = str(self._config.get("deployment_trust_mode", "") or "")
        self._agent_role: str = str(self._config.get("agent_role", "") or "")
        self._agent_template: str = str(self._config.get("agent_template", "") or "")

        # User location (only included if user explicitly consented via the
        # PREFERENCES step). RAW values — lens-core fuzzes lat/lng to the
        # ~11 km region grid as a construction-time type invariant
        # (CIRISAgent#757); un-fuzzed coordinates are unconstructable on
        # the wire by design.
        env_share_location = os.environ.get("CIRIS_SHARE_LOCATION_IN_TRACES", "").lower() == "true"
        self._share_location_in_traces: bool = env_share_location
        self._user_location: str = os.environ.get("CIRIS_USER_LOCATION", "") if env_share_location else ""
        self._user_timezone: str = os.environ.get("CIRIS_USER_TIMEZONE", "") if env_share_location else ""
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

        # The substrate client (constructed in start(); REQUIRED)
        self._lens: Optional[Any] = None

        # Metrics (session counters)
        self._events_received = 0
        self._events_sent = 0  # trace_events rows persisted by the substrate
        self._events_failed = 0
        self._events_rejected = 0  # unknown event_type (typed rejection)
        self._traces_completed = 0
        self._traces_signed = 0
        self._traces_consent_blocked = 0
        self._last_send_time: Optional[datetime] = None

        # In-flight thought_ids → monotonic open time (from capture_event
        # outcomes; the authoritative partial-trace store lives in lens-core).
        # Timestamps let _periodic_sweep age out entries whose traces the
        # substrate orphan-purged (we only learn a count, not which ids).
        self._open_thoughts: Dict[str, float] = {}

        # Serializes ALL capture_event calls. The stream consumer and
        # send_deferral are separate asyncio tasks; without this, two
        # asyncio.to_thread executors can enter the substrate concurrently,
        # breaking the FIFO that attempt_index counters and seal ordering
        # depend on (a DEFERRAL_ROUTED landing after its thought's
        # ACTION_RESULT would re-open a fresh trace that then orphans).
        self._capture_lock = asyncio.Lock()

        # Persisted cumulative total from prior sessions (loaded in start())
        self._persisted_events_sent = 0

        # Agent ID for anonymization (set during start)
        self._agent_id_hash: Optional[str] = None
        # Agent name (human-readable identifier for traces at all levels)
        self._agent_name: Optional[str] = str(self._config.get("agent_name", "") or "")

        # Reasoning event stream subscription
        self._reasoning_queue: Optional[asyncio.Queue[Any]] = None
        self._reasoning_task: Optional[asyncio.Task[None]] = None
        self._sweep_task: Optional[asyncio.Task[None]] = None

        logger.info(
            f"AccordMetricsService initialized (consent_given={self._consent_given}, "
            f"substrate=ciris-lens-core, level={self._trace_level.value})"
        )

    def _build_deployment_profile(self) -> Dict[str, Any]:
        """Return the 6-field deployment_profile block per FSD §3.2.

        Operator-declared config values are used when present; otherwise the
        migration defaults from FSD §3.2 are emitted so 2.7.9 emission is
        unblocked for agents that have not yet been operator-configured.

        Migration defaults (FSD §3.2):
            agent_role             = lowercased(agent_name)
            agent_template         = "{agent_name}-default-unspecified"
            deployment_domain      = "general"
            deployment_type        = "production"
            deployment_region      = null
            deployment_trust_mode  = "sovereign"
        """
        agent_name = self._agent_name or ""
        agent_role = self._agent_role or (agent_name.lower() if agent_name else "unknown")
        agent_template = self._agent_template or (
            f"{agent_name}-default-unspecified" if agent_name else "unknown-default-unspecified"
        )
        # `deployment_region` is the only field whose absent-config value
        # is `null` rather than a default string — null is a valid declaration
        # of "not disclosed" per the spec, distinct from absence-of-field
        # which is malformed.
        deployment_region: Optional[str] = self._deployment_region or None
        return {
            "agent_role": agent_role,
            "agent_template": agent_template,
            "deployment_domain": self._deployment_domain or "general",
            "deployment_type": self._deployment_type or "production",
            "deployment_region": deployment_region,
            "deployment_trust_mode": self._deployment_trust_mode or "sovereign",
        }

    def _compute_instance_hash(self, fallback_id: Optional[str] = None) -> str:
        """Compute unique instance hash from the unified signing key.

        Uses the CIRISVerify-backed unified key's public bytes so the hash is
        unique per agent INSTANCE, not per template name — and stable across
        the LensCore fold (the same derivation the pre-fold Python signer
        used, preserving DSAR/lens-identifier continuity even though trace
        SIGNATURES now come from the persist federation key via
        `engine.signer()`).

        Args:
            fallback_id: If signing key unavailable, hash this ID instead (for tests)

        Returns:
            SHA-256 hash of signing key's public key (first 16 chars),
            or hash of fallback_id if provided and no signing key,
            or "unknown" if neither available.
        """
        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            unified_key = get_unified_signing_key()
            pubkey_bytes = unified_key.public_key_bytes
            return hashlib.sha256(pubkey_bytes).hexdigest()[:16]
        except Exception as e:
            logger.debug(f"Could not compute instance hash from signing key: {e}")

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

            node = get_graph_node("accord_metrics/trace_events_total", GraphScope.LOCAL)
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
                id="accord_metrics/trace_events_total",
                type=NodeType.CONFIG,
                scope=GraphScope.LOCAL,
                attributes={
                    # `key` is required for this NodeType.CONFIG node to be a
                    # valid ConfigNode — config_service.search("type:config")
                    # picks it up and ConfigNode.from_graph_node() does
                    # attrs["key"]. Without it, every config scan logged
                    # "Failed to convert node ... to ConfigNode: 'key'"
                    # (×100+ — a WARNING flood).
                    "key": "accord_metrics/trace_events_total",
                    "events_sent_total": total,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
                updated_by="accord_metrics_service",
                updated_at=datetime.now(timezone.utc),
            )
            time_service = TimeService()
            add_graph_node(node, time_service)
        except Exception as e:
            logger.debug(f"Could not persist events total: {e}")

    def _build_lens_client(self) -> Any:
        """Construct the substrate LensClient (REQUIRED in 2.9.6+).

        lens-core composes against the process-singleton persist Engine
        (constructed during persistence init, before adapters start) and
        signs via `engine.signer()` — the federation identity key. Raises
        RuntimeError when the substrate is unavailable: like persist/edge/
        verify, a missing lens-core blocks the trace surface the same way
        a missing persist blocks boot. (Platforms whose lens-core wheels
        are still in flight — Android/iOS/Windows — are release-gated on
        the upstream wheel asks, mirroring how persist/edge ship Chaquopy
        wheels.)
        """
        try:
            from ciris_lens_core import LensClient
        except ImportError as e:
            raise RuntimeError(
                "ciris-lens-core is REQUIRED in 2.9.6+ (the observability "
                "orchestrator — CIRISAgent#866). pip install "
                "'ciris-lens-core>=1.0.0,<2.0.0'. Import failed: " + str(e)
            ) from e

        # The consent wire artifact: lens-core's gate resolves the newest
        # consent:community_trust:v1 row BY this key at every seal — the
        # grant our consent attestation module writes on opt-in, the
        # withdraws/recants it writes on revocation (a recant is a hard
        # stop). The config-fallback timestamp below only matters while no
        # CEG row exists (e.g. QA-runner env override).
        try:
            from ciris_engine.logic.runtime.edge_runtime import get_federation_address

            consent_key_id: Optional[str] = get_federation_address()
        except Exception as e:
            logger.warning(f"Federation address unavailable for consent gate ({e}); config-fallback consent only")
            consent_key_id = None

        try:
            return LensClient(
                self._consent_timestamp if self._consent_given else None,
                self._trace_level.value,
                deployment_profile=self._build_deployment_profile(),
                consent_attesting_key_id=consent_key_id,
                local_copy_dir=str(self._local_copy_dir) if self._local_copy_dir else None,
                deployment_region=self._deployment_region or None,
                deployment_type=self._deployment_type or None,
                agent_role=self._agent_role or None,
                agent_template=self._agent_template or None,
                share_location=self._share_location_in_traces,
                user_location=self._user_location or None,
                user_timezone=self._user_timezone or None,
                user_latitude=self._user_latitude,
                user_longitude=self._user_longitude,
            )
        except Exception as e:
            raise RuntimeError(
                f"LensClient construction failed: {type(e).__name__}: {e}. "
                "The persist Engine singleton must be initialized before "
                "the accord_metrics adapter starts."
            ) from e

    async def start(self) -> None:
        """Start the service: substrate client + stream subscription."""
        # Load persisted event count from previous sessions
        self._persisted_events_sent = self._load_persisted_events_total()
        if self._persisted_events_sent:
            logger.info(f"   Loaded persisted events total: {self._persisted_events_sent}")

        logger.info("=" * 70)
        logger.info("🚀 ACCORD METRICS SERVICE STARTING (LensCore substrate)")
        logger.info(f"   Consent given: {self._consent_given}")
        logger.info(f"   Consent timestamp: {self._consent_timestamp or 'NOT SET'}")
        logger.info(f"   Trace level: {self._trace_level.value}")

        # Set agent_id from constructor if provided and not already set
        if self._initial_agent_id and not self._agent_id_hash:
            self.set_agent_id(self._initial_agent_id)
            logger.info(f"   Agent ID set from constructor: {self._initial_agent_id}")

        # REQUIRED substrate leg — raises if unavailable (see docstring)
        self._lens = self._build_lens_client()
        logger.info("   ✅ LensClient constructed (capture→seal→sign→persist owned by substrate)")
        logger.info("=" * 70)

        # Subscribe to reasoning_event_stream for trace capture.
        # Capture happens regardless of consent — lens-core's consent gate
        # decides at each seal (a recant between two seals is enforced at
        # the very next ACTION_RESULT).
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            self._reasoning_queue = asyncio.Queue(maxsize=1000)
            reasoning_event_stream.subscribe(self._reasoning_queue)
            self._reasoning_task = asyncio.create_task(self._process_reasoning_events())
            logger.info(f"✅ SUBSCRIBED to reasoning_event_stream (queue maxsize=1000)")
        except Exception as e:
            logger.error(f"❌ FAILED to subscribe to reasoning_event_stream: {e}")
            logger.error("   Traces will NOT be captured!")

        self._sweep_task = asyncio.create_task(self._periodic_sweep())

        if not self._consent_given:
            logger.warning(
                "⚠️  CONSENT NOT GIVEN — events are captured but every seal "
                "resolves consent_blocked at the substrate (nothing persists)"
            )

    async def stop(self) -> None:
        """Stop the service: final sweep + stats."""
        logger.info("=" * 70)
        logger.info("🛑 ACCORD METRICS SERVICE STOPPING")
        logger.info(f"   Traces completed: {self._traces_completed}")

        # Unsubscribe from reasoning_event_stream
        if self._reasoning_queue:
            try:
                from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

                reasoning_event_stream.unsubscribe(self._reasoning_queue)
                logger.info("   Unsubscribed from reasoning_event_stream")
            except Exception as e:
                logger.debug(f"Could not unsubscribe from reasoning_event_stream: {e}")

        for task in (self._reasoning_task, self._sweep_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected - we initiated the cancellation

        # Final orphan sweep + persist the cumulative counter
        if self._lens is not None:
            try:
                purged = await asyncio.to_thread(self._lens.orphan_sweep, int(self._orphan_trace_max_age))
                if purged:
                    logger.info(f"   Final orphan sweep purged {purged} in-flight trace(s)")
            except Exception as e:
                logger.debug(f"Final orphan sweep failed: {e}")
        self._persist_events_total()

        logger.info("📊 ACCORD METRICS FINAL STATS")
        logger.info(f"   Traces completed: {self._traces_completed}")
        logger.info(f"   Trace events persisted: {self._events_sent}")
        logger.info(f"   Consent-blocked seals: {self._traces_consent_blocked}")
        logger.info(f"   Events received: {self._events_received}")
        logger.info("=" * 70)

    async def _periodic_sweep(self) -> None:
        """Pace the substrate orphan sweep + events-total persistence.

        Orphaned in-flight traces (no ACTION_RESULT) are ephemeral by
        design — no action means it never happened; the substrate purges
        them after `_orphan_trace_max_age` rather than force-emitting
        partial traces.
        """
        try:
            while True:
                try:
                    await asyncio.sleep(self._sweep_interval)
                    if self._lens is not None:
                        purged = await asyncio.to_thread(
                            self._lens.orphan_sweep, int(self._orphan_trace_max_age)
                        )
                        if purged:
                            logger.warning(
                                f"⏰ [{self._adapter_instance_id}] Substrate purged {purged} orphan "
                                f"trace(s) (no ACTION_RESULT after {self._orphan_trace_max_age:.0f}s). "
                                "This usually means the upstream ACTION_COMPLETE broadcast was severed."
                            )
                        # Age out our open-thought mirror in lockstep: the
                        # substrate purge tells us a count, not which ids, so
                        # drop entries past the same orphan age.
                        cutoff = time.monotonic() - self._orphan_trace_max_age
                        stale = [tid for tid, opened in self._open_thoughts.items() if opened < cutoff]
                        for tid in stale:
                            self._open_thoughts.pop(tid, None)
                    self._persist_events_total()
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise  # Re-raise to exit cleanly
                    logger.error(
                        f"Error in periodic sweep: {type(e).__name__}: {e!r}",
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            pass  # Clean exit on cancellation

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
            # Per-event isolation: one bad event must not drop the rest of
            # the stream update (which may include the ACTION_RESULT seal).
            try:
                await self._process_single_event(event)
            except Exception as e:
                self._events_failed += 1
                logger.error(
                    f"capture failed for event {event.get('event_type', '?')} "
                    f"(thought {event.get('thought_id', '?')}): {type(e).__name__}: {e!r}"
                )

    async def _process_single_event(self, event: Dict[str, Any]) -> None:
        """Normalize one reasoning event and feed it to the substrate.

        The agent-side half of the lens-core client-emit contract: map the
        event to the `capture_event` component shape (event_type /
        thought_id / timestamp / agent_id_hash / task_id / trace_level /
        data) with `_extract_component_data` building `data` under the
        configured trace-level gating. Everything downstream — partial
        trace assembly, attempt_index injection, seal on ACTION_RESULT,
        consent gate, canonical bytes, Ed25519 signature, tee, persistence
        — is the substrate's.
        """
        raw_event_type = event.get("event_type", "")
        # Handle both enum objects and strings
        if hasattr(raw_event_type, "value"):
            event_type = raw_event_type.value.upper()  # 'thought_start' -> 'THOUGHT_START'
        else:
            event_type = str(raw_event_type).replace("ReasoningEvent.", "")

        thought_id = event.get("thought_id", "")
        if not thought_id:
            logger.debug(f"Ignoring event without thought_id: {event_type}")
            return

        self._events_received += 1

        if self._lens is None:
            # start() raises when the substrate is unavailable, so this only
            # happens if events arrive before start() — drop with a debug.
            logger.debug("LensClient not ready; dropping event %s", event_type)
            return

        component: Dict[str, Any] = {
            "event_type": event_type,
            "thought_id": thought_id,
            "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "agent_id_hash": self._agent_id_hash or self._compute_instance_hash(),
            "task_id": event.get("task_id"),
            "trace_level": self._trace_level.value,
            "data": self._extract_component_data(event_type, event),
        }

        # to_thread keeps the seal's Ed25519+DB work off the event loop;
        # _capture_lock serializes against send_deferral (a separate task)
        # so the substrate sees a strict FIFO — its attempt_index counters
        # and seal ordering depend on it.
        async with self._capture_lock:
            outcome = await asyncio.to_thread(self._lens.capture_event, component)
        kind = outcome.get("outcome", "")

        if kind == "opened":
            self._open_thoughts[thought_id] = time.monotonic()
        elif kind == "sealed_and_persisted":
            self._open_thoughts.pop(thought_id, None)
            self._traces_completed += 1
            if int(outcome.get("signatures_verified", 0)) > 0:
                self._traces_signed += 1
            inserted = int(outcome.get("trace_events_inserted", 0))
            self._events_sent += inserted
            self._last_send_time = datetime.now(timezone.utc)
            logger.info(
                f"✅ TRACE SEALED #{self._traces_completed}: {outcome.get('trace_id')} "
                f"({inserted} trace_events, {outcome.get('signatures_verified', 0)} signature(s) verified)"
            )
        elif kind == "consent_blocked":
            self._open_thoughts.pop(thought_id, None)
            self._traces_consent_blocked += 1
            logger.debug(
                f"⏭️  Trace for {thought_id} consent_blocked at seal "
                f"(reason={outcome.get('reason')})"
            )
        elif kind == "rejected":
            self._events_rejected += 1
            logger.warning(
                f"🚫 Substrate rejected unknown event_type {outcome.get('raw')!r} "
                f"(thought {thought_id})"
            )
        # "appended" needs no bookkeeping

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
            # RATIONALE (Part 1.5): Intuition DMA fragility check
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
                # is_recursive: True for the recursive_conscience pass after
                # an override. Lens uses this alongside attempt_index to
                # distinguish initial from recursive emissions in trace_events.
                # Mirrors the same field on ASPDMA_RESULT — without it the lens
                # has to infer recursive-ness from attempt_index>0 alone.
                # See FSD/TRACE_WIRE_FORMAT.md §5.8.
                "is_recursive": event.get("is_recursive", False),
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
                # Parent linkage (TRACE_WIRE_FORMAT.md §5.10 — required as of
                # trace_schema_version "2.7.9"). Populated from ContextVar by
                # llm_bus._broadcast_llm_call_event:218-219; closed taxonomy
                # forms the AV-9-resilient parent link with parent_attempt_index.
                #
                # Sentinel "UNKNOWN_PARENT" → None on the wire. Persist's
                # `BatchEvent.parent_event_type` is `Option<ReasoningEventType>`
                # with `#[serde(default, skip_serializing_if = "Option::is_none")]`
                # (CIRISPersist/src/schema/events.rs:268-275). Emitting the
                # literal "UNKNOWN_PARENT" lands a non-enum string in the
                # column and persist rejects the whole batch with HTTP 422
                # (CIRISLens#13 driver). The sentinel from
                # llm_call_context.py:44 is for agent-side WARN only —
                # llm_bus.py:183-189 logs the unwired call site so it can be
                # fixed; we just omit the field so the rest of the trace ships.
                "parent_event_type": (
                    None
                    if event.get("parent_event_type") == "UNKNOWN_PARENT"
                    else event.get("parent_event_type")
                ),
                "parent_attempt_index": event.get("parent_attempt_index"),
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

    # =========================================================================
    # WiseBus-Compatible Interface (Duck-typed)
    # =========================================================================

    async def send_deferral(self, request: DeferralRequest) -> str:
        """Receive WBD (Wisdom-Based Deferral) events.

        Called by WiseBus.send_deferral() which broadcasts to all
        WiseAuthority services with the send_deferral capability. Post-fold
        (CIRISAgent#857: "no second shipping mechanism") WBD events ride the
        SAME substrate capture path as everything else — DEFERRAL_ROUTED is
        one of the 5 Commons Credits events in the closed 15-variant
        taxonomy. The component joins the deferring thought's in-flight
        trace and seals with its ACTION_RESULT.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        deferral_id = f"wbd-{request.thought_id}-{timestamp}"

        if self._lens is None:
            logger.debug("LensClient not ready; WBD deferral %s not captured", deferral_id)
            return deferral_id

        is_detailed = self._trace_level in (TraceDetailLevel.DETAILED, TraceDetailLevel.FULL_TRACES)
        data: Dict[str, Any] = {
            "defer_until": request.defer_until.isoformat() if request.defer_until else None,
        }
        if is_detailed and request.reason:
            data["reason"] = request.reason[:500]

        component: Dict[str, Any] = {
            "event_type": "DEFERRAL_ROUTED",
            "thought_id": request.thought_id,
            "timestamp": timestamp,
            "agent_id_hash": self._agent_id_hash or self._compute_instance_hash(),
            "task_id": request.task_id,
            "trace_level": self._trace_level.value,
            "data": data,
        }
        try:
            async with self._capture_lock:
                outcome = await asyncio.to_thread(self._lens.capture_event, component)
            self._events_received += 1
            if outcome.get("outcome") == "opened":
                self._open_thoughts[request.thought_id] = time.monotonic()
            logger.info(
                f"🧭 WBD deferral captured for thought {request.thought_id} "
                f"(outcome={outcome.get('outcome')})"
            )
        except Exception as e:
            logger.error(f"Failed to capture WBD deferral: {type(e).__name__}: {e!r}")

        return deferral_id

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

    # =========================================================================
    # Consent Management
    # =========================================================================

    def set_consent(self, consent_given: bool, timestamp: Optional[str] = None) -> None:
        """Update consent state and rebuild the substrate client.

        The LensClient handle freezes its config-fallback consent_timestamp
        at construction (the 2.9.6 interim path — CIRISAgent#870), so a
        consent change rebuilds the handle. In-flight partial traces in the
        old handle are dropped with it: on a REVOKE that is exactly the
        desired hard stop; on a GRANT the loss of mid-flight thoughts is
        acceptable (the next thought captures cleanly).

        Once the canonical community key publishes and
        `consent_attesting_key_id` is wired, the substrate reads the CEG
        grant live at each seal and this rebuild becomes unnecessary.
        """
        self._consent_given = consent_given
        self._consent_timestamp = timestamp or datetime.now(timezone.utc).isoformat()

        if consent_given:
            logger.info(f"Consent granted for accord metrics at {self._consent_timestamp}")
        else:
            logger.info(f"Consent revoked for accord metrics at {self._consent_timestamp}")

        if self._lens is not None:
            try:
                self._lens = self._build_lens_client()
                logger.info("   LensClient rebuilt with updated consent state")
            except RuntimeError as e:
                logger.error(f"   LensClient rebuild failed: {e}")

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
        try:
            from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

            signer_key_id: Optional[str] = get_unified_signing_key().key_id
        except Exception:
            signer_key_id = None

        return {
            "consent_given": self._consent_given,
            "trace_level": self._trace_level.value,
            "events_received": self._events_received,
            "events_sent": self._persisted_events_sent + self._events_sent,
            "events_sent_session": self._events_sent,
            "events_failed": self._events_failed,
            "events_rejected": self._events_rejected,
            "events_queued": 0,  # no agent-side queue post-fold (substrate-owned)
            "last_send_time": self._last_send_time.isoformat() if self._last_send_time else None,
            # Trace capture metrics
            "traces_active": len(self._open_thoughts),
            "traces_completed": self._traces_completed,
            "traces_signed": self._traces_signed,
            "traces_consent_blocked": self._traces_consent_blocked,
            "signer_key_id": signer_key_id,
            "has_signing_key": signer_key_id is not None,
            "agent_id_hash": self._agent_id_hash,
            "substrate": "ciris-lens-core",
        }

    def queue_lens_deletion_on_revoke(self) -> None:
        """DSAR deletion request on consent revocation.

        Post-fold there is no bespoke deletion event to a lens HTTP API.
        Deletion is CEG-native: my_data.py emits the
        `emit_community_consent_revocation(RECANT)` attestation, lens-core's
        consent gate hard-stops every subsequent seal, and lens-side purge
        of historical data rides the CEG revoke/recant cascade
        (CIRISLensCore requirement filed with #869). This method remains for
        the my_data.py call-contract and records the request locally.
        """
        logger.info(
            f"DSAR deletion requested for agent {self._agent_id_hash or 'unknown'} — "
            "handled by the CEG recant cascade (consent gate stops emission at "
            "the next seal; lens-side purge rides the revoke/recant cascade)"
        )
