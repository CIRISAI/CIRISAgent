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
import base64
import hashlib
import logging
import os
import json
import re
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
# lens-core at seal time — "3.0.0"/JCS as of ciris-lens-core 1.0.1
# (CIRISLensCore#43.2): the seal selects its canonicalizer via the SAME
# canon_version_for_trace_schema gate the verifier uses, so stamp and
# bytes can never skew. E2E-verified 2026-06-12: Amharic+Chinese trace
# sealed, signed, persist-verified at ingest. This constant mirrors the
# substrate stamp for documentation/telemetry; nothing
# signature-bearing reads it (the legacy HTTP wire that used to carry it
# is retired per #857).
TRACE_SCHEMA_VERSION = "3.0.0"


def _capture_deferrals_enabled() -> bool:
    """Whether DEFERRAL_ROUTED components may join trace capture.

    Default OFF (CIRISPersist#203): the persist floor's trace_events
    component enum lacks `deferral_routed`, so a sealed trace carrying one
    fails ingest wholesale. Flip the default (and delete this gate) when
    the pinned persist ships the variant.
    """
    return _get_metrics_env("CAPTURE_DEFERRALS", "").lower() in ("1", "true", "yes", "on")


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


# --- #933 repeated-failure log hygiene --------------------------------------
# The 2.7.x-era HTTP flush hot loop (fixed-cadence 401 retries, one full
# traceback per attempt, ~3/min forever) was structurally removed by the
# 2.9.6 LensCore fold (#857 "no second shipping mechanism"): there is no
# agent-side HTTP shipping path left to retry. Two repeated-failure surfaces
# remain that could reproduce the same log-spam pattern under a persistent
# substrate fault:
#   * the per-event capture path (`LensClient.capture_event` — a
#     persistently failing seal, e.g. `verify_unknown_key` while the lens/
#     persist backend does not know the signer key, would otherwise log one
#     ERROR per event), and
#   * the periodic sweep loop (`_periodic_sweep` — a persistent
#     orphan_sweep/persist failure would otherwise log a full traceback per
#     interval, forever).
# Policy (#933): log the FIRST failure of a streak and state transitions
# only; steady-state failures go to counters (exposed via get_metrics), and
# the one timer-driven loop backs off exponentially while failing.
SWEEP_BACKOFF_MULTIPLIER = 2.0
# Cap for the backed-off sweep cadence — the slow re-probe interval #933
# asks for: frequent enough to recover promptly once the substrate heals,
# slow enough to be quiet in the meantime. Never drops below the configured
# sweep interval.
SWEEP_BACKOFF_MAX_SECONDS = 900.0

# Bounded event buffer (#933 buffer policy): the ONLY agent-side buffering
# post-fold is the reasoning-stream subscription queue created in start().
# It is hard-capped at this size; when full, the PUBLISHER drops the new
# update with a WARNING (step_streaming.py: asyncio.QueueFull →
# "Subscriber queue is full, dropping reasoning event") — drop-newest,
# never unbounded growth. A failed capture is dropped, never re-queued, so
# a persistent substrate fault cannot become a retry hot loop: capture
# attempts are paced by the reasoning stream itself, not a timer.
REASONING_QUEUE_MAXSIZE = 1000

# Marker persist's trace verifier uses when rejecting a seal signed by a
# key it does not know (`Engine.receive_and_persist` → ValueError
# "verify_unknown_key"). This is the post-fold manifestation of the
# 2.7.x-era HTTP 401 {"error":"verify_unknown_key"}: an auth/registration
# failure that retrying cannot fix — only registering the signer key with
# the verifying backend can.
_AUTH_FAILURE_MARKER = "verify_unknown_key"


class CaptureHealthState(str, Enum):
    """Health of a repeated-failure domain (#933 log hygiene).

    HEALTHY: normal operation — the streak tracker logs nothing.
    DEGRADED: consecutive failures of a presumed-transient class
        (substrate/db errors, timeouts) — first failure logged with
        traceback, the rest counted.
    DEGRADED_AUTH: the signer key is not registered with the verifying
        backend (verify_unknown_key) — non-retryable by waiting; the named
        remedy is logged ONCE, no traceback, and recovery is automatic at
        the next capture once the key is accepted (the lens collector
        migration window makes keys valid without an agent restart).
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DEGRADED_AUTH = "degraded_auth"


@dataclass
class FailureStreak:
    """Per-domain repeated-failure bookkeeping (#933).

    A gauge, not a log stream: the service logs the streak's FIRST failure
    (= the state transition, including a change of failure class) and the
    recovery transition; everything in between increments counters that
    get_metrics() surfaces.
    """

    domain: str
    state: CaptureHealthState = CaptureHealthState.HEALTHY
    consecutive_failures: int = 0
    suppressed_log_count: int = 0
    total_failures: int = 0
    last_error_class: str = ""
    last_error_message: str = ""


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
        # substrate writes every sealed batch to
        # <dir>/<instance>/lens-batch-<seq>.json (lens-core Gap 4 —
        # best-effort, never fails persist). The QA runner sets this
        # automatically. The per-INSTANCE subdir is load-bearing: each
        # LensClient keeps its own batch sequence counter starting at 0,
        # so two instances (e.g. the QA multi-level generic/detailed/
        # full_traces trio) sharing one dir silently overwrite each
        # other's lens-batch-00000000.json.
        # Per-adapter CONFIG takes precedence over env, matching trace_level's
        # resolution one block below. Without this, an adapter registered at
        # RUNTIME over the API (the QA runner's accord_detailed / accord_full —
        # the two that carry the actual detailed + full-text traces) had no way
        # to be told where to tee: its registration payload carries trace_level
        # and consent, and local_copy_dir was env-only.
        config_local_copy_dir = str(self._config.get("local_copy_dir", "") or "") or None
        env_local_copy_dir = config_local_copy_dir or _get_metrics_env("LOCAL_COPY_DIR") or None
        self._local_copy_dir: Optional[Path] = None
        if env_local_copy_dir:
            try:
                safe_instance = re.sub(r"[^A-Za-z0-9._-]", "_", self._adapter_instance_id) or "default"
                candidate = Path(env_local_copy_dir) / safe_instance
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
        else:
            # A run that captures reasoning events, seals traces, and writes
            # NOTHING to disk is indistinguishable from a healthy run unless it
            # says so. Observed exactly that: 28 events received, traces sealed,
            # zero lens-batch files, "Success Rate 100.0%". Anything downstream
            # that reads the tee dir then computes on an empty set and reports a
            # clean result.
            logger.warning(
                f"📂 [{self._adapter_instance_id}] Local-copy OFF (trace_level={self._config.get('trace_level') or _get_metrics_env('TRACE_LEVEL') or 'generic'}) "
                f"— sealed batches are NOT written to disk. Set local_copy_dir in the adapter "
                f"config or CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR in the env. Any harness reading "
                f"a tee dir will find zero traces and may report that as a clean run."
            )

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
        self._deferrals_held = 0  # WBD deferrals held from capture (CIRISPersist#203)
        self._traces_completed = 0
        self._traces_signed = 0
        self._traces_consent_blocked = 0
        self._last_send_time: Optional[datetime] = None

        # 933 log hygiene: per-domain failure streaks + the sweep loop's
        # current (possibly backed-off) cadence. While healthy,
        # _sweep_interval_current == _sweep_interval and nothing here has
        # any observable effect — the happy path is unchanged.
        self._capture_streak = FailureStreak("capture")
        self._sweep_streak = FailureStreak("sweep")
        self._sweep_interval_current: float = self._sweep_interval

        # Runtime self-heal: while consent is OFF, the event path re-checks the
        # CEG grant (throttled) so a grant written AFTER the service started
        # (the mobile first-run wizard case — Chaquopy keeps ONE Python process
        # across the Android UI "restart", so the boot-time derivation never
        # re-runs) arms the seal without a process restart. Monotonic seconds of
        # the last re-check; 0.0 = never checked.
        self._last_consent_recheck: float = 0.0
        self._consent_recheck_interval: float = 10.0

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
        """Compute unique instance hash from the persist Engine's local signer.

        2.9.7 (second-signer removal): derived from the engine's federation
        signing pubkey (`engine.local_public_key_b64()`) — the SAME identity
        that signs traces + audit entries. This CHANGES the instance hash /
        DSAR-lens identifier from the pre-2.9.7 CIRISVerify-key derivation;
        accepted breakage, one signer identity.

        Must stay in sync with
        ciris_engine/logic/adapters/api/routes/my_data.py.

        Args:
            fallback_id: If the engine is unavailable, hash this ID instead (for tests)

        Returns:
            SHA-256 hash of the signer's raw public key bytes (first 16 chars),
            or hash of fallback_id if provided and no engine,
            or "unknown" if neither available.
        """
        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            engine = get_persist_engine()
            if engine is not None:
                pubkey_bytes = base64.b64decode(engine.local_public_key_b64())
                return hashlib.sha256(pubkey_bytes).hexdigest()[:16]
        except Exception as e:
            logger.debug(f"Could not compute instance hash from engine signer: {e}")

        # Fallback for tests/environments without a wired engine
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

    # Graph node id for the cumulative events_sent counter (persists the
    # total across sessions; survives the 2.9.6 fold rename).
    _EVENTS_TOTAL_NODE_ID = "accord_metrics/trace_events_total"

    def _load_persisted_events_total(self) -> int:
        """Load persisted cumulative events_sent from previous sessions."""
        try:
            from ciris_engine.logic.persistence.models.graph import get_graph_node
            from ciris_engine.schemas.services.graph_core import GraphScope

            node = get_graph_node(self._EVENTS_TOTAL_NODE_ID, GraphScope.LOCAL)
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
                id=self._EVENTS_TOTAL_NODE_ID,
                type=NodeType.CONFIG,
                scope=GraphScope.LOCAL,
                attributes={
                    # `key` is required for this NodeType.CONFIG node to be a
                    # valid ConfigNode — config_service.search("type:config")
                    # picks it up and ConfigNode.from_graph_node() does
                    # attrs["key"]. Without it, every config scan logged
                    # "Failed to convert node ... to ConfigNode: 'key'"
                    # (×100+ — a WARNING flood).
                    "key": self._EVENTS_TOTAL_NODE_ID,
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
            # One wheel (#896): LensClient re-hosts from ciris_server so the
            # trace pipeline shares the SAME persist Engine the agent runs on.
            # Pulling it from standalone ciris_lens_core (which Requires
            # ciris-persist) reinstalls a second persist wheel alongside the
            # one wheel — a dual-registry cohabitation that makes the seal's
            # signer key invisible to the agent's Engine.receive_and_persist
            # (verify_unknown_key). Fall back to standalone for partial dev envs.
            try:
                from ciris_server import LensClient  # type: ignore[import-not-found, import-untyped, unused-ignore]
            except ImportError:
                from ciris_lens_core import LensClient  # type: ignore[import-not-found, import-untyped, unused-ignore]
        except ImportError as e:
            raise RuntimeError(
                "LensClient is REQUIRED in 2.9.6+ (the observability "
                "orchestrator — CIRISAgent#866). It re-hosts from the "
                "ciris-server one wheel (#896); install ciris-server, or "
                "ciris-lens-core for partial dev envs. Import failed: " + str(e)
            ) from e

        # The consent wire artifact: consent:community_trust:v1, written by our
        # consent attestation module on opt-in (grant) and revocation
        # (withdraws/recants — a recant is a hard stop).
        #
        # CIRISPersist#461 confirmation (0.5.118 wheel): this key_id is passed
        # as `consent_attesting_key_id`, but in the COHABITATION path (the one
        # we take — `engine=` is passed below) the wheel's LensClient IGNORES
        # it and gates on the CONFIG-FALLBACK consent (`consent_timestamp` +
        # `_consent_given`) only. The direct per-seal CEG read is the sovereign
        # (`engine=None`) path; wiring it in cohabitation is upstream
        # CIRISEdge#85. So the CEG grant reaches the seal INDIRECTLY: the
        # adapter reads it at boot (current_community_grant_id → _consent_given)
        # and that populates the config-fallback timestamp handed to LensClient.
        # We still resolve + pass the key_id so the sovereign path works
        # unchanged once/if the agent uses it.
        try:
            from ciris_engine.logic.runtime.edge_runtime import get_federation_address

            consent_key_id: Optional[str] = get_federation_address()
        except Exception as e:
            logger.warning(f"Federation address unavailable for consent gate ({e}); config-fallback consent only")
            consent_key_id = None

        # The cross-wheel Engine handshake (CIRISLensCore#43.1, lens-core
        # 1.0.1+): pass the host's wheel-constructed Engine explicitly —
        # lens-core extracts the shared Arc via the CIRISPersist#109 capsule
        # accessors. Without it, lens-core's in-crate singleton (a different
        # static in its statically-bundled persist copy) cannot see this
        # Engine and construction fails in pip cohabitation.
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            raise RuntimeError(
                "LensClient construction requires the persist Engine singleton — "
                "initialize_database() must run before the accord_metrics adapter starts."
            )

        # KEY DIAGNOSTICS (#896): lens traces are Ed25519-signed via the Engine
        # and v10's receive_and_persist verifies the signer key_id against the
        # registered federation keys, rejecting an unknown signer with
        # `verify_unknown_key`. 2.9.7: there is ONE signer identity — the
        # engine's local signer; the derived id is the federation-registered
        # form the substrate verifies against.
        try:
            _engine_local_kid = engine.local_key_id()
        except Exception as _e:  # noqa: BLE001
            _engine_local_kid = f"<err: {_e}>"
        try:
            _engine_derived_kid = engine.local_derived_key_id()
        except Exception as _e:  # noqa: BLE001
            _engine_derived_kid = f"<err: {_e}>"
        logger.info(
            "[LENS_KEY_DIAG] constructing LensClient: engine.local_key_id=%s | "
            "engine.local_derived_key_id=%s | "
            "consent_attesting_key_id(get_federation_address)=%s | trace_level=%s",
            _engine_local_kid,
            _engine_derived_kid,
            consent_key_id,
            self._trace_level.value,
        )

        try:
            return LensClient(
                self._consent_timestamp if self._consent_given else None,
                self._trace_level.value,
                engine=engine,
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

        # Consent is a CEG artifact (2.9.6 fold): the config-fallback consent
        # the cohabitation seal gate reads must be DERIVED FROM THE GRANT, which
        # is the source of truth. If config/env didn't already arm consent,
        # resolve it from the standing community-trust grant BEFORE building the
        # LensClient, so a clean restart (or any boot where the grant already
        # exists) seals from the very first thought. Without this the service
        # only ever saw config/env — which the wizard stopped writing at boot —
        # so every seal resolved NoConsent even with a happy grant on disk.
        consent_source = "config/env" if self._consent_given else None
        if not self._consent_given:
            grant_id = self._derive_consent_from_ceg()
            if grant_id:
                consent_source = f"ceg:grant {grant_id}"

        # REQUIRED substrate leg — raises if unavailable (see docstring)
        self._lens = self._build_lens_client()
        logger.info("   ✅ LensClient constructed (capture→seal→sign→persist owned by substrate)")

        # ONE authoritative, greppable consent one-liner (rides logcat →
        # mobile pull-logs). This is check (a) of the trace-consent validation
        # recipe (FSD/TRACE_CONSENT.md).
        self._log_consent_resolution(consent_source)
        logger.info("=" * 70)

        # Subscribe to reasoning_event_stream for trace capture.
        # Capture happens regardless of consent — lens-core's consent gate
        # decides at each seal (a recant between two seals is enforced at
        # the very next ACTION_RESULT).
        try:
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            self._reasoning_queue = asyncio.Queue(maxsize=REASONING_QUEUE_MAXSIZE)
            reasoning_event_stream.subscribe(self._reasoning_queue)
            self._reasoning_task = asyncio.create_task(self._process_reasoning_events())
            logger.info(f"✅ SUBSCRIBED to reasoning_event_stream (queue maxsize={REASONING_QUEUE_MAXSIZE})")
        except Exception as e:
            logger.error(f"❌ FAILED to subscribe to reasoning_event_stream: {e}")
            logger.error("   Traces will NOT be captured!")

        self._sweep_task = asyncio.create_task(self._periodic_sweep())

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

    @staticmethod
    def _classify_failure(exc: BaseException) -> CaptureHealthState:
        """Map an exception to the degraded state class it drives (#933).

        ``verify_unknown_key`` (persist's unknown-signer rejection at
        ``Engine.receive_and_persist``) is the post-fold analog of the
        2.7.x HTTP 401: an auth/registration failure retrying cannot fix.
        Everything else is presumed transient/retryable.
        """
        if _AUTH_FAILURE_MARKER in str(exc):
            return CaptureHealthState.DEGRADED_AUTH
        return CaptureHealthState.DEGRADED

    def _record_failure(self, streak: FailureStreak, exc: BaseException, context: str) -> None:
        """Count a failure; log ONLY on a state transition (#933).

        The first failure of a streak (or a change of failure class
        mid-streak) logs one ERROR naming the remedy. Steady-state failures
        increment counters (surfaced by get_metrics) and emit a DEBUG
        one-liner instead of an ERROR+traceback per attempt.
        """
        streak.consecutive_failures += 1
        streak.total_failures += 1
        streak.last_error_class = type(exc).__name__
        streak.last_error_message = str(exc)[:300]
        new_state = self._classify_failure(exc)
        if streak.state is not new_state:
            streak.state = new_state
            if new_state is CaptureHealthState.DEGRADED_AUTH:
                # ONE stable ERROR line, no traceback: the cause is known
                # and the remedy is named — a traceback per attempt is the
                # exact #933 anti-pattern.
                logger.error(
                    "[ACCORD_HEALTH] %s DEGRADED (auth) — %s: %s: %s. The engine signer key is "
                    "not registered with the trace verifier (verify_unknown_key). Remedy: register "
                    "the federation signing key with the lens/persist backend (lens collector "
                    "migration or node re-key). Capture keeps running and the service recovers "
                    "automatically once the key is accepted — no restart needed. Further failures "
                    "are counted, not logged (see get_metrics).",
                    streak.domain,
                    context,
                    type(exc).__name__,
                    exc,
                )
            else:
                logger.error(
                    "[ACCORD_HEALTH] %s DEGRADED — %s: %s: %s. First failure of this streak; "
                    "further failures are counted, not logged (see get_metrics).",
                    streak.domain,
                    context,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
        else:
            streak.suppressed_log_count += 1
            logger.debug(
                "[ACCORD_HEALTH] %s still %s (streak=%d): %s: %s",
                streak.domain,
                streak.state.value,
                streak.consecutive_failures,
                type(exc).__name__,
                exc,
            )

    def _record_success(self, streak: FailureStreak) -> None:
        """Close a failure streak; log the recovery transition once (#933)."""
        if streak.state is CaptureHealthState.HEALTHY:
            return
        logger.info(
            "[ACCORD_HEALTH] %s RECOVERED after %d consecutive failure(s) "
            "(%d repeat log line(s) suppressed; last error: %s: %s)",
            streak.domain,
            streak.consecutive_failures,
            streak.suppressed_log_count,
            streak.last_error_class,
            streak.last_error_message,
        )
        streak.state = CaptureHealthState.HEALTHY
        streak.consecutive_failures = 0
        streak.suppressed_log_count = 0

    async def _periodic_sweep(self) -> None:
        """Pace the substrate orphan sweep + events-total persistence.

        Orphaned in-flight traces (no ACTION_RESULT) are ephemeral by
        design — no action means it never happened; the substrate purges
        them after `_orphan_trace_max_age` rather than force-emitting
        partial traces.

        Failure hygiene (#933): this is the only timer-driven loop left in
        the service. While failing it backs off exponentially (base = the
        configured sweep interval, ×SWEEP_BACKOFF_MULTIPLIER per
        consecutive failure, capped at SWEEP_BACKOFF_MAX_SECONDS) and logs
        only the streak's first failure; a clean pass logs recovery once
        and resets the cadence.
        """
        try:
            while True:
                try:
                    await asyncio.sleep(self._sweep_interval_current)
                    if self._lens is not None:
                        purged = await asyncio.to_thread(self._lens.orphan_sweep, int(self._orphan_trace_max_age))
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
                    # 933: a clean pass closes any failure streak and resets
                    # the backed-off cadence (no-op while healthy).
                    self._record_success(self._sweep_streak)
                    self._sweep_interval_current = self._sweep_interval
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise  # Re-raise to exit cleanly
                    # 933: transition-logged, steady-state-counted — no
                    # fixed-cadence traceback spam while the substrate is
                    # down. Back off up to the cap; never below the
                    # configured interval.
                    self._record_failure(self._sweep_streak, e, "periodic sweep")
                    self._sweep_interval_current = max(
                        self._sweep_interval,
                        min(
                            self._sweep_interval_current * SWEEP_BACKOFF_MULTIPLIER,
                            SWEEP_BACKOFF_MAX_SECONDS,
                        ),
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
                # 933: transition-logged, steady-state-counted. The failed
                # event is DROPPED, never re-queued — capture attempts are
                # paced by the reasoning stream itself (no timer), so a
                # persistent substrate fault (e.g. verify_unknown_key while
                # the backend does not know the signer key) cannot become a
                # fixed-cadence retry hot loop; the next reasoning event is
                # the re-probe, and recovery is automatic.
                self._record_failure(
                    self._capture_streak,
                    e,
                    f"capture failed for event {event.get('event_type', '?')} "
                    f"(thought {event.get('thought_id', '?')})",
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

        # Runtime self-heal (throttled, no-op once armed): if a CEG grant landed
        # after boot (mobile first-run wizard — single Chaquopy process), arm the
        # seal here so this event captures into the rebuilt, consent-on client.
        self._maybe_self_heal_consent()

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
        # 933: a successful substrate round-trip closes any failure streak
        # (logs the recovery transition once; no-op while healthy).
        self._record_success(self._capture_streak)
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
                f"[SEAL] sealed thought={thought_id} trace_id={outcome.get('trace_id')} "
                f"✅ TRACE SEALED #{self._traces_completed} "
                f"({inserted} trace_events, {outcome.get('signatures_verified', 0)} signature(s) verified)"
            )
            # Tee the CEG carriers on SEAL — never gated on delivery.
            self._tee_ceg_on_seal(thought_id, outcome.get("trace_id"))
        elif kind == "consent_blocked":
            self._open_thoughts.pop(thought_id, None)
            self._traces_consent_blocked += 1
            # WARNING (not debug): a skipped seal is the exact silent failure the
            # RCA chased — no trace_events row, no error. Greppable in pull-logs
            # as `[SEAL] SKIPPED`. Self-heal (above) normally arms before this;
            # if it still fires, the CEG grant is genuinely absent.
            logger.warning(
                f"[SEAL] SKIPPED thought={thought_id} reason=no-consent "
                f"(substrate reason={outcome.get('reason')}) — opt in via wizard or "
                f"Data & Privacy → Send traces"
            )
        elif kind == "rejected":
            self._events_rejected += 1
            logger.warning(f"🚫 Substrate rejected unknown event_type {outcome.get('raw')!r} (thought {thought_id})")
        # "appended" needs no bookkeeping


    def _tee_ceg_on_seal(self, thought_id: str, trace_id: Optional[str]) -> None:
        """Write the sealed CEG carriers to disk as SIGNED, WIRE-READY envelopes.

        Two properties, both load-bearing:

        1. WRITTEN ON SEAL, NEVER ON SHIP. The substrate's own local-copy tees a
           batch only when that batch ships, so an unreachable canonical yielded
           zero local trace files while the rows sat sealed in persist. Local
           capture must not depend on remote reachability — offline is exactly
           when the corpus matters most.

        2. FULL PQC WIRE FORM. Every column is captured, including
           scrub_signature_classical / scrub_signature_pqc / scrub_key_id /
           scrub_timestamp / original_content_hash / persist_row_hash. An
           envelope without its signatures is not importable into the mesh; it
           is a transcript. What lands here is what a peer would receive and
           can verify.

        Bytes are hex-encoded so the JSON round-trips losslessly.
        """
        if not self._local_copy_dir:
            logger.warning(
                f"⚠️ [{self._adapter_instance_id}] CEG seal NOT teed (no local_copy_dir) "
                f"thought={thought_id} — set local_copy_dir in adapter config or "
                f"CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR"
            )
            return
        if not trace_id:
            logger.warning(
                f"⚠️ [{self._adapter_instance_id}] CEG seal NOT teed (seal returned no trace_id) "
                f"thought={thought_id}"
            )
            return
        try:
            # The persist Engine is a Rust PyO3 object with no Python DBAPI
            # handle, so read the SQLite file directly, READ-ONLY. The runtime
            # holds it in WAL mode; a read-only URI connection is safe alongside
            # the writer and cannot disturb it.
            import sqlite3

            from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()
            like = f"%{trace_id}%"
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
            try:
                cur = conn.execute(
                    "SELECT * FROM federation_attestations "
                    "WHERE CAST(attestation_envelope AS TEXT) LIKE ?",
                    (like,),
                )
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            finally:
                conn.close()
            if not rows:
                logger.warning(
                    f"⚠️ [{self._adapter_instance_id}] CEG seal teed NOTHING: no federation_attestations "
                    f"row matches trace_id={trace_id}. The seal reported success but no carrier row "
                    f"exists — that is a source-side defect, not a capture one."
                )
                return

            def _enc(v: object) -> object:
                if isinstance(v, (bytes, bytearray)):
                    return {"__hex__": bytes(v).hex()}
                return v

            ceg_rows = []
            for r in rows:
                d = {c: _enc(v) for c, v in zip(cols, r)}
                env = d.get("attestation_envelope")
                if isinstance(env, (str, bytes, bytearray)):
                    try:
                        d["attestation_envelope"] = json.loads(
                            env.decode() if isinstance(env, (bytes, bytearray)) else env
                        )
                    except Exception:  # noqa: BLE001 — keep the raw form if it is not JSON
                        pass
                ceg_rows.append(d)

            signed = sum(
                1
                for d in ceg_rows
                if d.get("scrub_signature_classical") or d.get("scrub_signature_pqc")
            )
            payload = {
                "thought_id": thought_id,
                "trace_id": trace_id,
                "adapter_instance": self._adapter_instance_id,
                "trace_level": self._trace_level.value,
                "wire_form": "federation_attestations row, all columns, bytes hex-encoded as {__hex__: ...}",
                "signed_rows": signed,
                "ceg_rows": ceg_rows,
            }
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(trace_id))[:120]
            out = self._local_copy_dir / f"ceg-seal-{safe}.json"
            out.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str))
            if signed == 0:
                logger.warning(
                    f"⚠️ [{self._adapter_instance_id}] CEG seal teed {out.name} but {len(ceg_rows)} row(s) "
                    f"carry NO scrub signature — not mesh-importable as-is (PQC scrub may still be pending)"
                )
            else:
                logger.info(
                    f"📂 [{self._adapter_instance_id}] CEG seal teed: {out.name} — "
                    f"{len(ceg_rows)} carrier row(s), {signed} signed, full wire envelope "
                    f"(written on SEAL, independent of delivery)"
                )
        except Exception as exc:  # noqa: BLE001 — capture must never break the seal
            logger.warning(
                f"⚠️ [{self._adapter_instance_id}] CEG seal tee FAILED trace_id={trace_id}: "
                f"{type(exc).__name__}: {exc}"
            )

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
                # FLAT summary alias (CIRISServer#315 seam sweep): persist's
                # trace-summary projection reads '$.thought_type' off
                # THOUGHT_START at every level — an ENUM (seed/followup/…),
                # zero content, safe at GENERIC. (persist also reads
                # '$.task_description' — that one is TEXT and stays FULL-tier
                # by design; flagged upstream as a wrong-tier read.)
                "thought_type": event.get("thought_type"),
            }
            # DETAILED: Add type identifiers
            if is_detailed:
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
                    idma_data["common_cause_flags"] = idma.get("common_cause_flags") if isinstance(idma, dict) else None
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
                    idma_data["defense_function"] = idma.get("defense_function") if isinstance(idma, dict) else None
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
                # FLAT summary aliases (CIRISServer#315 root cause): persist's
                # trace-summary projection extracts these exact top-level paths
                # (json_extract '$.csdma_plausibility_score' etc., see
                # SQLITE_TRACE_SUMMARY_SELECT). Without them every summary row
                # carries NULL essentials → the capacity scorer's feature
                # matrix drops all rows → emitted=0 → NO trace ever ships.
                # Additive alongside the nested shape the lens reads.
                "csdma_plausibility_score": csdma_data.get("plausibility_score"),
                "dsdma_domain_alignment": dsdma_data.get("domain_alignment"),
                "dsdma_domain": dsdma.get("domain") if isinstance(dsdma, dict) else None,
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
                # FLAT summary aliases (CIRISServer#315 root cause): persist's
                # trace-summary projection reads '$.idma_k_eff' etc. off the
                # IDMA_RESULT payload — idma_k_eff is one of the TWO essential
                # feature dims (with csdma_plausibility_score) whose absence
                # empties the capacity scorer's feature matrix. Additive.
                "idma_k_eff": event.get("k_eff"),
                "idma_correlation_risk": event.get("correlation_risk"),
                "idma_fragility_flag": event.get("fragility_flag"),
                "idma_phase": event.get("phase"),
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
                # FLAT summary aliases (CIRISServer#315 seam sweep): persist's
                # trace-summary projection reads '$.success' (→ action_success)
                # and '$.action_executed' (→ selected_action) off ACTION_RESULT
                # at EVERY trace level. `success` is a bool alias of
                # execution_success; `action_executed` is the handler-action
                # ENUM (speak/ponder/defer/…) — zero content, safe at GENERIC,
                # and without it the summary's selected_action column is dead.
                "success": event.get("execution_success"),
                "action_executed": event.get("action_executed"),
            }
            # DETAILED: Add follow-up, error details, and audit signature
            if is_detailed:
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
                    None if event.get("parent_event_type") == "UNKNOWN_PARENT" else event.get("parent_event_type")
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

        # HOLD (CIRISPersist#203): persist 5.5.x's trace_events component
        # enum does not yet include `deferral_routed` — lens-core 1.0.1
        # accepts the capture, but the seal then fails receive_and_persist
        # with schema_malformed_json, losing the deferring thought's ENTIRE
        # trace. Until the floor ships the variant, count the deferral and
        # skip the capture. Operator override for floor-validation runs:
        # CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS=true.
        if not _capture_deferrals_enabled():
            self._deferrals_held += 1
            logger.info(
                f"🧭 WBD deferral for thought {request.thought_id} HELD from trace capture "
                f"(persist floor lacks deferral_routed variant — CIRISPersist#203; "
                f"held={self._deferrals_held})"
            )
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
            # 933: same capture domain — success closes any streak.
            self._record_success(self._capture_streak)
            self._events_received += 1
            if outcome.get("outcome") == "opened":
                self._open_thoughts[request.thought_id] = time.monotonic()
            logger.info(f"🧭 WBD deferral captured for thought {request.thought_id} (outcome={outcome.get('outcome')})")
        except Exception as e:
            # 933: transition-logged, steady-state-counted (was a full
            # traceback per failed deferral capture).
            self._record_failure(
                self._capture_streak,
                e,
                f"WBD deferral capture (thought {request.thought_id})",
            )

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

    def _derive_consent_from_ceg(self) -> Optional[str]:
        """Resolve consent from the CEG community-trust grant (source of truth).

        The 2.9.6 fold made the ``consent:community_trust:v1`` grant THE consent
        artifact. In the cohabitation seal path lens-core gates on the
        config-fallback consent, so the service must TRANSLATE the grant into
        that fallback. Reads ``current_community_grant_id`` (+ its ``asserted_at``
        for a restart-stable timestamp). On a hit, sets ``_consent_given`` /
        ``_consent_timestamp`` (never clobbering an already-set timestamp) and
        returns the grant id; else returns None. Never raises — a broken read
        leaves consent untouched (capture keeps running; seals stay blocked).
        """
        try:
            from ciris_engine.logic.services.governance.consent.attestation import (
                current_community_grant_asserted_at,
                current_community_grant_id,
            )

            grant_id = current_community_grant_id()
            if not grant_id:
                return None
            self._consent_given = True
            if not self._consent_timestamp:
                self._consent_timestamp = (
                    current_community_grant_asserted_at() or datetime.now(timezone.utc).isoformat()
                )
            return grant_id
        except Exception as exc:  # noqa: BLE001 — best-effort, never break capture
            logger.debug("consent-CEG: service consent derivation skipped (%s): %s", type(exc).__name__, exc)
            return None

    def _log_consent_resolution(self, source: Optional[str]) -> None:
        """Emit the single authoritative ``[CONSENT]`` boot one-liner.

        ARMED when consent resolved (source = ``config/env`` or ``ceg:grant <id>``),
        ABSENT otherwise — with the exact signals checked, so troubleshooting is
        a one-line grep (``grep '\\[CONSENT\\]'`` in mobile pull-logs).
        """
        # CONSENT DRY (opt-in paths 3+4: env var / legacy-convert): capture
        # consent resolving TRUE here does NOT imply the v22 federation grants
        # (consent:replication + CC#46 analyze) exist — those are owner acts.
        # Detect drift via the engine's own resolvers and surface the remedy;
        # never silently author owner-tier grants from a session-less path.
        if self._consent_given:
            try:
                from ciris_engine.logic.services.governance.consent.attestation import (
                    log_federation_consent_drift,
                )

                log_federation_consent_drift(source or "boot")
            except Exception:  # noqa: BLE001 — advisory only
                pass
        if self._consent_given:
            logger.info(
                "[CONSENT] trace consent ARMED — source=%s role=community_trust "
                "target=canonical-community ts=%s → traces WILL seal",
                source or "unknown",
                self._consent_timestamp or "now",
            )
        else:
            config_consent = bool(self._config.get("consent_given", False))
            env_consent = _get_metrics_env("CONSENT", "").lower() == "true"
            # On a first run this fires BEFORE the setup wizard can possibly have
            # granted consent — it describes the expected pre-wizard state, not a
            # fault. Logged as a WARNING saying "traces will NOT seal", it reads
            # as the cause of any later trace problem and gets blamed for
            # failures it precedes by a minute. Say which state this is, and only
            # raise the volume once the wizard has had its chance.
            pre_wizard = not bool(self._config.get("setup_complete", False))
            logger.log(
                logging.INFO if pre_wizard else logging.WARNING,
                "[CONSENT] trace consent %s — traces will not seal yet "
                "(checked: ceg=none config=%s env=%s). %s",
                "not yet granted (pre-wizard, expected)" if pre_wizard else "ABSENT",
                config_consent,
                env_consent,
                (
                    "The setup wizard has not run; it grants consent at the FED-ID step."
                    if pre_wizard
                    else "Opt in via the setup wizard or Data & Privacy → Send traces; the "
                    "service SELF-ARMS at the next reasoning event once the grant lands "
                    "(no restart needed)."
                ),
            )

    def _maybe_self_heal_consent(self) -> None:
        """Throttled runtime re-arm from the CEG grant while consent is OFF.

        Called at the TOP of the event path (before capture), so when a grant
        lands after boot the LensClient is rebuilt BEFORE the first event of the
        next thought opens — that whole thought then captures in the armed
        client and its ACTION_RESULT seals cleanly. No-ops once consent is on.
        """
        if self._consent_given:
            return
        now = time.monotonic()
        # First re-check (sentinel 0.0) is always allowed — don't let a small
        # monotonic epoch right after boot throttle the very first opportunity
        # to arm. Subsequent re-checks are interval-throttled.
        if self._last_consent_recheck != 0.0 and now - self._last_consent_recheck < self._consent_recheck_interval:
            return
        self._last_consent_recheck = now
        grant_id = self._derive_consent_from_ceg()
        if grant_id:
            logger.info(
                "[CONSENT] trace consent SELF-ARMED at runtime — source=ceg:grant %s "
                "ts=%s (grant landed after boot; rebuilding LensClient)",
                grant_id,
                self._consent_timestamp or "now",
            )
            # Rebuild the substrate client so its config-fallback consent picks
            # up the now-armed state (set_consent freezes it at construction).
            if self._lens is not None:
                try:
                    self._lens = self._build_lens_client()
                    logger.info("   [CONSENT] LensClient rebuilt — seals now persist")
                except RuntimeError:
                    logger.exception("   [CONSENT] LensClient rebuild failed after self-arm")

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
            except RuntimeError:
                logger.exception("   LensClient rebuild failed")

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
            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            _engine = get_persist_engine()
            signer_key_id: Optional[str] = _engine.local_derived_key_id() if _engine is not None else None
        except Exception:
            signer_key_id = None

        return {
            "consent_given": self._consent_given,
            "trace_level": self._trace_level.value,
            "events_received": self._events_received,
            "events_sent": self._persisted_events_sent + self._events_sent,
            "events_sent_session": self._events_sent,
            "events_failed": self._events_failed,
            "deferrals_held": self._deferrals_held,
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
            # 933 failure-hygiene surface: the degraded condition is adapter
            # STATE, not a log stream — a steady-state failure is a gauge.
            "capture_state": self._capture_streak.state.value,
            "capture_consecutive_failures": self._capture_streak.consecutive_failures,
            "capture_failures_total": self._capture_streak.total_failures,
            "capture_last_error_class": self._capture_streak.last_error_class or None,
            "sweep_state": self._sweep_streak.state.value,
            "sweep_consecutive_failures": self._sweep_streak.consecutive_failures,
            "sweep_interval_current_seconds": self._sweep_interval_current,
            "failure_logs_suppressed": (
                self._capture_streak.suppressed_log_count + self._sweep_streak.suppressed_log_count
            ),
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
