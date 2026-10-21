"""Tests for the MobileLocalLLMService LLM provider."""

from __future__ import annotations

from unittest import mock

import pytest
from pydantic import BaseModel

from ciris_adapters.mobile_local_llm.capability import DeviceCapabilityReport
from ciris_adapters.mobile_local_llm.config import DeviceTier, MobileLocalLLMConfig, ModelVariant, Platform
from ciris_adapters.mobile_local_llm.service import MobileLocalLLMService, _estimate_input_tokens


class _SampleResponse(BaseModel):
    answer: str


def _capable_report(tier: DeviceTier = DeviceTier.CAPABLE_E2B) -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=tier,
        platform=Platform.ANDROID,
        architecture="arm64-v8a",
        total_ram_gb=8.0,
        available_ram_gb=4.0,
        free_disk_gb=10.0,
        reasons=["test"],
    )


def _ios_stub_report() -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=DeviceTier.IOS_STUB,
        platform=Platform.IOS,
        architecture="arm64-v8a",
        total_ram_gb=8.0,
        available_ram_gb=4.0,
        free_disk_gb=10.0,
        reasons=["iOS capable but no model bundle"],
    )


def _incapable_report() -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=DeviceTier.INCAPABLE,
        platform=Platform.DESKTOP,
        architecture="x86_64",
        total_ram_gb=4.0,
        available_ram_gb=2.0,
        free_disk_gb=1.0,
        reasons=["running on desktop"],
    )


def _fake_server_manager(*, available=True, health=True):
    mgr = mock.MagicMock()
    mgr.start = (
        mock.AsyncMock(return_value=None)
        if available
        else mock.AsyncMock(
            side_effect=__import__(
                "ciris_adapters.mobile_local_llm.inference_server", fromlist=["InferenceServerError"]
            ).InferenceServerError("boom")
        )
    )
    mgr.stop = mock.AsyncMock(return_value=None)
    mgr.health_check = mock.AsyncMock(return_value=health)
    return mgr


@pytest.mark.asyncio
class TestLifecycle:
    async def test_capable_device_becomes_available(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager(available=True, health=True)
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()
        try:
            assert svc.available is True
            assert await svc.is_healthy() is True
        finally:
            await svc.stop()
        mgr.start.assert_awaited_once()
        mgr.stop.assert_awaited_once()

    async def test_incapable_device_stays_unavailable(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager()
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_incapable_report())
        await svc.start()
        assert svc.available is False
        assert await svc.is_healthy() is False
        mgr.start.assert_not_awaited()
        await svc.stop()

    async def test_disabled_config_skips_start(self):
        cfg = MobileLocalLLMConfig(enabled=False)
        mgr = _fake_server_manager()
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()
        assert svc.available is False
        mgr.start.assert_not_awaited()
        await svc.stop()

    async def test_ios_stub_stays_unavailable(self):
        """iOS stub devices must not try to spawn the inference server."""
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager()
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_ios_stub_report())
        await svc.start()
        assert svc.available is False
        assert await svc.is_healthy() is False
        mgr.start.assert_not_awaited()
        await svc.stop()

    async def test_server_start_error_keeps_service_unavailable(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager(available=False)
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()
        assert svc.available is False
        assert await svc.is_healthy() is False
        await svc.stop()

    async def test_e2b_device_rejects_e4b_variant(self):
        """Mid-range phone config: E2B tier should refuse to load E4B."""
        cfg = MobileLocalLLMConfig(model_variant=ModelVariant.GEMMA_4_E4B)
        mgr = _fake_server_manager()
        svc = MobileLocalLLMService(
            cfg,
            server_manager=mgr,
            capability_report=_capable_report(DeviceTier.CAPABLE_E2B),
        )
        await svc.start()
        assert svc.available is False
        mgr.start.assert_not_awaited()
        await svc.stop()

    async def test_is_healthy_reports_probe_result_without_mutating_state(self):
        """is_healthy() is a pure liveness probe.

        It must not permanently mark the service unavailable after a single
        failed probe — otherwise a transient network/timeout error would
        short-circuit all subsequent probes to False and prevent recovery
        before the adapter's 3-strike health loop even runs.
        """
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager(available=True, health=False)
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()
        assert svc.available is True
        # A failing probe reports False but leaves _available intact so the
        # next probe can still observe recovery.
        assert await svc.is_healthy() is False
        assert svc.available is True
        # When the server recovers, the next probe must succeed.
        mgr.health_check = mock.AsyncMock(return_value=True)
        assert await svc.is_healthy() is True
        assert svc.available is True
        await svc.stop()


@pytest.mark.asyncio
class TestCallLLMStructured:
    async def test_raises_when_unavailable(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager()
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_incapable_report())
        await svc.start()
        with pytest.raises(RuntimeError):
            await svc.call_llm_structured(
                messages=[{"role": "user", "content": "hi"}],
                response_model=_SampleResponse,
            )
        await svc.stop()

    async def test_success_path_returns_parsed_response_and_usage(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager(available=True, health=True)
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()

        parsed = _SampleResponse(answer="ok")

        async def fake_dispatch(**_kwargs):
            return parsed

        with mock.patch.object(svc, "_dispatch_structured", side_effect=fake_dispatch):
            result, usage = await svc.call_llm_structured(
                messages=[{"role": "user", "content": "hello world"}],
                response_model=_SampleResponse,
                max_tokens=128,
            )

        assert result is parsed
        assert usage.tokens_input > 0
        assert usage.tokens_output > 0
        assert usage.cost_cents == 0.0
        assert "mobile-local" in (usage.model_used or "")
        await svc.stop()

    async def test_inference_error_marks_unavailable_and_reraises(self):
        cfg = MobileLocalLLMConfig()
        mgr = _fake_server_manager(available=True, health=True)
        svc = MobileLocalLLMService(cfg, server_manager=mgr, capability_report=_capable_report())
        await svc.start()

        async def boom(**_kwargs):
            raise RuntimeError("inference failure")

        with mock.patch.object(svc, "_dispatch_structured", side_effect=boom):
            with pytest.raises(RuntimeError, match="inference failure"):
                await svc.call_llm_structured(
                    messages=[{"role": "user", "content": "hi"}],
                    response_model=_SampleResponse,
                )
        assert svc.available is False
        await svc.stop()


class TestTokenEstimator:
    def test_counts_word_tokens_with_1_3_multiplier(self):
        count = _estimate_input_tokens([{"role": "user", "content": "hello world foo bar"}])
        assert count >= 4

    def test_handles_multimodal_content(self):
        msg = [{"role": "user", "content": [{"type": "text", "text": "hi there friend"}]}]
        # ``MessageDict`` uses ``content: str``, but the implementation is
        # defensive about list content used by multimodal callers. We cast via
        # ``Any`` here.
        count = _estimate_input_tokens(msg)  # type: ignore[arg-type]
        assert count >= 3

    def test_returns_at_least_one(self):
        assert _estimate_input_tokens([]) == 1
