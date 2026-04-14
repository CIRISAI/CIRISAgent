"""Tests for the MobileLocalLLMAdapter wrapper and lifecycle."""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

from ciris_adapters.mobile_local_llm.adapter import MobileLocalLLMAdapter
from ciris_adapters.mobile_local_llm.capability import DeviceCapabilityReport
from ciris_adapters.mobile_local_llm.config import (
    DeviceTier,
    MobileLocalLLMConfig,
    ModelVariant,
    Platform,
)
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.runtime.enums import ServiceType


def _capable_report() -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=DeviceTier.CAPABLE_E2B,
        platform=Platform.ANDROID,
        architecture="arm64-v8a",
        total_ram_gb=6.5,
        available_ram_gb=3.5,
        free_disk_gb=10.0,
        reasons=["capable"],
    )


def _ios_stub_report() -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=DeviceTier.IOS_STUB,
        platform=Platform.IOS,
        architecture="arm64-v8a",
        total_ram_gb=8.0,
        available_ram_gb=4.0,
        free_disk_gb=20.0,
        reasons=["iOS hardware capable but no Gemma 4 model bundle found"],
    )


def _incapable_report() -> DeviceCapabilityReport:
    return DeviceCapabilityReport(
        tier=DeviceTier.INCAPABLE,
        platform=Platform.ANDROID,
        architecture="arm64-v8a",
        total_ram_gb=3.0,
        available_ram_gb=1.0,
        free_disk_gb=5.0,
        reasons=["total RAM 3.0GB below threshold"],
    )


@pytest.fixture
def patched_probe():
    """Patch the capability probe used by both adapter and service."""
    with mock.patch(
        "ciris_adapters.mobile_local_llm.adapter.probe_device_capability"
    ) as adapter_probe, mock.patch(
        "ciris_adapters.mobile_local_llm.service.probe_device_capability"
    ) as service_probe:
        yield adapter_probe, service_probe


@pytest.mark.asyncio
class TestAdapterRegistration:
    async def test_registers_single_llm_service_at_high_priority(self):
        cfg = MobileLocalLLMConfig()
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        services = adapter.get_services_to_register()
        assert len(services) == 1
        reg = services[0]
        assert reg.service_type == ServiceType.LLM
        assert reg.priority == Priority.HIGH
        assert reg.provider is adapter.llm_service
        assert "provider:mobile_local" in reg.capabilities
        assert "call_llm_structured" in reg.capabilities
        assert f"model:{cfg.model_variant.value}" in reg.capabilities

    async def test_accepts_config_as_pydantic(self):
        cfg = MobileLocalLLMConfig(model_variant=ModelVariant.GEMMA_4_E4B)
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        assert adapter.config.model_variant == ModelVariant.GEMMA_4_E4B

    async def test_accepts_config_as_dict_overlay(self):
        adapter = MobileLocalLLMAdapter(
            runtime=None, adapter_config={"port": 9100, "host": "127.0.0.1"}
        )
        assert adapter.config.port == 9100


@pytest.mark.asyncio
class TestAdapterLifecycle:
    async def test_start_on_capable_device_spawns_health_loop(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _capable_report()
        service_probe.return_value = _capable_report()

        cfg = MobileLocalLLMConfig(health_interval_seconds=0.05)
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        # Replace the underlying server manager so we don't spawn anything.
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock(return_value=None)
        mgr.stop = mock.AsyncMock(return_value=None)
        mgr.health_check = mock.AsyncMock(return_value=True)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]

        await adapter.start()
        try:
            assert adapter._running is True  # type: ignore[attr-defined]
            assert adapter.llm_service.available is True
            assert adapter._health_task is not None  # type: ignore[attr-defined]
        finally:
            await adapter.stop()
        assert adapter._running is False  # type: ignore[attr-defined]
        mgr.stop.assert_awaited()

    async def test_start_on_incapable_device_skips_health_loop(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _incapable_report()
        service_probe.return_value = _incapable_report()

        cfg = MobileLocalLLMConfig()
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock(return_value=None)
        mgr.stop = mock.AsyncMock(return_value=None)
        mgr.health_check = mock.AsyncMock(return_value=False)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]

        await adapter.start()
        try:
            assert adapter.llm_service.available is False
            assert adapter._health_task is None  # type: ignore[attr-defined]
            mgr.start.assert_not_awaited()
        finally:
            await adapter.stop()

    async def test_stop_cancels_health_loop_cleanly(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _capable_report()
        service_probe.return_value = _capable_report()

        cfg = MobileLocalLLMConfig(health_interval_seconds=0.05)
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock(return_value=None)
        mgr.stop = mock.AsyncMock(return_value=None)
        mgr.health_check = mock.AsyncMock(return_value=True)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]

        await adapter.start()
        await asyncio.sleep(0.12)  # let the health loop run at least once
        await adapter.stop()
        assert adapter._health_task is None or adapter._health_task.done()  # type: ignore[attr-defined]

    async def test_run_lifecycle_returns_when_agent_task_finishes(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _incapable_report()
        service_probe.return_value = _incapable_report()

        cfg = MobileLocalLLMConfig()
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock(return_value=None)
        mgr.stop = mock.AsyncMock(return_value=None)
        mgr.health_check = mock.AsyncMock(return_value=True)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]

        await adapter.start()

        async def agent():
            await asyncio.sleep(0.01)

        await adapter.run_lifecycle(asyncio.create_task(agent()))
        assert adapter._running is False  # type: ignore[attr-defined]


@pytest.mark.asyncio
class TestStatusReporting:
    async def test_get_status_reports_device_not_capable(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _incapable_report()
        service_probe.return_value = _incapable_report()

        cfg = MobileLocalLLMConfig()
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock()
        mgr.stop = mock.AsyncMock()
        mgr.health_check = mock.AsyncMock(return_value=False)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]
        await adapter.start()
        status = adapter.get_status()
        assert status.adapter_type == "mobile_local_llm"
        assert status.is_running is True
        assert "device_not_capable" in (status.error or "")
        await adapter.stop()

    async def test_get_config_surfaces_tier_and_variant(self, patched_probe):
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _capable_report()
        service_probe.return_value = _capable_report()

        cfg = MobileLocalLLMConfig(port=9090)
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock()
        mgr.stop = mock.AsyncMock()
        mgr.health_check = mock.AsyncMock(return_value=True)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]
        await adapter.start()
        config_snapshot = adapter.get_config()
        assert config_snapshot.adapter_type == "mobile_local_llm"
        assert config_snapshot.settings["variant"] == "gemma-4-e2b"
        assert config_snapshot.settings["port"] == 9090
        assert config_snapshot.settings["device_tier"] == "capable_e2b"
        await adapter.stop()

    async def test_get_status_reports_ios_stub_distinctly(self, patched_probe):
        """iOS stub is reported as a distinct state — not as a plain failure."""
        adapter_probe, service_probe = patched_probe
        adapter_probe.return_value = _ios_stub_report()
        service_probe.return_value = _ios_stub_report()

        cfg = MobileLocalLLMConfig()
        adapter = MobileLocalLLMAdapter(runtime=None, adapter_config=cfg)
        mgr = mock.MagicMock()
        mgr.start = mock.AsyncMock()
        mgr.stop = mock.AsyncMock()
        mgr.health_check = mock.AsyncMock(return_value=False)
        adapter.llm_service._server = mgr  # type: ignore[attr-defined]
        await adapter.start()
        status = adapter.get_status()
        config_snapshot = adapter.get_config()
        assert status.error is not None
        assert status.error.startswith("ios_stub")
        assert config_snapshot.settings["device_tier"] == "ios_stub"
        mgr.start.assert_not_awaited()  # stub tier must not spawn the server
        await adapter.stop()

    async def test_adapter_export_alias(self):
        from ciris_adapters.mobile_local_llm import Adapter

        assert Adapter is MobileLocalLLMAdapter
