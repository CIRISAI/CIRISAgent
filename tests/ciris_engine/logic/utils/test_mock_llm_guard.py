"""The mock-LLM trace-export guard and run-kind marker (CIRISAgent#1244, #1245).

1,499 mock-LLM traces reached the PRODUCTION canonical. The guard is the one
place that decides whether a trace may leave the node; these tests pin each
detection signal, the loopback-only allowance and the run-kind resolution.
"""

import logging
import sys

import pytest

from ciris_engine.logic.utils import mock_llm_guard
from ciris_engine.logic.utils.mock_llm_guard import (
    TraceRunKind,
    is_loopback_endpoint,
    is_mock_llm_active,
    mark_mock_llm_active,
    remote_trace_export_permitted,
    trace_run_kind,
)

PRODUCTION_LENS = "https://lens.ciris-services-1.ai/lens-api/api/v1"


class TestDetection:
    def test_no_signal_means_real_llm(self, real_llm_mode: None) -> None:
        assert not is_mock_llm_active()
        assert mock_llm_guard.mock_llm_source() is None

    def test_env_var(self, mock_llm_mode: None) -> None:
        assert is_mock_llm_active()
        assert mock_llm_guard.mock_llm_source() == "env:CIRIS_MOCK_LLM"

    @pytest.mark.parametrize("value", ["false", "0", "", "no"])
    def test_falsy_env_values_are_not_mock(
        self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("CIRIS_MOCK_LLM", value)
        assert not is_mock_llm_active()

    def test_dotenv_value(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from ciris_engine.logic.config import env_utils

        monkeypatch.setitem(env_utils._ENV_VALUES, "CIRIS_MOCK_LLM", "true")
        monkeypatch.setattr(env_utils, "_ENV_LOADED", True)
        assert mock_llm_guard.mock_llm_source() == ".env:CIRIS_MOCK_LLM"

    def test_cli_flag(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["main.py", "--adapter", "api", "--mock-llm"])
        assert mock_llm_guard.mock_llm_source() == "argv:--mock-llm"

    def test_latch_is_one_way(self, real_llm_mode: None) -> None:
        mark_mock_llm_active("test")
        mark_mock_llm_active("second-caller-does-not-overwrite")
        assert mock_llm_guard.mock_llm_source() == "test"
        # There is no public way to clear it: only the test reset exists.
        assert not hasattr(mock_llm_guard, "clear_mock_llm_active")

    def test_constructing_the_mock_service_latches(self, real_llm_mode: None) -> None:
        from ciris_adapters.mock_llm.service import MockLLMService

        assert not is_mock_llm_active()
        MockLLMService()
        assert mock_llm_guard.mock_llm_source() == "MockLLMService"

    def test_loading_the_mock_module_latches(self, real_llm_mode: None) -> None:
        import json
        from pathlib import Path

        from ciris_engine.logic.runtime.module_loader import ModuleLoader
        from ciris_engine.schemas.runtime.manifest import ServiceManifest

        root = Path(__file__).resolve().parents[4]
        manifest = ServiceManifest.model_validate(
            json.loads((root / "ciris_adapters" / "mock_llm" / "manifest.json").read_text())
        )
        ModuleLoader()._handle_mock_module("mock_llm", manifest, disable_core=True)
        assert mock_llm_guard.mock_llm_source() == "module_loader:mock_llm"


class TestLoopback:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://127.0.0.1:18080/lens-api/api/v1",
            "http://localhost:18080",
            "http://[::1]:18080/x",
            "127.0.0.5:4242",
            "localhost",
            "http://foo.localhost:8080",
        ],
    )
    def test_loopback(self, endpoint: str) -> None:
        assert is_loopback_endpoint(endpoint)

    @pytest.mark.parametrize(
        "endpoint",
        [
            PRODUCTION_LENS,
            "108.61.242.236:4242",
            "http://10.0.0.5:8080",
            "http://localhost.evil.example:8080",
            "http://127.0.0.1.nip.io/",
            "",
            None,
        ],
    )
    def test_not_loopback(self, endpoint: str) -> None:
        assert not is_loopback_endpoint(endpoint)


class TestRefusal:
    def test_real_llm_permits_production(self, real_llm_mode: None) -> None:
        assert remote_trace_export_permitted("lens", PRODUCTION_LENS)
        assert remote_trace_export_permitted("federation replication grant")

    def test_mock_refuses_production_and_logs_once_at_info(
        self, mock_llm_mode: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=mock_llm_guard.__name__):
            assert not remote_trace_export_permitted("lens", PRODUCTION_LENS)
            assert not remote_trace_export_permitted("lens", PRODUCTION_LENS)
        refusals = [r for r in caplog.records if "REFUSED remote trace export via lens" in r.getMessage()]
        assert len(refusals) == 1
        assert refusals[0].levelno == logging.INFO

    def test_mock_refuses_the_remote_mesh(self, mock_llm_mode: None) -> None:
        assert not remote_trace_export_permitted("federation replication grant")

    def test_mock_allows_loopback(self, mock_llm_mode: None) -> None:
        assert remote_trace_export_permitted("lens", "http://127.0.0.1:18080/lens-api/api/v1")

    def test_consent_cannot_lift_the_refusal(self, mock_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
        monkeypatch.setenv("CIRIS_FEDERATION_DELIVERY", "true")
        assert not remote_trace_export_permitted("lens", PRODUCTION_LENS)


class TestRunKind:
    def test_default_is_production(self, real_llm_mode: None) -> None:
        assert trace_run_kind() == TraceRunKind.PRODUCTION

    @pytest.mark.parametrize("value,kind", [("qa", TraceRunKind.QA), ("battery", TraceRunKind.BATTERY)])
    def test_harness_declared(
        self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch, value: str, kind: TraceRunKind
    ) -> None:
        monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", value)
        assert trace_run_kind() == kind

    def test_mock_always_wins(self, mock_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", "production")
        assert trace_run_kind() == TraceRunKind.MOCK

    def test_unknown_value_fails_toward_synthetic(
        self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", "qa-typo")
        with caplog.at_level(logging.WARNING, logger=mock_llm_guard.__name__):
            assert trace_run_kind() == TraceRunKind.QA
        assert any("is not one of qa|battery|production" in r.getMessage() for r in caplog.records)


class TestBootstrapModulesLatchBeforeEdge:
    """Codex P1: a mock named only in RuntimeBootstrapConfig.modules must latch before edge init."""

    @pytest.mark.parametrize("modules", [["mock_llm"], ["modular:mockllm"], ["ciris_adapters.mock_llm"]])
    def test_constructor_check_latches_from_modules(self, real_llm_mode: None, modules: list) -> None:
        from types import SimpleNamespace

        from ciris_engine.logic.runtime.bootstrap_helpers import check_mock_llm

        check_mock_llm(SimpleNamespace(modules_to_load=list(modules)))
        assert is_mock_llm_active()

    def test_non_mock_modules_do_not_latch(self, real_llm_mode: None) -> None:
        assert not mock_llm_guard.latch_if_mock_llm_module(["modular:ciris_accord_metrics", "mock_llm_extra"], "t")
        assert not is_mock_llm_active()

    @pytest.mark.asyncio
    async def test_edge_init_step_sees_the_latch(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from ciris_engine.logic.runtime import edge_runtime, initialization_steps

        seen: list = []
        monkeypatch.setattr(edge_runtime, "initialize_edge_runtime", lambda _dir: seen.append(is_mock_llm_active()))
        runtime = SimpleNamespace(modules_to_load=["mock_llm"], essential_config=_essential_config())
        await initialization_steps.init_edge_runtime(runtime)
        assert seen == [True], "the edge initialized before the bootstrap mock module was latched"

    @pytest.mark.asyncio
    async def test_runtime_edge_init_sees_the_latch(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from ciris_engine.logic.runtime import edge_runtime
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        seen: list = []
        monkeypatch.setattr(edge_runtime, "initialize_edge_runtime", lambda _dir: seen.append(is_mock_llm_active()))
        fake = SimpleNamespace(modules_to_load=["mock_llm"], _ensure_config=_essential_config)
        await CIRISRuntime._init_edge_runtime(fake)  # type: ignore[arg-type]
        assert seen == [True]


def _essential_config():  # type: ignore[no-untyped-def]
    from ciris_engine.schemas.config.essential import EssentialConfig

    return EssentialConfig()
