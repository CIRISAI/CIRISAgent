"""
Tests for AccordMetricsService — post-LensCore-fold surface (CIRISAgent#866).

The trace pipeline (assembly/signing/consent-gate/tee/persistence) is owned
by the ciris-lens-core substrate; what remains agent-side — and what these
tests cover — is:

- Initialization / consent state / env precedence
- Agent ID anonymization (signing-key hash with agent_id fallback)
- Event normalization + `LensClient.capture_event` outcome bookkeeping
  (via a scripted FakeLensClient — the real client is exercised in
  test_lens_fold_integration.py)
- `_extract_component_data` trace-level gating (kept verbatim in the fold)
- WBD deferrals riding the same capture path (DEFERRAL_ROUTED)
- Metrics shape (new post-fold keys)
- Lifecycle: lens-core is a REQUIRED substrate leg — start() raises
"""

import asyncio
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService, SimpleCapabilities, TraceDetailLevel
from ciris_engine.schemas.services.authority_core import DeferralRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeLensClient:
    """Scripted stand-in for ciris_lens_core.LensClient (capture surface).

    `outcomes` is a FIFO of outcome dicts returned by capture_event
    (the dict shape is the frozen FFI contract, hence plain dicts here);
    when exhausted, returns {"outcome": "appended"}. Every component fed
    to capture_event is recorded in `captured`.
    """

    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    captured: List[Dict[str, Any]] = field(default_factory=list)
    orphan_purged: int = 0

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.captured.append(component)
        if self.outcomes:
            return self.outcomes.pop(0)
        return {"outcome": "appended"}

    def orphan_sweep(self, max_age_secs: int) -> int:
        return self.orphan_purged


@dataclass
class EnumLikeEventType:
    """Mimics a ReasoningEventType enum member (has .value)."""

    value: str


def _make_service(trace_level: TraceDetailLevel = TraceDetailLevel.GENERIC) -> AccordMetricsService:
    """Construct a consented service at the given trace level."""
    return AccordMetricsService(
        config={
            "consent_given": True,
            "consent_timestamp": "2026-01-01T00:00:00Z",
            "trace_level": trace_level.value,
        }
    )


def make_deferral_request(
    thought_id: str = "thought-123",
    task_id: str = "task-456",
    reason: str = "Test reason",
    defer_until: datetime = None,
) -> DeferralRequest:
    """Helper to create DeferralRequest with defaults."""
    if defer_until is None:
        defer_until = datetime.now(timezone.utc)
    return DeferralRequest(
        thought_id=thought_id,
        task_id=task_id,
        reason=reason,
        defer_until=defer_until,
    )


def _event(event_type: Any = "THOUGHT_START", thought_id: str = "th-1", **overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "event_type": event_type,
        "thought_id": thought_id,
        "task_id": "task-1",
        "timestamp": "2026-06-09T00:00:00Z",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clean_metrics_env(monkeypatch):
    """Keep service construction deterministic regardless of the host env."""
    for name in (
        "CONSENT",
        "CONSENT_TIMESTAMP",
        "TRACE_LEVEL",
        "LOCAL_COPY_DIR",
        "FLUSH_INTERVAL",
        "ORPHAN_MAX_AGE",
        "CAPTURE_DEFERRALS",
    ):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)
        monkeypatch.delenv(f"CIRIS_COVENANT_METRICS_{name}", raising=False)
    monkeypatch.delenv("CIRIS_SHARE_LOCATION_IN_TRACES", raising=False)


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestSimpleCapabilities:
    """Tests for SimpleCapabilities dataclass."""

    def test_simple_capabilities_creation(self):
        caps = SimpleCapabilities(
            actions=["send_deferral", "accord_metrics"],
            scopes=["accord_compliance"],
        )
        assert caps.actions == ["send_deferral", "accord_metrics"]
        assert caps.scopes == ["accord_compliance"]
        assert caps.supported_domains == []

    def test_get_capabilities(self):
        service = AccordMetricsService()
        caps = service.get_capabilities()

        assert isinstance(caps, SimpleCapabilities)
        assert "send_deferral" in caps.actions
        assert "accord_metrics" in caps.actions
        assert "accord_compliance" in caps.scopes


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceInit:
    """Tests for AccordMetricsService initialization."""

    def test_default_initialization(self):
        service = AccordMetricsService()

        assert service._consent_given is False
        assert service._consent_timestamp is None
        assert service._trace_level == TraceDetailLevel.GENERIC
        assert service._lens is None
        assert service._events_received == 0
        assert service._events_sent == 0
        assert service._events_rejected == 0
        assert service._traces_consent_blocked == 0
        assert service._open_thoughts == {}

    def test_initialization_with_consent(self):
        config = {
            "consent_given": True,
            "consent_timestamp": "2025-01-01T00:00:00Z",
        }
        service = AccordMetricsService(config=config)

        assert service._consent_given is True
        assert service._consent_timestamp == "2025-01-01T00:00:00Z"

    def test_consent_without_timestamp_generates_one(self):
        service = AccordMetricsService(config={"consent_given": True})

        assert service._consent_given is True
        assert service._consent_timestamp is not None

    def test_env_consent_enables(self, monkeypatch):
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP", "2026-02-02T00:00:00Z")
        service = AccordMetricsService()

        assert service._consent_given is True
        assert service._consent_timestamp == "2026-02-02T00:00:00Z"

    def test_legacy_covenant_env_consent_still_works(self, monkeypatch):
        monkeypatch.setenv("CIRIS_COVENANT_METRICS_CONSENT", "true")
        service = AccordMetricsService()

        assert service._consent_given is True

    def test_sweep_interval_default(self):
        service = AccordMetricsService()
        assert service._sweep_interval == 60.0
        # Default orphan max age: max(120, interval * 2)
        assert service._orphan_trace_max_age == 120.0

    def test_sweep_interval_from_config(self):
        service = AccordMetricsService(config={"flush_interval_seconds": 120.0})
        assert service._sweep_interval == 120.0
        assert service._orphan_trace_max_age == 240.0

    def test_sweep_interval_env_overrides_config(self, monkeypatch):
        """FLUSH_INTERVAL env (historical knob) takes precedence over config."""
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_FLUSH_INTERVAL", "5")
        service = AccordMetricsService(config={"flush_interval_seconds": 120.0})
        assert service._sweep_interval == 5.0

    def test_orphan_max_age_from_env(self, monkeypatch):
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_ORPHAN_MAX_AGE", "300")
        service = AccordMetricsService()
        assert service._orphan_trace_max_age == 300.0


class TestTraceDetailLevelParsing:
    """Trace level resolution: config > env > default, invalid -> generic."""

    def test_default_is_generic(self):
        service = AccordMetricsService()
        assert service._trace_level == TraceDetailLevel.GENERIC

    def test_env_sets_level(self, monkeypatch):
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_TRACE_LEVEL", "detailed")
        service = AccordMetricsService()
        assert service._trace_level == TraceDetailLevel.DETAILED

    def test_config_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_TRACE_LEVEL", "detailed")
        service = AccordMetricsService(config={"trace_level": "full_traces"})
        assert service._trace_level == TraceDetailLevel.FULL_TRACES

    def test_invalid_level_falls_back_to_generic(self):
        service = AccordMetricsService(config={"trace_level": "extra_spicy"})
        assert service._trace_level == TraceDetailLevel.GENERIC

    def test_legacy_covenant_env_level(self, monkeypatch):
        monkeypatch.setenv("CIRIS_COVENANT_METRICS_TRACE_LEVEL", "full_traces")
        service = AccordMetricsService()
        assert service._trace_level == TraceDetailLevel.FULL_TRACES


class TestLocalCopyDirInit:
    """Agent-side wiring for the substrate tee dir (the tee itself is
    lens-core's; only the env -> Path probe lives in the service)."""

    def test_unset_env_means_local_copy_disabled(self):
        service = AccordMetricsService()
        assert service._local_copy_dir is None

    def test_set_env_creates_dir_and_enables(self, monkeypatch, tmp_path):
        target = tmp_path / "lens-tee"
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(target))
        service = AccordMetricsService()
        # Per-instance subdir: each LensClient numbers its batches from 0,
        # so instances sharing the base dir would overwrite each other.
        assert service._local_copy_dir == target / "default"
        assert (target / "default").is_dir()

    def test_instance_id_namespaces_tee_subdir(self, monkeypatch, tmp_path):
        target = tmp_path / "lens-tee"
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(target))
        service = AccordMetricsService(config={"adapter_id": "ciris_accord_metrics:full/x"})
        assert service._local_copy_dir == target / "ciris_accord_metrics_full_x"

    def test_unwritable_dir_falls_through_to_disabled(self, monkeypatch, tmp_path):
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("")
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(blocker / "sub"))
        service = AccordMetricsService()
        assert service._local_copy_dir is None


# ---------------------------------------------------------------------------
# Anonymization
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceAnonymization:
    """Agent ID anonymization — signing-key hash with agent_id fallback.

    The autouse conftest mock replaces the unified signing key with a stub
    lacking public_key_bytes, so _compute_instance_hash exercises the
    fallback-id hashing path (the test/no-vault behavior).
    """

    def test_anonymize_agent_id(self):
        service = AccordMetricsService()

        hashed = service._anonymize_agent_id("test-agent-123")

        assert len(hashed) == 16
        assert all(c in "0123456789abcdef" for c in hashed)

    def test_anonymize_same_id_consistent(self):
        service = AccordMetricsService()

        assert service._anonymize_agent_id("test-agent-123") == service._anonymize_agent_id("test-agent-123")

    def test_anonymize_different_ids_different_hashes(self):
        service = AccordMetricsService()

        assert service._anonymize_agent_id("agent-1") != service._anonymize_agent_id("agent-2")

    def test_compute_instance_hash_no_key_no_fallback_is_unknown(self):
        service = AccordMetricsService()

        assert service._compute_instance_hash(fallback_id=None) == "unknown"

    def test_set_agent_id(self):
        service = AccordMetricsService()

        service.set_agent_id("my-agent")

        assert service._agent_id_hash is not None
        assert len(service._agent_id_hash) == 16
        assert service._agent_name == "my-agent"

    def test_set_agent_id_rejects_non_string(self):
        service = AccordMetricsService()

        service.set_agent_id(MagicMock())

        assert service._agent_id_hash is None

    def test_set_agent_id_keeps_existing_agent_name(self):
        service = AccordMetricsService(config={"agent_name": "Configured"})

        service.set_agent_id("Template")

        assert service._agent_name == "Configured"


# ---------------------------------------------------------------------------
# Consent state transitions
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceConsent:
    """set_consent flips flags and rebuilds the substrate client."""

    def test_set_consent_granted(self):
        service = AccordMetricsService()

        service.set_consent(True, "2025-01-01T12:00:00Z")

        assert service._consent_given is True
        assert service._consent_timestamp == "2025-01-01T12:00:00Z"

    def test_set_consent_revoked(self):
        service = AccordMetricsService(config={"consent_given": True})

        service.set_consent(False, "2025-01-01T13:00:00Z")

        assert service._consent_given is False
        assert service._consent_timestamp == "2025-01-01T13:00:00Z"

    def test_set_consent_without_timestamp_generates_one(self):
        service = AccordMetricsService()

        service.set_consent(True)

        assert service._consent_given is True
        assert service._consent_timestamp is not None

    def test_set_consent_does_not_build_client_when_not_started(self):
        """Before start() there is no client handle — nothing to rebuild."""
        service = AccordMetricsService()
        service._build_lens_client = MagicMock()

        service.set_consent(True)

        service._build_lens_client.assert_not_called()
        assert service._lens is None

    def test_set_consent_rebuilds_client_when_started(self):
        """A consent change rebuilds the LensClient handle (the handle
        freezes its config-fallback consent_timestamp at construction)."""
        service = AccordMetricsService(config={"consent_given": True})
        old_lens = FakeLensClient()
        new_lens = FakeLensClient()
        service._lens = old_lens
        service._build_lens_client = MagicMock(return_value=new_lens)

        service.set_consent(False)

        service._build_lens_client.assert_called_once()
        assert service._lens is new_lens

    def test_set_consent_rebuild_failure_keeps_old_client(self):
        """If the rebuild raises RuntimeError, the old handle is retained
        (logged, not raised — consent flags still flipped)."""
        service = AccordMetricsService(config={"consent_given": True})
        old_lens = FakeLensClient()
        service._lens = old_lens
        service._build_lens_client = MagicMock(side_effect=RuntimeError("substrate gone"))

        service.set_consent(False)

        assert service._consent_given is False
        assert service._lens is old_lens


# ---------------------------------------------------------------------------
# Capture path — _process_single_event outcome bookkeeping
# ---------------------------------------------------------------------------


class TestProcessSingleEventBookkeeping:
    """Each of the 5 capture_event outcomes drives distinct bookkeeping."""

    @pytest.mark.asyncio
    async def test_opened_tracks_in_flight_thought(self):
        service = _make_service()
        fake = FakeLensClient(outcomes=[{"outcome": "opened"}])
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", "th-open"))

        assert "th-open" in service._open_thoughts
        # _open_thoughts maps thought_id -> monotonic open time (for the
        # local mirror's orphan aging)
        assert isinstance(service._open_thoughts["th-open"], float)
        assert service._events_received == 1
        assert service.get_metrics()["traces_active"] == 1

    @pytest.mark.asyncio
    async def test_appended_needs_no_bookkeeping(self):
        service = _make_service()
        fake = FakeLensClient(outcomes=[{"outcome": "appended"}])
        service._lens = fake

        await service._process_single_event(_event("CONSCIENCE_RESULT", "th-app"))

        assert service._events_received == 1
        assert service._open_thoughts == {}
        assert service._traces_completed == 0

    @pytest.mark.asyncio
    async def test_sealed_and_persisted_bookkeeping(self):
        service = _make_service()
        fake = FakeLensClient(
            outcomes=[
                {"outcome": "opened"},
                {
                    "outcome": "sealed_and_persisted",
                    "trace_id": "th-seal",
                    "trace_events_inserted": 3,
                    "signatures_verified": 1,
                },
            ]
        )
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", "th-seal"))
        await service._process_single_event(_event("ACTION_RESULT", "th-seal"))

        assert "th-seal" not in service._open_thoughts
        assert service._traces_completed == 1
        assert service._traces_signed == 1
        assert service._events_sent == 3
        assert service._last_send_time is not None

    @pytest.mark.asyncio
    async def test_sealed_without_verified_signature_not_counted_signed(self):
        service = _make_service()
        fake = FakeLensClient(
            outcomes=[
                {
                    "outcome": "sealed_and_persisted",
                    "trace_id": "th-x",
                    "trace_events_inserted": 1,
                    "signatures_verified": 0,
                }
            ]
        )
        service._lens = fake

        await service._process_single_event(_event("ACTION_RESULT", "th-x"))

        assert service._traces_completed == 1
        assert service._traces_signed == 0

    @pytest.mark.asyncio
    async def test_consent_blocked_bookkeeping(self):
        service = _make_service()
        fake = FakeLensClient(
            outcomes=[
                {"outcome": "opened"},
                {"outcome": "consent_blocked", "reason": "NoConsent"},
            ]
        )
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", "th-cb"))
        await service._process_single_event(_event("ACTION_RESULT", "th-cb"))

        assert "th-cb" not in service._open_thoughts
        assert service._traces_consent_blocked == 1
        assert service._traces_completed == 0
        assert service._events_sent == 0

    @pytest.mark.asyncio
    async def test_rejected_bookkeeping(self):
        service = _make_service()
        fake = FakeLensClient(outcomes=[{"outcome": "rejected", "raw": "BOGUS_EVENT"}])
        service._lens = fake

        await service._process_single_event(_event("BOGUS_EVENT", "th-rej"))

        assert service._events_rejected == 1
        assert service._traces_completed == 0

    @pytest.mark.asyncio
    async def test_missing_thought_id_skips_capture(self):
        service = _make_service()
        fake = FakeLensClient()
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", thought_id=""))

        assert fake.captured == []
        assert service._events_received == 0

    @pytest.mark.asyncio
    async def test_lens_not_ready_drops_event(self):
        """Events arriving before start() are dropped (start() raising is
        the enforcement point for a missing substrate)."""
        service = _make_service()
        assert service._lens is None

        await service._process_single_event(_event("THOUGHT_START", "th-early"))

        assert service._events_received == 1
        assert service._open_thoughts == {}


class TestProcessSingleEventComponentShape:
    """Normalization of event_type + the capture_event component contract."""

    @pytest.mark.asyncio
    async def test_enum_event_type_normalized_to_upper_wire_string(self):
        service = _make_service()
        fake = FakeLensClient()
        service._lens = fake

        await service._process_single_event(_event(EnumLikeEventType("thought_start"), "th-enum"))

        assert fake.captured[0]["event_type"] == "THOUGHT_START"

    @pytest.mark.asyncio
    async def test_reasoning_event_prefix_stripped(self):
        service = _make_service()
        fake = FakeLensClient()
        service._lens = fake

        await service._process_single_event(_event("ReasoningEvent.ACTION_RESULT", "th-prefix"))

        assert fake.captured[0]["event_type"] == "ACTION_RESULT"

    @pytest.mark.asyncio
    async def test_component_carries_required_fields(self):
        service = _make_service()
        service.set_agent_id("component-shape-agent")
        fake = FakeLensClient()
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", "th-shape", round_number=2))

        component = fake.captured[0]
        assert component["thought_id"] == "th-shape"
        assert component["task_id"] == "task-1"
        assert component["timestamp"] == "2026-06-09T00:00:00Z"
        assert component["agent_id_hash"] == service._agent_id_hash
        assert component["trace_level"] == TraceDetailLevel.GENERIC.value
        assert component["data"]["round_number"] == 2


# ---------------------------------------------------------------------------
# WBD deferrals (send_deferral) — DEFERRAL_ROUTED via the capture path
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceWBDEvents:
    """Post-fold WBD deferrals ride the same substrate capture path.

    Capture is HELD by default until the persist floor ships the
    `deferral_routed` trace_events variant (CIRISPersist#203) — these
    tests opt in via CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS to exercise
    the capture path itself.
    """

    @pytest.fixture(autouse=True)
    def _enable_deferral_capture(self, monkeypatch):
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS", "true")

    @pytest.mark.asyncio
    async def test_send_deferral_held_by_default(self, monkeypatch):
        """Default (no env): the deferral is counted but never reaches the
        substrate — a sealed trace carrying deferral_routed fails persist
        ingest wholesale (CIRISPersist#203)."""
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_CAPTURE_DEFERRALS", raising=False)
        service = _make_service()
        fake = FakeLensClient(outcomes=[{"outcome": "opened"}])
        service._lens = fake

        result = await service.send_deferral(make_deferral_request(thought_id="th-held"))

        assert result.startswith("wbd-th-held-")
        assert fake.captured == []
        assert service._deferrals_held == 1
        assert service.get_metrics()["deferrals_held"] == 1

    @pytest.mark.asyncio
    async def test_send_deferral_captures_deferral_routed(self):
        service = _make_service()
        service.set_agent_id("test-agent")
        fake = FakeLensClient(outcomes=[{"outcome": "opened"}])
        service._lens = fake

        defer_time = datetime.now(timezone.utc)
        request = make_deferral_request(
            thought_id="thought-123",
            task_id="task-456",
            defer_until=defer_time,
        )

        result = await service.send_deferral(request)

        assert result.startswith("wbd-thought-123-")
        component = fake.captured[0]
        assert component["event_type"] == "DEFERRAL_ROUTED"
        assert component["thought_id"] == "thought-123"
        assert component["task_id"] == "task-456"
        assert component["data"]["defer_until"] == defer_time.isoformat()
        # opened outcome adds the thought to the in-flight set
        assert "thought-123" in service._open_thoughts
        assert service._events_received == 1

    @pytest.mark.asyncio
    async def test_send_deferral_generic_level_omits_reason(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        fake = FakeLensClient()
        service._lens = fake

        await service.send_deferral(make_deferral_request(reason="sensitive text"))

        assert "reason" not in fake.captured[0]["data"]

    @pytest.mark.asyncio
    async def test_send_deferral_detailed_level_truncates_reason(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        fake = FakeLensClient()
        service._lens = fake

        await service.send_deferral(make_deferral_request(reason="x" * 3000))

        assert fake.captured[0]["data"]["reason"] == "x" * 500

    @pytest.mark.asyncio
    async def test_send_deferral_without_lens_still_returns_id(self):
        service = _make_service()
        assert service._lens is None

        result = await service.send_deferral(make_deferral_request(thought_id="th-nolens"))

        assert result.startswith("wbd-th-nolens-")

    @pytest.mark.asyncio
    async def test_send_deferral_capture_failure_does_not_raise(self):
        service = _make_service()

        class _BoomLens:
            def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
                raise RuntimeError("persist handle gone")

        service._lens = _BoomLens()

        result = await service.send_deferral(make_deferral_request(thought_id="th-boom"))

        assert result.startswith("wbd-th-boom-")


# ---------------------------------------------------------------------------
# Guidance stubs
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceStubMethods:
    """Tests for stub methods (fetch_guidance, get_guidance)."""

    @pytest.mark.asyncio
    async def test_fetch_guidance_returns_none(self):
        service = AccordMetricsService()

        assert await service.fetch_guidance({}) is None

    @pytest.mark.asyncio
    async def test_get_guidance_returns_empty(self):
        service = AccordMetricsService()

        result = await service.get_guidance("test question")

        assert result["guidance"] is None
        assert result["confidence"] == 0.0
        assert result["source"] == "accord_metrics"


# ---------------------------------------------------------------------------
# Metrics shape (post-fold keys)
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceMetrics:
    """get_metrics — assert the NEW post-fold key set."""

    def test_get_metrics_shape(self):
        service = AccordMetricsService()

        metrics = service.get_metrics()

        for key in (
            "consent_given",
            "trace_level",
            "events_received",
            "events_sent",
            "events_sent_session",
            "events_failed",
            "events_rejected",
            "events_queued",
            "last_send_time",
            "traces_active",
            "traces_completed",
            "traces_signed",
            "traces_consent_blocked",
            "signer_key_id",
            "has_signing_key",
            "agent_id_hash",
            "substrate",
        ):
            assert key in metrics, f"get_metrics missing key: {key}"

        assert metrics["substrate"] == "ciris-lens-core"
        # No agent-side queue post-fold — always 0
        assert metrics["events_queued"] == 0

    def test_get_metrics_initial_values(self):
        service = AccordMetricsService()

        metrics = service.get_metrics()

        assert metrics["consent_given"] is False
        assert metrics["events_received"] == 0
        assert metrics["events_sent"] == 0
        assert metrics["events_rejected"] == 0
        assert metrics["traces_active"] == 0
        assert metrics["traces_consent_blocked"] == 0
        assert metrics["last_send_time"] is None

    @pytest.mark.asyncio
    async def test_get_metrics_after_capture_outcomes(self):
        service = _make_service()
        fake = FakeLensClient(
            outcomes=[
                {"outcome": "opened"},
                {
                    "outcome": "sealed_and_persisted",
                    "trace_id": "th-m",
                    "trace_events_inserted": 2,
                    "signatures_verified": 1,
                },
                {"outcome": "rejected", "raw": "NOPE"},
            ]
        )
        service._lens = fake

        await service._process_single_event(_event("THOUGHT_START", "th-m"))
        await service._process_single_event(_event("ACTION_RESULT", "th-m"))
        await service._process_single_event(_event("NOPE", "th-m2"))

        metrics = service.get_metrics()

        assert metrics["events_received"] == 3
        assert metrics["events_sent"] == 2
        assert metrics["traces_completed"] == 1
        assert metrics["traces_signed"] == 1
        assert metrics["events_rejected"] == 1
        assert metrics["traces_active"] == 0
        assert metrics["events_queued"] == 0

    def test_events_sent_includes_persisted_total(self):
        service = AccordMetricsService()
        service._persisted_events_sent = 100
        service._events_sent = 5

        metrics = service.get_metrics()

        assert metrics["events_sent"] == 105
        assert metrics["events_sent_session"] == 5


# ---------------------------------------------------------------------------
# Lifecycle — lens-core is a REQUIRED substrate leg
# ---------------------------------------------------------------------------


class TestAccordMetricsServiceLifecycle:
    """start() raises when the substrate can't be constructed; stop is clean."""

    @pytest.mark.asyncio
    async def test_start_raises_when_lens_core_unimportable(self, monkeypatch):
        # None in sys.modules makes `from ciris_lens_core import LensClient`
        # raise ImportError — the "wheel not installed" shape.
        monkeypatch.setitem(sys.modules, "ciris_lens_core", None)
        service = AccordMetricsService()

        with pytest.raises(RuntimeError, match="ciris-lens-core is REQUIRED"):
            await service.start()

    @pytest.mark.asyncio
    async def test_start_raises_when_lens_client_construction_fails(self, monkeypatch):
        boom_mod = types.ModuleType("ciris_lens_core")

        class _BoomLensClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise RuntimeError("no process Engine — host must construct ciris_persist.Engine first")

        boom_mod.LensClient = _BoomLensClient  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "ciris_lens_core", boom_mod)
        service = AccordMetricsService()

        with pytest.raises(RuntimeError, match="LensClient construction failed"):
            await service.start()

    @pytest.mark.asyncio
    async def test_start_and_stop_clean_with_fake_substrate(self, monkeypatch):
        service = _make_service()
        fake = FakeLensClient()
        monkeypatch.setattr(service, "_build_lens_client", lambda: fake)

        await service.start()

        assert service._lens is fake
        assert service._reasoning_task is not None
        assert service._sweep_task is not None

        await service.stop()

        assert service._reasoning_task.done()
        assert service._sweep_task.done()

    @pytest.mark.asyncio
    async def test_start_sets_agent_id_from_constructor(self, monkeypatch):
        service = AccordMetricsService(
            config={"consent_given": True, "consent_timestamp": "2026-01-01T00:00:00Z"},
            agent_id="ctor-agent",
        )
        fake = FakeLensClient()
        monkeypatch.setattr(service, "_build_lens_client", lambda: fake)

        await service.start()
        try:
            assert service._agent_id_hash is not None
            assert service._agent_name == "ctor-agent"
        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_clean(self):
        service = AccordMetricsService()

        await service.stop()  # must not raise


# ---------------------------------------------------------------------------
# Deployment profile builder
# ---------------------------------------------------------------------------


class TestBuildDeploymentProfile:
    """FSD §3.2 — operator config wins, migration defaults otherwise."""

    def test_defaults_without_any_config(self):
        service = AccordMetricsService()

        profile = service._build_deployment_profile()

        assert profile == {
            "agent_role": "unknown",
            "agent_template": "unknown-default-unspecified",
            "deployment_domain": "general",
            "deployment_type": "production",
            "deployment_region": None,
            "deployment_trust_mode": "sovereign",
        }

    def test_defaults_derive_from_agent_name(self):
        service = AccordMetricsService(config={"agent_name": "Ally"})

        profile = service._build_deployment_profile()

        assert profile["agent_role"] == "ally"
        assert profile["agent_template"] == "Ally-default-unspecified"

    def test_operator_declared_values_win(self):
        service = AccordMetricsService(
            config={
                "agent_name": "Ally",
                "agent_role": "moderator",
                "agent_template": "echo-core-v2",
                "deployment_domain": "community",
                "deployment_type": "staging",
                "deployment_region": "eu-west-1",
                "deployment_trust_mode": "managed",
            }
        )

        profile = service._build_deployment_profile()

        assert profile == {
            "agent_role": "moderator",
            "agent_template": "echo-core-v2",
            "deployment_domain": "community",
            "deployment_type": "staging",
            "deployment_region": "eu-west-1",
            "deployment_trust_mode": "managed",
        }

    def test_profile_field_set_locked_at_six(self):
        """The 6-field block is the wire contract — additions need the FSD."""
        service = AccordMetricsService()

        assert len(service._build_deployment_profile()) == 6


# ---------------------------------------------------------------------------
# DSAR deletion hook (log-only post-fold)
# ---------------------------------------------------------------------------


class TestQueueLensDeletionOnRevoke:
    """Post-fold the method is log-only — deletion rides the CEG recant
    cascade; this just preserves the my_data.py call-contract."""

    def test_log_only_no_state_mutation(self):
        service = _make_service()
        service.set_agent_id("dsar-agent")
        before = service.get_metrics()

        service.queue_lens_deletion_on_revoke()  # must not raise

        assert service.get_metrics() == before

    def test_works_without_agent_id(self):
        service = AccordMetricsService()

        service.queue_lens_deletion_on_revoke()  # must not raise


# ---------------------------------------------------------------------------
# _extract_component_data — trace-level gating (kept verbatim in the fold)
# ---------------------------------------------------------------------------


def _llm_call_event_dict(**overrides: Any) -> Dict[str, Any]:
    """Reasoning event dict shaped like what reasoning_event_stream ships."""
    base = {
        "event_type": "LLM_CALL",
        "thought_id": "th_test",
        "task_id": "task_test",
        "timestamp": "2026-04-30T15:00:00Z",
        "handler_name": "EthicalPDMA",
        "service_name": "OpenAICompatibleLLM",
        "model": "google/gemma-4-31B-it",
        "base_url": "https://api.together.xyz/v1",
        "response_model": "EthicalDMAResult",
        "duration_ms": 90000.0,
        "prompt_tokens": 8192,
        "completion_tokens": 512,
        "prompt_bytes": 32666,
        "completion_bytes": 1024,
        "cost_usd": 0.0123,
        "status": "ok",
        "error_class": None,
        "attempt_count": 1,
        "retry_count": 0,
        "prompt_hash": "0" * 64,
        "prompt": "<full prompt text here>",
        "response_text": "<full completion here>",
    }
    base.update(overrides)
    return base


def _verb_second_pass_event_dict(**overrides: Any) -> Dict[str, Any]:
    base = {
        "event_type": "VERB_SECOND_PASS_RESULT",
        "thought_id": "th_test",
        "task_id": "task_test",
        "timestamp": "2026-04-30T15:00:00Z",
        "verb": "tool",
        "original_action": "tool",
        "original_reasoning": "ASPDMA selected curl",
        "final_action": "speak",
        "final_reasoning": "TSASPDMA wants clarification",
        "verb_specific_data": {
            "original_tool_name": "curl",
            "final_tool_name": None,
            "original_parameters": {},
            "final_parameters": {"content": "clarify"},
        },
        "second_pass_prompt": "<full TSASPDMA prompt>",
    }
    base.update(overrides)
    return base


class TestLlmCallExtractComponentData:
    """Per-LLM-call event builder. The trace-level gating is the privacy
    contract — full prompt/response text is FULL only, hash is DETAILED+,
    nothing content-bearing at GENERIC."""

    def test_generic_excludes_prompt_hash_and_text(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("LLM_CALL", _llm_call_event_dict())

        # Cheap fields always present — needed for cost/latency monitoring
        assert data["handler_name"] == "EthicalPDMA"
        assert data["service_name"] == "OpenAICompatibleLLM"
        assert data["model"] == "google/gemma-4-31B-it"
        assert data["duration_ms"] == 90000.0
        assert data["prompt_tokens"] == 8192
        assert data["completion_tokens"] == 512
        assert data["status"] == "ok"
        # GENERIC privacy contract: no content-bearing fields
        assert "prompt_hash" not in data
        assert "prompt" not in data
        assert "response_text" not in data

    def test_detailed_adds_prompt_hash(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        data = service._extract_component_data("LLM_CALL", _llm_call_event_dict())

        assert data["prompt_hash"] == "0" * 64
        # DETAILED still excludes the actual content
        assert "prompt" not in data
        assert "response_text" not in data

    def test_full_traces_adds_prompt_and_response(self):
        service = _make_service(TraceDetailLevel.FULL_TRACES)
        data = service._extract_component_data("LLM_CALL", _llm_call_event_dict())

        assert data["prompt"] == "<full prompt text here>"
        assert data["response_text"] == "<full completion here>"
        assert data["prompt_hash"] == "0" * 64  # DETAILED includes still apply

    def test_failure_event_carries_error_class(self):
        """status + error_class land at GENERIC, not gated."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(
            status="timeout",
            error_class="ReadTimeout",
            completion_tokens=None,
            completion_bytes=None,
        )
        data = service._extract_component_data("LLM_CALL", event)

        assert data["status"] == "timeout"
        assert data["error_class"] == "ReadTimeout"
        assert data["completion_tokens"] is None


class TestLlmCallParentEventTypeWireContract:
    """parent_event_type wire contract (TRACE_WIRE_FORMAT.md §5.10):
    persist's BatchEvent.parent_event_type is Option<ReasoningEventType>;
    the agent-side WARN sentinel "UNKNOWN_PARENT" must never reach the wire
    (a non-enum string 422s the whole batch — CIRISLens#13 driver)."""

    def test_unknown_parent_normalized_to_none(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(parent_event_type="UNKNOWN_PARENT", parent_attempt_index=None)
        data = service._extract_component_data("LLM_CALL", event)

        assert data["parent_event_type"] is None

    @pytest.mark.parametrize(
        "parent_event_type",
        ["DMA_RESULTS", "ASPDMA_RESULT", "CONSCIENCE_RESULT", "IDMA_RESULT"],
    )
    def test_valid_enum_values_pass_through_unchanged(self, parent_event_type: str):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(parent_event_type=parent_event_type, parent_attempt_index=0)
        data = service._extract_component_data("LLM_CALL", event)

        assert data["parent_event_type"] == parent_event_type
        assert data["parent_attempt_index"] == 0

    def test_absent_parent_is_none(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("LLM_CALL", _llm_call_event_dict())

        assert data["parent_event_type"] is None


class TestVerbSecondPassExtractComponentData:
    """Verb discriminator + opaque verb_specific_data at GENERIC; reasoning
    text DETAILED+; the second-pass prompt FULL only."""

    def test_generic_carries_verb_and_action_and_payload(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", _verb_second_pass_event_dict())

        assert data["verb"] == "tool"
        assert data["original_action"] == "tool"
        assert data["final_action"] == "speak"
        assert data["verb_specific_data"]["original_tool_name"] == "curl"
        assert data["verb_specific_data"]["final_parameters"] == {"content": "clarify"}
        assert "original_reasoning" not in data
        assert "final_reasoning" not in data
        assert "second_pass_prompt" not in data

    def test_detailed_adds_reasoning_text(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", _verb_second_pass_event_dict())

        assert data["original_reasoning"] == "ASPDMA selected curl"
        assert data["final_reasoning"] == "TSASPDMA wants clarification"
        assert "second_pass_prompt" not in data

    def test_full_adds_second_pass_prompt(self):
        service = _make_service(TraceDetailLevel.FULL_TRACES)
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", _verb_second_pass_event_dict())

        assert data["second_pass_prompt"] == "<full TSASPDMA prompt>"

    def test_defer_verb_specific_data_passes_through(self):
        """verb_specific_data is per-verb — schema-agnostic passthrough."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _verb_second_pass_event_dict(
            verb="defer",
            original_action="defer",
            final_action="defer",
            verb_specific_data={
                "rights_basis": ["fair_trial"],
                "primary_need_category": "justice_and_legal_agency",
                "domain_hint": "legal",
                "operational_reason": "licensed_domain_required",
            },
        )
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", event)

        assert data["verb"] == "defer"
        assert data["verb_specific_data"]["rights_basis"] == ["fair_trial"]
        assert data["verb_specific_data"]["domain_hint"] == "legal"
        assert "original_tool_name" not in data["verb_specific_data"]


class TestConscienceResultIsRecursive:
    """is_recursive must be present at GENERIC so the lens distinguishes
    initial from recursive conscience passes without inference (§5.8)."""

    def _conscience_event(self, **overrides: Any) -> Dict[str, Any]:
        base = {
            "event_type": "CONSCIENCE_RESULT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "conscience_passed": True,
        }
        base.update(overrides)
        return base

    def test_is_recursive_present_at_generic_level(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data(
            "CONSCIENCE_RESULT", self._conscience_event(action_was_overridden=False, is_recursive=False)
        )
        assert "is_recursive" in data
        assert data["is_recursive"] is False

    def test_is_recursive_true_for_recursive_pass(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data(
            "CONSCIENCE_RESULT",
            self._conscience_event(conscience_passed=False, action_was_overridden=True, is_recursive=True),
        )
        assert data["is_recursive"] is True
        assert data["action_was_overridden"] is True

    def test_is_recursive_defaults_to_false_when_missing(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("CONSCIENCE_RESULT", self._conscience_event())
        assert data.get("is_recursive") is False


class TestSnapshotAndContextCirisVerifyFields:
    """Pin the CIRISVerify attestation field set on SNAPSHOT_AND_CONTEXT.
    Each `*_ok` boolean is an independent k_eff dimension at GENERIC;
    key identity fields are DETAILED-gated."""

    def _snapshot_event_with_attestation(self) -> Dict[str, Any]:
        return {
            "event_type": "SNAPSHOT_AND_CONTEXT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "system_snapshot": {
                "cognitive_state": "work",
                "verify_attestation": {
                    "attestation_level": 3,
                    "attestation_status": "verified",
                    "attestation_summary": "Level 3/5 | ✓Binary ✓Environment ✓Registry",
                    "disclosure_severity": "info",
                    "disclosure_text": "",
                    "binary_ok": True,
                    "env_ok": True,
                    "registry_ok": True,
                    "file_integrity_ok": False,
                    "audit_ok": False,
                    "play_integrity_ok": False,
                    "hardware_backed": True,
                    "key_status": "local",
                    "key_id": "agent-test",
                    "ed25519_fingerprint": "0123abcd" * 8,
                    "key_storage_mode": "TPM",
                    "hardware_type": "TpmFirmware",
                    "verify_version": "1.6.3",
                },
            },
        }

    def test_generic_carries_full_per_check_boolean_set(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation())
        for fname in (
            "binary_ok",
            "env_ok",
            "registry_ok",
            "file_integrity_ok",
            "audit_ok",
            "play_integrity_ok",
            "hardware_backed",
        ):
            assert fname in data, f"GENERIC missing CIRISVerify check field: {fname}"
        assert data["binary_ok"] is True
        assert data["registry_ok"] is True
        assert data["file_integrity_ok"] is False

    def test_generic_carries_attestation_summary_fields(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation())
        for fname in (
            "attestation_level",
            "attestation_status",
            "attestation_context",
            "disclosure_severity",
        ):
            assert fname in data, f"GENERIC missing attestation summary field: {fname}"
        assert data["attestation_level"] == 3
        assert data["attestation_status"] == "verified"
        assert "Level 3/5" in data["attestation_context"]

    def test_detailed_adds_key_identifying_fields(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation())
        for fname in (
            "key_status",
            "key_id",
            "ed25519_fingerprint",
            "key_storage_mode",
            "hardware_type",
            "verify_version",
        ):
            assert fname in data, f"DETAILED missing key/version field: {fname}"
        assert data["ed25519_fingerprint"] == "0123abcd" * 8
        assert data["hardware_type"] == "TpmFirmware"

    def test_generic_does_not_leak_key_identity(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation())
        for fname in ("ed25519_fingerprint", "key_id", "key_status"):
            assert fname not in data, f"GENERIC unexpectedly leaks identifying field: {fname}"

    def test_attestation_absent_when_verify_not_run(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = {
            "event_type": "SNAPSHOT_AND_CONTEXT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "system_snapshot": {"cognitive_state": "work"},  # no verify_attestation
        }
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", event)
        assert data["attestation_level"] == 0
        assert data["attestation_status"] == "not_attempted"
        # None (not run) is distinct from False (ran and failed)
        assert data["binary_ok"] is None
        assert data["env_ok"] is None


class TestEventToComponentMapping:
    """EVENT_TO_COMPONENT routes events to trace component_type — pin the
    entries that decide the lens column an event lands in."""

    def test_llm_call_maps_to_llm_call_component(self):
        assert AccordMetricsService.EVENT_TO_COMPONENT["LLM_CALL"] == "llm_call"
        assert AccordMetricsService.EVENT_TO_COMPONENT["ReasoningEvent.LLM_CALL"] == "llm_call"

    def test_verb_second_pass_maps_to_verb_second_pass_component(self):
        assert AccordMetricsService.EVENT_TO_COMPONENT["VERB_SECOND_PASS_RESULT"] == "verb_second_pass"
        assert AccordMetricsService.EVENT_TO_COMPONENT["ReasoningEvent.VERB_SECOND_PASS_RESULT"] == "verb_second_pass"

    def test_legacy_tsaspdma_still_maps_to_rationale(self):
        assert AccordMetricsService.EVENT_TO_COMPONENT["TSASPDMA_RESULT"] == "rationale"

    def test_commons_credits_events_mapped(self):
        for name in (
            "DEFERRAL_ROUTED",
            "DEFERRAL_RECEIVED",
            "DEFERRAL_RESOLVED",
            "GRATITUDE_SIGNALED",
            "CREDIT_GENERATED",
        ):
            assert AccordMetricsService.EVENT_TO_COMPONENT[name] == name.lower()


# ---------------------------------------------------------------------------
# Stream plumbing — _handle_reasoning_event fan-out
# ---------------------------------------------------------------------------


class TestHandleReasoningEvent:
    """Stream updates carry a list of events; each is fed to the substrate."""

    @pytest.mark.asyncio
    async def test_fans_out_each_event_in_update(self):
        service = _make_service()
        fake = FakeLensClient()
        service._lens = fake

        await service._handle_reasoning_event(
            {
                "events": [
                    _event("THOUGHT_START", "th-f1"),
                    _event("CONSCIENCE_RESULT", "th-f1"),
                ]
            }
        )

        assert len(fake.captured) == 2
        assert [c["event_type"] for c in fake.captured] == ["THOUGHT_START", "CONSCIENCE_RESULT"]

    @pytest.mark.asyncio
    async def test_empty_update_is_noop(self):
        service = _make_service()
        fake = FakeLensClient()
        service._lens = fake

        await service._handle_reasoning_event({})

        assert fake.captured == []

    @pytest.mark.asyncio
    async def test_one_bad_event_does_not_drop_the_rest(self):
        """Per-event isolation: a capture failure increments events_failed
        and the remaining events in the update (which may include the
        ACTION_RESULT seal) still reach the substrate."""
        service = _make_service()

        class _FlakyLens:
            def __init__(self) -> None:
                self.captured: List[Dict[str, Any]] = []

            def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
                if component["thought_id"] == "th-bad":
                    raise RuntimeError("substrate hiccup")
                self.captured.append(component)
                return {"outcome": "appended"}

        flaky = _FlakyLens()
        service._lens = flaky

        await service._handle_reasoning_event(
            {
                "events": [
                    _event("THOUGHT_START", "th-bad"),
                    _event("ACTION_RESULT", "th-good"),
                ]
            }
        )

        assert service._events_failed == 1
        assert [c["thought_id"] for c in flaky.captured] == ["th-good"]
        assert service.get_metrics()["events_failed"] == 1
