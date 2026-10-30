"""Discovery must never construct the mock LLM in a live run (CIRISAgent#1244 regression).

2.15.0 (#1246) made ``MockLLMService.__init__`` latch the mock-LLM trace guard.
``AdapterDiscoveryService`` instantiates every discovered service to read its
tools, and the ``mockllm`` manifest was not excluded, so the setup wizard's
``GET /v1/setup/adapters/available`` (and every action-selection context build,
via the installable-tools cache) constructed ``MockLLMService`` in a LIVE
install. The latch then refused the wizard's ship grant and kept every sealed
trace on the local tee: the five-platform nightly authored 0 traces from
2026-10-09 on, and so would every fresh desktop or mobile install.

A mock module now loads only on an explicit mock request (``--mock-llm``,
``CIRIS_MOCK_LLM``, the runtime module list, an operator adapter load).
"""

import sys
import types
from typing import Any, Iterator, List, Optional, Tuple

import pytest

from ciris_adapters.mock_llm import service as mock_service_module
from ciris_engine.logic.services.governance.consent import trace_sharing
from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService
from ciris_engine.logic.utils.mock_llm_guard import is_mock_llm_active, mock_llm_source
from ciris_engine.schemas.consent.trace_sharing import TraceConsentSource, TraceSharingGrantResult
from ciris_engine.schemas.runtime.manifest import ServiceManifest

CANONICAL = "ciris-canonical-1"


@pytest.fixture
def constructions(monkeypatch: pytest.MonkeyPatch) -> Iterator[List[str]]:
    """Record every MockLLMService construction (the original __init__ still runs)."""
    made: List[str] = []
    original = mock_service_module.MockLLMService.__init__

    def spy(self: Any, *args: Any, **kwargs: Any) -> None:
        made.append("MockLLMService")
        original(self, *args, **kwargs)

    monkeypatch.setattr(mock_service_module.MockLLMService, "__init__", spy)
    yield made


@pytest.fixture
def mock_manifest() -> ServiceManifest:
    """The REAL mockllm manifest, as discovery finds it under ciris_adapters/."""
    for manifest in AdapterDiscoveryService().discover_adapters():
        if manifest.module.name == "mockllm":
            assert manifest.module.is_mock, "fixture premise: the mockllm manifest declares MOCK"
            return manifest
    pytest.fail("mockllm manifest not discovered under ciris_adapters/")


@pytest.fixture
def discovery_sees_mock(monkeypatch: pytest.MonkeyPatch, mock_manifest: ServiceManifest) -> None:
    """Every AdapterDiscoveryService in this test discovers exactly the real mockllm manifest."""
    monkeypatch.setattr(AdapterDiscoveryService, "discover_adapters", lambda self: [mock_manifest])


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, Optional[list], bool]]:
    """A ciris_server stand-in (no network, no :4243) that records ship grants."""
    calls: List[Tuple[str, Optional[list], bool]] = []
    fake = types.ModuleType("ciris_server")
    fake.author_federation_consent = lambda peer, prefixes, analyze: calls.append((peer, prefixes, analyze))  # type: ignore[attr-defined]
    fake.delivery_status = lambda: {"canonical_targets": [CANONICAL]}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ciris_server", fake)
    return calls


class TestDiscoveryNeverConstructsTheMock:
    def test_manifest_flag_skips_mock_for_auto_load(self, mock_manifest: ServiceManifest) -> None:
        reason = AdapterDiscoveryService()._should_skip_for_auto_load(mock_manifest)
        assert reason is not None and "MOCK" in reason

    @pytest.mark.asyncio
    async def test_setup_wizard_adapter_listing(
        self, real_llm_mode: None, discovery_sees_mock: None, constructions: List[str]
    ) -> None:
        """GET /v1/setup/adapters/available — the call the 2026-10-14 nightly made at 17:22:11."""
        from ciris_engine.logic.adapters.api.routes.setup.providers import list_available_adapters_for_setup

        response = await list_available_adapters_for_setup()
        names = [a["name"] for a in response.data["eligible"] + response.data["ineligible"]]
        assert "mockllm" not in names
        assert constructions == []
        assert not is_mock_llm_active(), f"mock latched by discovery: {mock_llm_source()}"

    @pytest.mark.asyncio
    async def test_skill_auto_load(
        self, real_llm_mode: None, discovery_sees_mock: None, constructions: List[str]
    ) -> None:
        eligible = await AdapterDiscoveryService().load_eligible_adapters()
        assert "mockllm" not in eligible
        assert constructions == []
        assert not is_mock_llm_active()

    @pytest.mark.asyncio
    async def test_per_adapter_eligibility_by_name(
        self, real_llm_mode: None, discovery_sees_mock: None, constructions: List[str]
    ) -> None:
        """``get_adapter_eligibility`` bypasses the listing skip; the instantiate choke point holds."""
        assert await AdapterDiscoveryService().get_adapter_eligibility("mockllm") is None
        assert constructions == []
        assert not is_mock_llm_active()

    @pytest.mark.asyncio
    async def test_action_selection_installable_tools_cache(
        self, real_llm_mode: None, discovery_sees_mock: None, constructions: List[str]
    ) -> None:
        """The installable-tools block is built from a discovery report (reused for a TTL, see context_builder)."""
        from ciris_engine.logic.dma.action_selection.context_builder import ActionSelectionContextBuilder

        builder = ActionSelectionContextBuilder.__new__(ActionSelectionContextBuilder)
        await builder._build_installable_tools()
        assert constructions == []
        assert not is_mock_llm_active()


class TestLiveFirstRunThenWizard:
    @pytest.mark.asyncio
    async def test_wizard_listing_then_real_provider_grants_ship(
        self,
        real_llm_mode: None,
        discovery_sees_mock: None,
        constructions: List[str],
        fake_server: List[Tuple[str, Optional[list], bool]],
    ) -> None:
        """First-run boot, the wizard lists adapters, setup completes with a real provider: ship granted."""
        from ciris_engine.logic.adapters.api.routes.setup.providers import list_available_adapters_for_setup

        await list_available_adapters_for_setup()
        result = TraceSharingGrantResult(source=TraceConsentSource.SETUP_WIZARD, opted_in=True)
        trace_sharing._author_ship_grant(result, analyze=True)

        assert constructions == []
        assert not any("mock LLM active" in e for e in result.errors), result.errors
        assert result.peers_authored == [CANONICAL]
        assert fake_server == [(CANONICAL, None, True)]

        from ciris_engine.logic.utils.mock_llm_guard import TraceRunKind, trace_run_kind

        assert trace_run_kind() == TraceRunKind.PRODUCTION


class TestExplicitMockStillLatches:
    """Negative: an explicitly requested mock still loads, latches and is refused."""

    def test_module_loader_mock_load_latches(self, real_llm_mode: None) -> None:
        from ciris_engine.logic.runtime.module_loader import ModuleLoader

        loader = ModuleLoader()
        assert loader.load_module("mock_llm"), "explicit mock module load failed"
        assert is_mock_llm_active()
        assert (mock_llm_source() or "").startswith("module_loader:")

    def test_explicit_construction_latches_and_refuses_ship(
        self, real_llm_mode: None, fake_server: List[Tuple[str, Optional[list], bool]]
    ) -> None:
        mock_service_module.MockLLMService()
        assert mock_llm_source() == "MockLLMService"
        result = TraceSharingGrantResult(source=TraceConsentSource.SETUP_WIZARD, opted_in=True)
        trace_sharing._author_ship_grant(result, analyze=True)
        assert fake_server == []
        assert any("mock LLM active" in e for e in result.errors)

    def test_mock_llm_cli_flag_is_mock(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from ciris_engine.logic.utils.mock_llm_guard import TraceRunKind, trace_run_kind

        monkeypatch.setattr(sys, "argv", ["main.py", "--adapter", "api", "--mock-llm"])
        assert is_mock_llm_active()
        assert trace_run_kind() == TraceRunKind.MOCK
