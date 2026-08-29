"""The agent-tier capability field must produce four distinguishable wire shapes.

CIRISClient's `CapabilityWire` reads `agent_capabilities` off this document and
maps it to four states with four different remedies:

    key absent      UNDECLARED    the agent predates the field  -> upgrade it
    null            UNDETERMINED  it could not read its registry -> retry
    []              ABSENT        it read, and holds nothing     -> use another
    [...]           membership    the declared set               -> proceed

Collapsing any pair produces a confident wrong answer rather than a missing one.
The collapse has already been committed three times on this surface, most
recently by the reader whose whole purpose was to prevent it — which is why the
shapes are asserted here explicitly rather than left to follow from the types.

The pair these tests exist for is `null` vs `[]`. A brain that is still
initialising has no service registry yet; reporting `[]` there tells an operator
their agent can do nothing, permanently, on the strength of a condition that
resolves in seconds.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from ciris_engine.logic.adapters.api.routes.system.helpers import (
    AGENT_CAPABILITY_SERVICES,
    collect_agent_capabilities,
)
from ciris_engine.logic.adapters.api.routes.system.schemas import SystemHealthResponse
from ciris_engine.schemas.runtime.enums import ServiceType


class _Registry:
    """A service registry holding exactly the given types."""

    def __init__(self, types: Optional[List[ServiceType]] = None, raises: bool = False) -> None:
        self._types = set(types or [])
        self._raises = raises

    def get_services_by_type(self, service_type: ServiceType) -> List[Any]:
        if self._raises:
            raise RuntimeError("registry unavailable")
        return [object()] if service_type in self._types else []


def _request(registry: Any) -> Any:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(service_registry=registry)))


# ── the two states that must never collapse ──────────────────────────────────


def test_no_registry_is_undetermined_not_absent() -> None:
    """No registry means we could not read our own state, not that we hold nothing."""
    got = collect_agent_capabilities(_request(None), has_working_llm=True)
    assert got is None, "a missing registry must be UNDETERMINED (null), never ABSENT ([])"


def test_a_raising_registry_is_undetermined_not_absent() -> None:
    """A registry that throws is a registry we did not read."""
    got = collect_agent_capabilities(_request(_Registry(raises=True)), has_working_llm=True)
    assert got is None


def test_an_empty_registry_is_absent_not_undetermined() -> None:
    """We read it, and the brain holds nothing. That is a real, different answer."""
    got = collect_agent_capabilities(_request(_Registry([])), has_working_llm=False)
    assert got == [], "a readable, empty registry must be ABSENT ([]), never UNDETERMINED (null)"


# ── membership ───────────────────────────────────────────────────────────────


def test_registered_services_become_capabilities() -> None:
    got = collect_agent_capabilities(
        _request(_Registry([ServiceType.COMMUNICATION, ServiceType.MEMORY])),
        has_working_llm=False,
    )
    assert got == ["agent:converse", "agent:remember"], got


def test_the_set_is_sorted_so_the_wire_is_stable() -> None:
    """An unstable order makes two identical answers look like a change."""
    got = collect_agent_capabilities(
        _request(_Registry(list(AGENT_CAPABILITY_SERVICES.values()))),
        has_working_llm=False,
    )
    assert got == sorted(got)


# ── reasoning is not established by registration ─────────────────────────────


def test_a_registered_but_unusable_llm_does_not_claim_reasoning() -> None:
    """`degraded_mode` exists because a provider can be registered and dead.

    Claiming `agent:reason` on registration alone is the permissive error — and
    the capability gate is explicitly not there to catch it, because this is not
    a security boundary.
    """
    got = collect_agent_capabilities(_request(_Registry([ServiceType.LLM])), has_working_llm=False)
    assert "agent:reason" not in got


def test_a_working_llm_claims_reasoning() -> None:
    got = collect_agent_capabilities(_request(_Registry([ServiceType.LLM])), has_working_llm=True)
    assert got == ["agent:reason"]


# ── the wire itself ──────────────────────────────────────────────────────────


def _render(agent_capabilities: Optional[List[str]]) -> dict:
    response = SystemHealthResponse(
        status="healthy",
        version="0.0.0",
        uptime_seconds=1.0,
        services={},
        initialization_complete=True,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        agent_capabilities=agent_capabilities,
    )
    return json.loads(response.model_dump_json())


def test_undetermined_reaches_the_wire_as_null_not_as_an_omitted_key() -> None:
    """THE regression this file exists for.

    If the serializer drops nulls, UNDETERMINED arrives as UNDECLARED and the
    operator is told their current agent is out of date — the exact false
    diagnosis that has now been produced three times on this surface.
    """
    doc = _render(None)
    assert "agent_capabilities" in doc, "the key was omitted; null must be explicit on the wire"
    assert doc["agent_capabilities"] is None


def test_absent_reaches_the_wire_as_an_empty_list() -> None:
    doc = _render([])
    assert doc["agent_capabilities"] == []


def test_membership_reaches_the_wire_as_a_list_of_strings() -> None:
    doc = _render(["agent:converse"])
    assert doc["agent_capabilities"] == ["agent:converse"]
    assert all(isinstance(x, str) for x in doc["agent_capabilities"])


# ── provenance ───────────────────────────────────────────────────────────────


def test_the_agent_field_is_not_named_capabilities() -> None:
    """Conferred scopes and agent features must not be merged.

    One is signed by the trust root and enforced by the node; the other is a
    property of the running brain that nothing attests. `/v1/system/health` is
    the node's health merged with the brain's, so a bare `capabilities` here
    could not be attributed to either tier by a reader holding only the parsed
    set. CIRISServer refuses the same laundering at its own tier.
    """
    doc = _render(["agent:converse"])
    assert "capabilities" not in doc, "a bare `capabilities` here is unattributable — use agent_capabilities"
    assert "agent_capabilities" in doc


@pytest.mark.parametrize("capability", sorted(AGENT_CAPABILITY_SERVICES))
def test_every_agent_capability_is_namespaced(capability: str) -> None:
    """`agent:` so no reader can mistake one for a conferred `infra:` scope."""
    assert capability.startswith("agent:")
