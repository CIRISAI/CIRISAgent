"""
Tests for Commons Credits: agent credit schemas, WiseBus domain auto-deferral,
CIRISNode credit generation, and anti-gaming policy.
"""

import hashlib
from datetime import datetime, timezone

import pytest

from ciris_engine.schemas.services.agent_credits import (
    AgentCreditSummary,
    CreditGenerationPolicy,
    CreditRecord,
    CreditRecordBatch,
    DomainCategory,
    DomainDeferralRequired,
    DualSignature,
    GratitudeSignal,
    InteractionOutcome,
)
from ciris_engine.schemas.services.context import DeferralContext

# =========================================================================
# Schema Tests
# =========================================================================


class TestInteractionOutcome:
    def test_enum_values(self) -> None:
        assert InteractionOutcome.RESOLVED == "resolved"
        assert InteractionOutcome.PARTIAL == "partial"
        assert InteractionOutcome.UNRESOLVED == "unresolved"
        assert InteractionOutcome.REJECTED == "rejected"


class TestDomainCategory:
    def test_all_requires_separate_module_domains(self) -> None:
        """Verify DomainCategory covers all REQUIRES_SEPARATE_MODULE domains."""
        expected = {
            "MEDICAL",
            "FINANCIAL",
            "LEGAL",
            "HOME_SECURITY",
            "IDENTITY_VERIFICATION",
            "CONTENT_MODERATION",
            "RESEARCH",
            "INFRASTRUCTURE_CONTROL",
        }
        actual = {d.value for d in DomainCategory}
        assert actual == expected


class TestDualSignature:
    def test_create_ed25519_only(self) -> None:
        sig = DualSignature(
            ed25519_signature="abc123",
            ed25519_key_id="agent-abc123def456",
        )
        assert sig.ed25519_signature == "abc123"
        assert sig.ml_dsa_65_signature is None

    def test_create_full_dual(self) -> None:
        sig = DualSignature(
            ed25519_signature="abc123",
            ed25519_key_id="agent-abc123def456",
            ml_dsa_65_signature="pq_sig_here",
            ml_dsa_65_key_id="agent-pq-key",
        )
        assert sig.ml_dsa_65_signature == "pq_sig_here"


class TestCreditRecord:
    def _make_signature(self) -> DualSignature:
        return DualSignature(
            ed25519_signature="test_sig",
            ed25519_key_id="agent-testkey123",
        )

    def test_compute_interaction_id_deterministic(self) -> None:
        """Interaction ID must be the same regardless of which agent computes it."""
        id1 = CreditRecord.compute_interaction_id("trace-A", "trace-B")
        id2 = CreditRecord.compute_interaction_id("trace-B", "trace-A")
        assert id1 == id2

    def test_compute_interaction_id_different_traces(self) -> None:
        id1 = CreditRecord.compute_interaction_id("trace-A", "trace-B")
        id2 = CreditRecord.compute_interaction_id("trace-A", "trace-C")
        assert id1 != id2

    def test_compute_interaction_id_format(self) -> None:
        """Interaction ID should be 16 hex characters."""
        iid = CreditRecord.compute_interaction_id("trace-1", "trace-2")
        assert len(iid) == 16
        # Verify it's valid hex
        int(iid, 16)

    def test_create_full_record(self) -> None:
        now = datetime.now(timezone.utc)
        record = CreditRecord(
            interaction_id="abc123def4567890",
            requesting_agent_id="agent_a_hash",
            resolving_agent_id="agent_b_hash",
            requesting_trace_id="trace-a-123",
            resolving_trace_id="trace-b-456",
            outcome=InteractionOutcome.RESOLVED,
            domain_category=DomainCategory.MEDICAL,
            coherence_score=0.85,
            requesting_agent_signature=self._make_signature(),
            node_attestation="node_sig_here",
            node_attestation_key_id="node-key-123",
            created_at=now,
            resolved_at=now,
        )
        assert record.outcome == InteractionOutcome.RESOLVED
        assert record.domain_category == DomainCategory.MEDICAL
        assert record.coherence_score == 0.85
        assert record.resolving_agent_signature is None

    def test_coherence_score_validation(self) -> None:
        """Coherence score must be between 0 and 1."""
        with pytest.raises(Exception):
            CreditRecord(
                interaction_id="test",
                requesting_agent_id="a",
                resolving_agent_id="b",
                requesting_trace_id="t1",
                resolving_trace_id="t2",
                outcome=InteractionOutcome.RESOLVED,
                coherence_score=1.5,  # Invalid
                requesting_agent_signature=self._make_signature(),
                created_at=datetime.now(timezone.utc),
            )


class TestGratitudeSignal:
    def test_create_signal(self) -> None:
        sig = DualSignature(
            ed25519_signature="test",
            ed25519_key_id="agent-test",
        )
        signal = GratitudeSignal(
            from_agent_id="agent_a",
            to_agent_id="agent_b",
            interaction_id="interaction_123",
            quality_score=0.9,
            message="Thank you for the help!",
            signature=sig,
            timestamp=datetime.now(timezone.utc),
        )
        assert signal.quality_score == 0.9
        assert signal.message == "Thank you for the help!"

    def test_quality_score_bounds(self) -> None:
        """Quality score must be 0-1."""
        with pytest.raises(Exception):
            GratitudeSignal(
                from_agent_id="a",
                to_agent_id="b",
                interaction_id="x",
                quality_score=-0.1,  # Invalid
                signature=DualSignature(ed25519_signature="s", ed25519_key_id="k"),
                timestamp=datetime.now(timezone.utc),
            )


class TestAgentCreditSummary:
    def test_default_values(self) -> None:
        summary = AgentCreditSummary(
            agent_id="test_agent",
            computed_at=datetime.now(timezone.utc),
        )
        assert summary.total_interactions == 0
        assert summary.k_eff == 1.0
        assert summary.governance_weight == 0.0
        assert summary.domain_expertise == {}

    def test_with_interactions(self) -> None:
        summary = AgentCreditSummary(
            agent_id="test_agent",
            total_interactions=50,
            resolved_interactions=45,
            average_coherence=0.8,
            k_eff=3.5,
            unique_partners=12,
            domain_expertise={"MEDICAL": 10, "LEGAL": 5},
            governance_weight=126.0,
            computed_at=datetime.now(timezone.utc),
        )
        assert summary.unique_partners == 12
        assert summary.domain_expertise["MEDICAL"] == 10


class TestCreditGenerationPolicy:
    def test_default_policy(self) -> None:
        policy = CreditGenerationPolicy(policy_version="2026-04-08")
        assert policy.cooldown_seconds == 60
        assert policy.max_daily_interactions_per_pair == 10
        assert policy.coherence_threshold == 0.3
        assert policy.circular_deferral_window_seconds == 300
        assert policy.min_attestation_level == 2

    def test_custom_policy(self) -> None:
        policy = CreditGenerationPolicy(
            policy_version="2026-04-08",
            cooldown_seconds=120,
            max_daily_interactions_per_pair=5,
            coherence_threshold=0.5,
            policy_signature="signed_by_l3c",
            policy_key_id="ciris-l3c-root",
        )
        assert policy.cooldown_seconds == 120
        assert policy.policy_signature == "signed_by_l3c"

    def test_coherence_threshold_validation(self) -> None:
        """Coherence threshold must be 0-1."""
        with pytest.raises(Exception):
            CreditGenerationPolicy(
                policy_version="2026-04-08",
                coherence_threshold=1.5,
            )


class TestDomainDeferralRequired:
    def test_create_signal(self) -> None:
        signal = DomainDeferralRequired(
            category=DomainCategory.MEDICAL,
            capability="diagnosis",
            reason="MEDICAL capability 'diagnosis' requires licensed domain handler.",
        )
        assert signal.category == DomainCategory.MEDICAL
        assert signal.capability == "diagnosis"


# =========================================================================
# DeferralContext domain_hint Tests
# =========================================================================


class TestDeferralContextDomainHint:
    def test_domain_hint_field(self) -> None:
        ctx = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Domain deferral",
            domain_hint="MEDICAL",
        )
        assert ctx.domain_hint == "MEDICAL"

    def test_domain_hint_optional(self) -> None:
        ctx = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Normal deferral",
        )
        assert ctx.domain_hint is None

    def test_domain_hint_in_metadata(self) -> None:
        """domain_hint should be a first-class field, not buried in metadata."""
        ctx = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="test",
            domain_hint="FINANCIAL",
            metadata={"extra": "data"},
        )
        assert ctx.domain_hint == "FINANCIAL"
        assert "extra" in ctx.metadata


# =========================================================================
# WiseBus Auto-Deferral Tests
# =========================================================================


class TestWiseBusValidateCapability:
    """Test that _validate_capability returns DomainDeferralRequired
    for REQUIRES_SEPARATE_MODULE instead of raising ValueError."""

    def _make_bus(self):
        """Create a WiseBus with minimal mocking."""
        from unittest.mock import MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = []
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        return WiseBus(
            service_registry=mock_registry,
            time_service=mock_time,
        )

    def test_medical_returns_deferral_signal(self) -> None:
        bus = self._make_bus()
        result = bus._validate_capability("diagnosis", agent_tier=1)
        assert result is not None
        assert isinstance(result, DomainDeferralRequired)
        assert result.category == DomainCategory.MEDICAL

    def test_financial_returns_deferral_signal(self) -> None:
        bus = self._make_bus()
        result = bus._validate_capability("investment_advice", agent_tier=1)
        assert result is not None
        assert result.category == DomainCategory.FINANCIAL

    def test_legal_returns_deferral_signal(self) -> None:
        bus = self._make_bus()
        result = bus._validate_capability("legal_advice", agent_tier=1)
        assert result is not None
        assert result.category == DomainCategory.LEGAL

    def test_never_allowed_still_raises(self) -> None:
        """NEVER_ALLOWED capabilities must still raise ValueError."""
        bus = self._make_bus()
        with pytest.raises(ValueError, match="ABSOLUTELY PROHIBITED"):
            bus._validate_capability("weapon_design", agent_tier=1)

    def test_safe_capability_returns_none(self) -> None:
        """Non-prohibited capabilities should return None."""
        bus = self._make_bus()
        result = bus._validate_capability("general_chat", agent_tier=1)
        assert result is None

    def test_none_capability_returns_none(self) -> None:
        bus = self._make_bus()
        result = bus._validate_capability(None, agent_tier=1)
        assert result is None

    def test_community_mod_tier_restricted(self) -> None:
        """Community moderation should still raise for low-tier agents."""
        bus = self._make_bus()
        with pytest.raises(ValueError, match="TIER RESTRICTED"):
            bus._validate_capability("notify_moderators", agent_tier=1)

    def test_community_mod_allowed_tier4(self) -> None:
        """Community moderation should be allowed for Tier 4+ agents."""
        bus = self._make_bus()
        result = bus._validate_capability("notify_moderators", agent_tier=4)
        assert result is None


# =========================================================================
# WiseBus Domain-Based Deferral Routing Tests
# =========================================================================


class TestWiseBusDomainFiltering:
    """Test that WiseBus filters services by supported_domains when routing deferrals."""

    @pytest.mark.asyncio
    async def test_filters_services_by_domain(self) -> None:
        """Services without the required domain should not receive deferrals."""
        from dataclasses import dataclass, field
        from typing import List
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        @dataclass
        class MockCapabilities:
            actions: List[str]
            scopes: List[str]
            supported_domains: List[str] = field(default_factory=list)

        # Create mock services - one supports MEDICAL, one doesn't
        medical_service = MagicMock()
        medical_service.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
            supported_domains=["MEDICAL", "RESEARCH"],
        )
        medical_service.send_deferral = AsyncMock(return_value="deferred_123")

        financial_service = MagicMock()
        financial_service.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
            supported_domains=["FINANCIAL"],
        )
        financial_service.send_deferral = AsyncMock(return_value="deferred_456")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [medical_service, financial_service]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        # Send a MEDICAL deferral - should only go to medical_service
        context = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Medical consultation needed",
            domain_hint="MEDICAL",
        )
        result = await bus.send_deferral(context, "test_handler")

        assert result is True
        medical_service.send_deferral.assert_called_once()
        financial_service.send_deferral.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_domain_hint_broadcasts_to_all(self) -> None:
        """Without domain_hint, should broadcast to all services."""
        from dataclasses import dataclass, field
        from typing import List
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        @dataclass
        class MockCapabilities:
            actions: List[str]
            scopes: List[str]
            supported_domains: List[str] = field(default_factory=list)

        service_a = MagicMock()
        service_a.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
            supported_domains=["MEDICAL"],
        )
        service_a.send_deferral = AsyncMock(return_value="deferred_a")

        service_b = MagicMock()
        service_b.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
            supported_domains=["FINANCIAL"],
        )
        service_b.send_deferral = AsyncMock(return_value="deferred_b")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [service_a, service_b]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        # Send deferral without domain_hint - should go to both
        context = DeferralContext(
            thought_id="t2",
            task_id="task2",
            reason="Human review needed",
            domain_hint=None,  # No domain hint
        )
        result = await bus.send_deferral(context, "test_handler")

        assert result is True
        service_a.send_deferral.assert_called_once()
        service_b.send_deferral.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_without_get_capabilities_skipped(self) -> None:
        """Services without get_capabilities method are skipped with warning."""
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        # Service without get_capabilities method
        service_no_caps = MagicMock(spec=[])  # Empty spec = no methods
        service_no_caps.send_deferral = AsyncMock(return_value="deferred")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [service_no_caps]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        context = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Test",
        )
        result = await bus.send_deferral(context, "test_handler")

        # Should fail because no valid service found
        assert result is False
        service_no_caps.send_deferral.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_without_send_deferral_capability_skipped(self) -> None:
        """Services without send_deferral in capabilities are skipped."""
        from dataclasses import dataclass
        from typing import List
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        @dataclass
        class MockCapabilities:
            actions: List[str]
            scopes: List[str]

        # Service with other capabilities but not send_deferral
        service = MagicMock()
        service.get_capabilities.return_value = MockCapabilities(
            actions=["fetch_guidance"],  # No send_deferral
            scopes=["oversight"],
        )
        service.send_deferral = AsyncMock(return_value="deferred")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [service]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        context = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Test",
        )
        result = await bus.send_deferral(context, "test_handler")

        # Should fail because no service has send_deferral capability
        assert result is False
        service.send_deferral.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_services_support_domain_hint(self) -> None:
        """Returns False when no services support the requested domain."""
        from dataclasses import dataclass, field
        from typing import List
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        @dataclass
        class MockCapabilities:
            actions: List[str]
            scopes: List[str]
            supported_domains: List[str] = field(default_factory=list)

        # Service only supports FINANCIAL, not MEDICAL
        service = MagicMock()
        service.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
            supported_domains=["FINANCIAL"],
        )
        service.send_deferral = AsyncMock(return_value="deferred")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [service]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        # Request MEDICAL domain which no service supports
        context = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Medical consultation needed",
            domain_hint="MEDICAL",
        )
        result = await bus.send_deferral(context, "test_handler")

        # Should fail because no service supports MEDICAL
        assert result is False
        service.send_deferral.assert_not_called()

    @pytest.mark.asyncio
    async def test_defer_until_with_z_suffix(self) -> None:
        """Defer until with Z suffix (ISO 8601) is parsed correctly."""
        from dataclasses import dataclass, field
        from typing import List
        from unittest.mock import AsyncMock, MagicMock

        from ciris_engine.logic.buses.wise_bus import WiseBus
        from ciris_engine.schemas.services.context import DeferralContext

        @dataclass
        class MockCapabilities:
            actions: List[str]
            scopes: List[str]
            supported_domains: List[str] = field(default_factory=list)

        service = MagicMock()
        service.get_capabilities.return_value = MockCapabilities(
            actions=["send_deferral"],
            scopes=["oversight"],
        )
        service.send_deferral = AsyncMock(return_value="deferred")

        mock_registry = MagicMock()
        mock_registry.get_services_by_type.return_value = [service]
        mock_time = MagicMock()
        mock_time.now.return_value = datetime.now(timezone.utc)

        bus = WiseBus(service_registry=mock_registry, time_service=mock_time)

        # Use Z suffix format
        context = DeferralContext(
            thought_id="t1",
            task_id="task1",
            reason="Test with Z suffix",
            defer_until="2026-04-10T12:00:00Z",
        )
        result = await bus.send_deferral(context, "test_handler")

        assert result is True
        service.send_deferral.assert_called_once()


# =========================================================================
# Anti-Gaming Policy Tests
# =========================================================================


class TestAntiGamingPolicy:
    def test_policy_serialization(self) -> None:
        """Policy should round-trip through JSON."""
        policy = CreditGenerationPolicy(
            policy_version="2026-04-08",
            cooldown_seconds=120,
            max_daily_interactions_per_pair=5,
        )
        data = policy.model_dump(mode="json")
        restored = CreditGenerationPolicy(**data)
        assert restored.cooldown_seconds == 120
        assert restored.max_daily_interactions_per_pair == 5

    def test_policy_signature_optional(self) -> None:
        """Policy should work without signature (for local defaults)."""
        policy = CreditGenerationPolicy(policy_version="2026-04-08")
        assert policy.policy_signature is None
        assert policy.policy_key_id is None


# =========================================================================
# Credit Record Batch Tests
# =========================================================================


class TestCreditRecordBatch:
    def test_create_batch(self) -> None:
        now = datetime.now(timezone.utc)
        sig = DualSignature(ed25519_signature="batch_sig", ed25519_key_id="agent-key")
        record_sig = DualSignature(ed25519_signature="rec_sig", ed25519_key_id="agent-key")

        record = CreditRecord(
            interaction_id="test_id_12345678",
            requesting_agent_id="agent_a",
            resolving_agent_id="agent_b",
            requesting_trace_id="t1",
            resolving_trace_id="t2",
            outcome=InteractionOutcome.RESOLVED,
            coherence_score=0.7,
            requesting_agent_signature=record_sig,
            created_at=now,
        )

        batch = CreditRecordBatch(
            records=[record],
            agent_id="agent_a",
            batch_signature=sig,
            submitted_at=now,
        )
        assert len(batch.records) == 1
        assert batch.agent_id == "agent_a"
