"""Regression test for the registration-time prohibition gate on WISE_AUTHORITY providers.

Background: until 2.8.8, ServiceRegistry.register_service accepted a
`capabilities` list without checking it against the prohibitions table.
A wisdom source declaring a NEVER_ALLOWED capability (e.g. `torture`,
`pastoral_care`) would only get caught the first time someone actually
asked for it via WiseBus.request_guidance — which is too late.

This test pins the cheap-close fix from MISSION.md §2.3:
  - NEVER_ALLOWED capabilities are rejected at registration.
  - REQUIRES_SEPARATE_MODULE capabilities still register successfully
    (they are gated at query-time inside WiseBus._validate_capability,
    pending the future registry-attestation work).
  - Non-WISE_AUTHORITY service types are unaffected.
  - WISE_AUTHORITY providers with only safe capabilities register cleanly.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.schemas.runtime.enums import ServiceType


def _fake_provider(name: str = "FakeWA") -> Mock:
    """Build a provider with a service_name attribute the registry uses for naming."""
    p = Mock()
    p.service_name = name
    return p


def test_registration_rejects_never_allowed_capability():
    """NEVER_ALLOWED capability → ValueError at registration time."""
    registry = ServiceRegistry()
    with pytest.raises(ValueError, match="REGISTRATION REJECTED"):
        registry.register_service(
            service_type=ServiceType.WISE_AUTHORITY,
            provider=_fake_provider("HostileWA"),
            priority=Priority.NORMAL,
            capabilities=["fetch_guidance", "torture"],
        )
    assert registry.get_provider_info(service_type="wise_authority")["services"]["wise_authority"] == []


def test_registration_rejects_spiritual_direction_capability():
    """A second NEVER_ALLOWED category (SPIRITUAL_DIRECTION) — not just weapons."""
    registry = ServiceRegistry()
    with pytest.raises(ValueError, match="NEVER_ALLOWED capability 'pastoral_care'"):
        registry.register_service(
            service_type=ServiceType.WISE_AUTHORITY,
            provider=_fake_provider("ChaplainWA"),
            priority=Priority.NORMAL,
            capabilities=["pastoral_care"],
        )


def test_registration_allows_requires_separate_module():
    """REQUIRES_SEPARATE_MODULE capabilities must still register; query-time gate handles them.

    This is the deliberate gap documented in MISSION.md §2.3: licensed
    sister modules (CIRISMedical etc.) legitimately declare
    REQUIRES_SEPARATE_MODULE capabilities, and we don't yet have the
    registry-signed attestation flow to distinguish them from
    unauthorized providers at registration time.
    """
    registry = ServiceRegistry()
    name = registry.register_service(
        service_type=ServiceType.WISE_AUTHORITY,
        provider=_fake_provider("MedicalLikeWA"),
        priority=Priority.NORMAL,
        capabilities=["fetch_guidance", "diagnose"],
    )
    assert name == "MedicalLikeWA"
    providers = registry._services[ServiceType.WISE_AUTHORITY]
    assert len(providers) == 1
    assert "diagnose" in providers[0].capabilities


def test_registration_allows_safe_capabilities():
    """Plain WA capabilities → register cleanly."""
    registry = ServiceRegistry()
    name = registry.register_service(
        service_type=ServiceType.WISE_AUTHORITY,
        provider=_fake_provider("CleanWA"),
        priority=Priority.NORMAL,
        capabilities=["fetch_guidance", "send_deferral"],
    )
    assert name == "CleanWA"


def test_registration_gate_does_not_apply_to_other_service_types():
    """Only WISE_AUTHORITY is gated; other service types may legitimately
    have capability strings that incidentally match prohibition tokens
    (e.g. an LLM with a 'medical' tag for routing). The bus-level
    prohibition contract is specifically about wisdom-source providers,
    not about every service in the system.
    """
    registry = ServiceRegistry()
    # An LLM with a capability string that would be NEVER_ALLOWED for a WA
    # should NOT be rejected here — different service type, different contract.
    name = registry.register_service(
        service_type=ServiceType.LLM,
        provider=_fake_provider("WeirdlyNamedLLM"),
        priority=Priority.NORMAL,
        capabilities=["torture"],  # not a real LLM cap, but proves the gate is WA-only
    )
    assert name == "WeirdlyNamedLLM"


def test_registration_with_no_capabilities_is_ok():
    """Empty / None capabilities list → no gate, no error."""
    registry = ServiceRegistry()
    # None
    name = registry.register_service(
        service_type=ServiceType.WISE_AUTHORITY,
        provider=_fake_provider("NoCapsWA"),
        priority=Priority.NORMAL,
        capabilities=None,
    )
    assert name == "NoCapsWA"
    # Empty list
    name2 = registry.register_service(
        service_type=ServiceType.WISE_AUTHORITY,
        provider=_fake_provider("EmptyCapsWA"),
        priority=Priority.NORMAL,
        capabilities=[],
    )
    assert name2 == "EmptyCapsWA"
